"""Alarm clock groups: one device that combines several alarm clocks.

A group owns no alarm. Its entities read the snapshots of its member clocks,
and its buttons act on those members. Every clock keeps its own device.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import (
    CONF_KIND,
    CONF_MEMBERS,
    DOMAIN,
    KIND_CLOCK,
    SIGNAL_CLOCK_UPDATED,
    STATE_ARMED,
    STATE_DISABLED,
    STATE_POST_ACTIVE,
    STATE_POST_PENDING,
    STATE_PRE_ACTIVE,
    STATE_RINGING,
    STATE_SNOOZED,
)
from .coordinator import AlarmClockCoordinator
from .entity import async_assign_entity_id

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import EntityPlatform

_LOGGER = logging.getLogger(__name__)

# The state a group shows when its members are in several states at once.
_STATE_PRIORITY: Final = (
    STATE_RINGING,
    STATE_SNOOZED,
    STATE_PRE_ACTIVE,
    STATE_POST_ACTIVE,
    STATE_POST_PENDING,
    STATE_ARMED,
    STATE_DISABLED,
)


def entry_kind(entry: ConfigEntry) -> str:
    """Kind of a config entry; entries written before groups are clocks."""
    return entry.data.get(CONF_KIND, KIND_CLOCK)


@dataclass(frozen=True)
class AlarmClockGroupSnapshot:
    """Combined state of the members, read by the group entities."""

    state: str
    ringing: bool
    next_alarm: datetime | None
    # A member is ringing or snoozing, so the group buttons have an effect.
    engaged: bool
    snoozable: bool


class AlarmClockGroupCoordinator(DataUpdateCoordinator[AlarmClockGroupSnapshot]):
    """Combines the snapshots of the member clocks. Push based, no polling."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Set up the coordinator without polling."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=entry.title,
            update_interval=None,
        )

    async def async_setup(self) -> None:
        """Recompute the state whenever a clock pushes a change."""
        self.config_entry.async_on_unload(
            async_dispatcher_connect(
                self.hass, SIGNAL_CLOCK_UPDATED, self._async_push
            )
        )
        self._async_push()

    @property
    def members(self) -> list[AlarmClockCoordinator]:
        """Running member clocks. Deleted or unloaded ones are skipped."""
        members: list[AlarmClockCoordinator] = []
        for entry_id in self.config_entry.options.get(CONF_MEMBERS, []):
            entry = self.hass.config_entries.async_get_entry(entry_id)
            if (
                entry is None
                or entry.domain != DOMAIN
                or entry_kind(entry) != KIND_CLOCK
            ):
                continue
            coordinator = getattr(entry, "runtime_data", None)
            if isinstance(coordinator, AlarmClockCoordinator) and coordinator.is_running:
                members.append(coordinator)
        return members

    async def async_apply_options(self) -> None:
        """Apply changed members."""
        self._async_push()

    async def async_snooze(self) -> None:
        """Snooze every member; each one ignores the call unless it is ringing."""
        for member in self.members:
            await member.async_snooze()

    async def async_dismiss(self) -> None:
        """Dismiss every member; each one ignores the call unless it is ringing."""
        for member in self.members:
            await member.async_dismiss()

    @callback
    def _async_push(self) -> None:
        """Recompute the combined state and push it to the group entities."""
        self.async_set_updated_data(self._build_snapshot())

    def _build_snapshot(self) -> AlarmClockGroupSnapshot:
        """Combine the snapshots of the running members."""
        members = self.members
        snapshots = [member.data for member in members]
        states = {snapshot.state for snapshot in snapshots}
        engaged = [
            member
            for member in members
            if member.data.ringing or member.data.snooze_active
        ]
        return AlarmClockGroupSnapshot(
            state=next((s for s in _STATE_PRIORITY if s in states), STATE_DISABLED),
            ringing=any(snapshot.ringing for snapshot in snapshots),
            next_alarm=min(
                (s.next_alarm for s in snapshots if s.next_alarm is not None),
                default=None,
            ),
            engaged=bool(engaged),
            snoozable=any(member.config.snooze_duration > 0 for member in engaged),
        )


class AlarmClockGroupEntity(CoordinatorEntity[AlarmClockGroupCoordinator]):
    """Base class of the group entities: the group device and a unique ID."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AlarmClockGroupCoordinator, key: str) -> None:
        """Bind the entity to the coordinator and the group device."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Alarm Clocks & Wake-up Routines",
            model="Alarm Clock Group",
            entry_type=DeviceEntryType.SERVICE,
        )

    @callback
    def add_to_platform_start(
        self,
        hass: HomeAssistant,
        platform: EntityPlatform,
        parallel_updates: Any,
    ) -> None:
        """Derive the entity ID from the English key, as for the clocks."""
        async_assign_entity_id(
            self,
            hass,
            platform,
            self.coordinator.config_entry.title,
            self._key,
        )
        super().add_to_platform_start(hass, platform, parallel_updates)
