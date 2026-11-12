"""Buttons for snooze and dismiss, and the group hub's create group button."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_KIND, DOMAIN, KIND_GROUP, KIND_HUB
from .coordinator import AlarmClockConfigEntry, AlarmClockCoordinator
from .entity import AlarmClockEntity, async_assign_entity_id
from .group import AlarmClockGroupCoordinator, AlarmClockGroupEntity, entry_kind

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import EntityPlatform


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AlarmClockConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the buttons."""
    kind = entry_kind(entry)
    if kind == KIND_HUB:
        async_add_entities([AlarmClockCreateGroupButton(entry)])
        return

    if kind == KIND_GROUP:
        group: AlarmClockGroupCoordinator = entry.runtime_data
        async_add_entities(
            [
                AlarmClockGroupSnoozeButton(group),
                AlarmClockGroupDismissButton(group),
            ]
        )
        return

    coordinator = entry.runtime_data
    async_add_entities(
        [
            AlarmClockSnoozeButton(coordinator),
            AlarmClockDismissButton(coordinator),
        ]
    )


class AlarmClockSnoozeButton(AlarmClockEntity, ButtonEntity):
    """Triggers a snooze."""

    _attr_icon = "mdi:alarm-snooze"

    def __init__(self, coordinator: AlarmClockCoordinator) -> None:
        """Set up the button."""
        super().__init__(coordinator, "snooze")

    @property
    def available(self) -> bool:
        """Unavailable while snoozing is switched off."""
        return super().available and self.coordinator.config.snooze_duration > 0

    async def async_press(self) -> None:
        """Trigger a snooze."""
        await self.coordinator.async_snooze()


class AlarmClockDismissButton(AlarmClockEntity, ButtonEntity):
    """Ends ringing or snoozing."""

    _attr_icon = "mdi:alarm-off"

    def __init__(self, coordinator: AlarmClockCoordinator) -> None:
        """Set up the button."""
        super().__init__(coordinator, "dismiss")

    async def async_press(self) -> None:
        """Trigger a dismiss."""
        await self.coordinator.async_dismiss()


class AlarmClockGroupSnoozeButton(AlarmClockGroupEntity, ButtonEntity):
    """Snoozes every member that is ringing; available while one is engaged."""

    _attr_icon = "mdi:alarm-snooze"

    def __init__(self, coordinator: AlarmClockGroupCoordinator) -> None:
        """Set up the button."""
        super().__init__(coordinator, "snooze")

    @property
    def available(self) -> bool:
        """Available while a member can be snoozed."""
        return (
            super().available
            and self.coordinator.data.engaged
            and self.coordinator.data.snoozable
        )

    async def async_press(self) -> None:
        """Snooze the members."""
        await self.coordinator.async_snooze()


class AlarmClockGroupDismissButton(AlarmClockGroupEntity, ButtonEntity):
    """Dismisses every member that is ringing or snoozing."""

    _attr_icon = "mdi:alarm-off"

    def __init__(self, coordinator: AlarmClockGroupCoordinator) -> None:
        """Set up the button."""
        super().__init__(coordinator, "dismiss")

    @property
    def available(self) -> bool:
        """Available while a member is ringing or snoozing."""
        return super().available and self.coordinator.data.engaged

    async def async_press(self) -> None:
        """Dismiss the members."""
        await self.coordinator.async_dismiss()


class AlarmClockCreateGroupButton(ButtonEntity):
    """Creates an empty group on the group hub; its members are set in its options."""

    _attr_has_entity_name = True
    _attr_translation_key = "create_group"
    _attr_icon = "mdi:alarm-multiple"

    def __init__(self, entry: AlarmClockConfigEntry) -> None:
        """Bind the button to the hub device."""
        self._key = "create_group"
        self._title = entry.title
        self._attr_unique_id = f"{entry.entry_id}_{self._key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Alarm Clocks & Wake-up Routines",
            model="Alarm Clock Group Hub",
            entry_type=DeviceEntryType.SERVICE,
        )

    @callback
    def add_to_platform_start(
        self,
        hass: HomeAssistant,
        platform: EntityPlatform,
        parallel_updates: Any,
    ) -> None:
        """Derive the entity ID from the English key, as for the other entities."""
        async_assign_entity_id(self, hass, platform, self._title, self._key)
        super().add_to_platform_start(hass, platform, parallel_updates)

    async def async_press(self) -> None:
        """Start the flow that creates a new group."""
        await self.hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data={CONF_KIND: KIND_GROUP},
        )

