"""Support for HISENSE HTTP controlled lights."""

import logging
from typing import Any, cast

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MANUFACTURER,
    MODEL_LIGHT,
)
from .coordinator import JianfaIotDataCoordinator
from .models import Room
from . import JianfaIotConfigEntry

_LOGGER = logging.getLogger(__name__)

# 灯属性代码
PROPERTY_POWER = "PowerSwitch"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JianfaIotConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the HISENSE lights."""
    _LOGGER.debug("Setting up HISENSE lights")

    # Get data from runtime_data
    data = entry.runtime_data
    devices = data.devices
    coordinator = data.coordinator
    room = data.room_config

    _LOGGER.info("Processing devices for light setup")

    entities = []
    light_devices = [device for device in devices if device.is_light]
    _LOGGER.info("Found %d light devices", len(light_devices))

    for device in light_devices:
        try:
            _LOGGER.info(
                "Creating light entity: id=%s, name=%s",
                device.device_id,
                device.device_name,
            )

            light = HisenseLight(
                coordinator,
                room,
                device.device_name,
                device.device_id,
                device.device_name,
                device.suit_name,
            )
            entities.append(light)

        except Exception as error:
            _LOGGER.error(
                "Failed to set up light for device %s: %s",
                device.device_id,
                error,
            )
            continue

    if entities:
        _LOGGER.info("Adding %d light entities", len(entities))
        async_add_entities(entities, True)
    else:
        _LOGGER.warning("No light entities found")


class HisenseLight(CoordinatorEntity[JianfaIotDataCoordinator], LightEntity):
    """Representation of a HISENSE light."""

    def __init__(
        self,
        coordinator: JianfaIotDataCoordinator,
        room: Room,
        name: str,
        device_id: str,
        device_name: str,
        room_name: str = "",
    ) -> None:
        """Initialize the light."""
        super().__init__(coordinator)

        self._device_id = device_id
        self._device_name = device_name
        self._room_name = room_name
        self._room = room  # Store room config

        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{device_id}"
        safe_device_id = (
            device_id.replace("-", "_").replace(".", "_").replace(":", "_").lower()
        )
        self.entity_id = f"{DOMAIN}.{safe_device_id}"

        # Set supported color modes
        self._attr_supported_color_modes = {ColorMode.ONOFF}
        self._attr_color_mode = ColorMode.ONOFF

        # 根据灯具名称设置合适的图标
        self._set_icon()

        # 设备信息
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._attr_unique_id)},
            "name": name,
            "manufacturer": MANUFACTURER,
            "model": MODEL_LIGHT,
            "suggested_area": room_name if room_name else None,
        }

        # 设置初始状态
        self._update_state_from_coordinator()

    def _update_state_from_coordinator(self) -> None:
        """Update state from coordinator data."""
        coordinator = cast(JianfaIotDataCoordinator, self.coordinator)

        if coordinator.data is None:
            _LOGGER.warning("Coordinator data is empty")
            return

        # Get device state
        state = coordinator.async_get_device_property(self._device_id, PROPERTY_POWER)

        if state is not None:
            self._attr_is_on = bool(state)
            _LOGGER.debug(
                "Updated light %s state to: %s",
                self._device_id,
                "ON" if self._attr_is_on else "OFF",
            )
        else:
            _LOGGER.warning("Could not get power state for light %s", self._device_id)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        # Debounce: if already on locally, skip
        if self._attr_is_on:
            _LOGGER.debug(
                "Light %s is already ON locally, skipping",
                self._device_id,
            )
            return

        coordinator = cast(JianfaIotDataCoordinator, self.coordinator)

        # Optimistic update - update UI immediately
        _LOGGER.debug("Turning on light %s", self._device_id)
        self._attr_is_on = True
        self.async_write_ha_state()

        # Send command with background verification
        await coordinator.async_send_command_with_verify(
            self._device_id, PROPERTY_POWER, 1
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        # Debounce: if already off locally, skip
        if not self._attr_is_on:
            _LOGGER.debug(
                "Light %s is already OFF locally, skipping",
                self._device_id,
            )
            return

        coordinator = cast(JianfaIotDataCoordinator, self.coordinator)

        # Optimistic update - update UI immediately
        _LOGGER.debug("Turning off light %s", self._device_id)
        self._attr_is_on = False
        self.async_write_ha_state()

        # Send command with background verification
        await coordinator.async_send_command_with_verify(
            self._device_id, PROPERTY_POWER, 0
        )

    async def async_update(self) -> None:
        """Update the entity."""
        _LOGGER.debug("Manual update for light %s", self._device_id)

        coordinator = cast(JianfaIotDataCoordinator, self.coordinator)

        # Force refresh and update
        if hasattr(coordinator, "async_force_refresh"):
            await coordinator.async_force_refresh()
        else:
            await coordinator.async_request_refresh()

        self._update_state_from_coordinator()
        self.async_write_ha_state()

    def _set_icon(self) -> None:
        """Set the icon based on device name."""
        device_name_lower = self._device_name.lower() if self._device_name else ""

        if (
            "筒灯" in device_name_lower
            or "射灯" in device_name_lower
            or "spotlight" in device_name_lower
        ):
            self._attr_icon = "mdi:spotlight-beam"
        elif "灯带" in device_name_lower or "strip" in device_name_lower:
            self._attr_icon = "mdi:led-strip-variant"
        elif "吊灯" in device_name_lower or "pendant" in device_name_lower:
            self._attr_icon = "mdi:ceiling-light"
        elif "壁灯" in device_name_lower or "wall" in device_name_lower:
            self._attr_icon = "mdi:wall-sconce-flat"
        elif "台灯" in device_name_lower or "lamp" in device_name_lower:
            self._attr_icon = "mdi:lamp"
        else:
            self._attr_icon = "mdi:lightbulb"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug(
            "Received coordinator update for light %s",
            self._device_id,
        )

        coordinator = cast(JianfaIotDataCoordinator, self.coordinator)

        # Check verification status before accepting update
        verification_status = coordinator.get_verification_status(
            self._device_id, PROPERTY_POWER
        )

        # If verification is still pending or hasn't started, ignore update
        if verification_status is None:
            _LOGGER.debug(
                "Skipping coordinator update for %s: verification not started",
                self._device_id,
            )
            return

        # If verification confirmed, accept the update
        if verification_status == "confirmed":
            _LOGGER.debug(
                "Accepting coordinator update for %s: verification confirmed",
                self._device_id,
            )
            old_state = self._attr_is_on
            self._update_state_from_coordinator()
            new_state = self._attr_is_on

            if old_state != new_state:
                _LOGGER.debug(
                    "Light %s state updated: %s -> %s",
                    self._device_id,
                    "ON" if old_state else "OFF",
                    "ON" if new_state else "OFF",
                )

            self.async_write_ha_state()
            return

        # If verification timed out, still update but log warning
        # (maintain optimistic state but eventually sync)
        _LOGGER.debug(
            "Accepting coordinator update for %s: verification timed out, syncing to actual state",
            self._device_id,
        )
        self._update_state_from_coordinator()
        self.async_write_ha_state()
