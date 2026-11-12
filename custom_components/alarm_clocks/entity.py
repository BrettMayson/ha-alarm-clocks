"""Shared base class for all alarm clock entities."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity, async_generate_entity_id
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AlarmClockCoordinator

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import EntityPlatform

# Nicer identifiers for the entity ID than the internal key.
OBJECT_ID_OVERRIDES: dict[str, str] = {
    "day_mon": "monday",
    "day_tue": "tuesday",
    "day_wed": "wednesday",
    "day_thu": "thursday",
    "day_fri": "friday",
    "day_sat": "saturday",
    "day_sun": "sunday",
}


@callback
def async_assign_entity_id(
    entity: Entity,
    hass: HomeAssistant,
    platform: EntityPlatform,
    title: str,
    key: str,
) -> None:
    """Derive the entity ID from the English key, not the translated name."""
    if entity.entity_id is None:
        suffix = OBJECT_ID_OVERRIDES.get(key, key)
        entity.entity_id = async_generate_entity_id(
            f"{platform.domain}.{{}}", f"{title} {suffix}", hass=hass
        )


class AlarmClockEntity(CoordinatorEntity[AlarmClockCoordinator]):
    """Base class providing device assignment and a unique ID."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AlarmClockCoordinator, key: str) -> None:
        """Bind the entity to the coordinator and the alarm clock device."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Alarm Clocks & Wake-up Routines",
            model="Alarm Clock",
            entry_type=DeviceEntryType.SERVICE,
        )

    @callback
    def add_to_platform_start(
        self,
        hass: HomeAssistant,
        platform: EntityPlatform,
        parallel_updates: Any,
    ) -> None:
        """Assign the entity ID before Home Assistant derives one itself.

        Without this step Home Assistant builds the entity ID from the
        translated display name, which would yield
        ``switch.alarm_1_aktiviert`` on a German instance and
        ``switch.alarm_1_enabled`` on an English one. The ID therefore comes
        from the internal key, which is always English, while the display
        name stays translated.
        """
        async_assign_entity_id(
            self,
            hass,
            platform,
            self.coordinator.config_entry.title,
            self._key,
        )
        super().add_to_platform_start(hass, platform, parallel_updates)


    @property
    def config(self):
        """Shorthand for the alarm clock configuration."""
        return self.coordinator.config
