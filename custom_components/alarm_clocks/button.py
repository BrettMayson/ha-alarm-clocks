"""Buttons for snooze and dismiss, of alarm clocks and of groups."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import KIND_GROUP
from .coordinator import AlarmClockConfigEntry, AlarmClockCoordinator
from .entity import AlarmClockEntity
from .group import AlarmClockGroupCoordinator, AlarmClockGroupEntity, entry_kind


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AlarmClockConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the buttons."""
    if entry_kind(entry) == KIND_GROUP:
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

