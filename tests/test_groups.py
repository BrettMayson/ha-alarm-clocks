"""Alarm clock groups: the hub, the group entities and their member clocks."""

from __future__ import annotations

from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.alarm_clocks.const import (
    CONF_ALARM_TIME,
    CONF_KIND,
    CONF_MEMBERS,
    DOMAIN,
    KIND_GROUP,
    KIND_HUB,
    STATE_ARMED,
    STATE_RINGING,
)
from custom_components.alarm_clocks.group import entry_kind


@pytest.fixture(autouse=True)
def fixed_clock(freezer: FrozenDateTimeFactory) -> None:
    """Monday noon: clear of the alarm phases, next alarm on Tuesday."""
    freezer.move_to("2026-01-05 12:00:00-08:00")


def _entries_of_kind(hass: HomeAssistant, kind: str) -> list[ConfigEntry]:
    return [e for e in hass.config_entries.async_entries(DOMAIN) if entry_kind(e) == kind]


def _entity_id(hass: HomeAssistant, entry: ConfigEntry, platform: str, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"{entry.entry_id}_{key}"
    )
    assert entity_id is not None, f"{platform}.{key} missing"
    return entity_id


async def _add_clock(
    hass: HomeAssistant, title: str, unique_id: str, options: dict[str, Any]
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=title,
        data={},
        options=options,
        unique_id=unique_id,
        version=2,
        minor_version=2,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _create_group(hass: HomeAssistant) -> ConfigEntry:
    await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_IMPORT}, data={CONF_KIND: KIND_GROUP}
    )
    await hass.async_block_till_done()
    return _entries_of_kind(hass, KIND_GROUP)[-1]


async def _set_members(
    hass: HomeAssistant, group: ConfigEntry, members: list[ConfigEntry]
) -> None:
    result = await hass.config_entries.options.async_init(group.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MEMBERS: [m.entry_id for m in members]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()


async def test_create_group_button_creates_empty_group(
    hass: HomeAssistant, setup_alarm: MockConfigEntry
) -> None:
    """The hub is created with the first clock; its button creates a group."""
    hub = _entries_of_kind(hass, KIND_HUB)[0]
    button = _entity_id(hass, hub, "button", "create_group")

    await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
    await hass.async_block_till_done()

    (group,) = _entries_of_kind(hass, KIND_GROUP)
    assert group.title == "Group 1"
    assert group.options[CONF_MEMBERS] == []

    result = await hass.config_entries.options.async_init(hub.entry_id)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "hub_not_configurable"


async def test_next_alarm_is_earliest_member(
    hass: HomeAssistant, setup_alarm: MockConfigEntry, options: dict[str, Any]
) -> None:
    """The group's next alarm is the earliest next alarm of its members."""
    early = setup_alarm
    late = await _add_clock(
        hass, "Alarm 2", "wecker_2", {**options, CONF_ALARM_TIME: "09:00:00"}
    )
    group = await _create_group(hass)
    await _set_members(hass, group, [early, late])

    group_next = hass.states.get(_entity_id(hass, group, "sensor", "next_alarm"))
    early_next = hass.states.get(_entity_id(hass, early, "sensor", "next_alarm"))
    assert group_next is not None
    assert early_next is not None
    assert group_next.state == early_next.state


async def test_group_dismiss_only_affects_ringing_members(
    hass: HomeAssistant, setup_alarm: MockConfigEntry, options: dict[str, Any]
) -> None:
    """Dismissing the group ends the ringing member and leaves the others alone."""
    ringing = setup_alarm
    idle = await _add_clock(
        hass, "Alarm 2", "wecker_2", {**options, CONF_ALARM_TIME: "09:00:00"}
    )
    group = await _create_group(hass)
    await _set_members(hass, group, [ringing, idle])

    dismiss = _entity_id(hass, group, "button", "dismiss")
    ringing_sensor = _entity_id(hass, group, "binary_sensor", "ringing")
    assert hass.states.get(dismiss).state == "unavailable"

    await ringing.runtime_data.async_trigger_alarm()
    await hass.async_block_till_done()
    assert hass.states.get(ringing_sensor).state == "on"
    assert hass.states.get(dismiss).state != "unavailable"

    await hass.services.async_call("button", "press", {"entity_id": dismiss}, blocking=True)
    await hass.async_block_till_done()

    assert ringing.runtime_data.data.state != STATE_RINGING
    assert idle.runtime_data.data.state == STATE_ARMED
    assert hass.states.get(ringing_sensor).state == "off"


async def test_clock_can_belong_to_two_groups(
    hass: HomeAssistant, setup_alarm: MockConfigEntry
) -> None:
    """A clock in two groups makes both group ringing sensors turn on."""
    first = await _create_group(hass)
    second = await _create_group(hass)
    await _set_members(hass, first, [setup_alarm])
    await _set_members(hass, second, [setup_alarm])

    await setup_alarm.runtime_data.async_trigger_alarm()
    await hass.async_block_till_done()

    for group in (first, second):
        assert hass.states.get(_entity_id(hass, group, "binary_sensor", "ringing")).state == "on"


async def test_unloaded_member_is_dropped_from_group(
    hass: HomeAssistant, setup_alarm: MockConfigEntry, options: dict[str, Any]
) -> None:
    """Unloading a member removes it from the group's combined next alarm."""
    remaining = await _add_clock(
        hass, "Alarm 2", "wecker_2", {**options, CONF_ALARM_TIME: "09:00:00"}
    )
    group = await _create_group(hass)
    await _set_members(hass, group, [setup_alarm, remaining])

    assert await hass.config_entries.async_unload(setup_alarm.entry_id)
    await hass.async_block_till_done()

    group_next = hass.states.get(_entity_id(hass, group, "sensor", "next_alarm"))
    remaining_next = hass.states.get(_entity_id(hass, remaining, "sensor", "next_alarm"))
    assert group_next is not None
    assert remaining_next is not None
    assert group_next.state == remaining_next.state
