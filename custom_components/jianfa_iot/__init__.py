"""The C&D Iot integration."""
from dataclasses import dataclass
from typing import Any

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import JianfaIotDataCoordinator
from .http_client import HttpClient
from .auth_client import AuthClient
from .models import Device, Room

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["light", "climate"]

# Type alias for ConfigEntry with runtime data
type JianfaIotConfigEntry = ConfigEntry[JianfaIotData]

@dataclass
class JianfaIotData:
    """Runtime data for the integration."""
    http_client: HttpClient
    coordinator: JianfaIotDataCoordinator
    room_config: Room
    devices: list[Device]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the C&D Iot component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JianfaIotConfigEntry,
) -> bool:
    """Set up C&D Iot from a config entry."""
    try:
        _LOGGER.debug("Setting up C&D Iot integration")

        # Get auth data from entry
        auth_data = entry.data.get("auth", {})
        phone = auth_data.get("phone")
        access_token = auth_data.get("access_token")

        if not phone or not access_token:
            _LOGGER.error("Missing auth data in config entry")
            raise ConfigEntryNotReady("Missing auth data")

        # Create HTTP client
        http_client = HttpClient(hass, x_token=access_token, phone=phone)

        # Get room configuration
        _LOGGER.debug("Fetching room configuration...")
        room_list = await http_client.get_room_list()

        if not room_list.rooms:
            _LOGGER.error("No rooms found for user")
            raise ConfigEntryNotReady("No rooms found")

        room_config = room_list.first_room
        _LOGGER.info("Using room: %s", room_config.room_name)

        # Get device list
        try:
            device_list = await http_client.get_device_list(room_config)
            devices = device_list.devices if device_list else []
        except Exception as error:
            _LOGGER.warning("Error getting device list, will retry: %s", error)
            devices = []

        # Log devices
        for device in devices:
            _LOGGER.info(
                "Device: id=%s, name=%s, product_id=%s",
                device.device_id,
                device.device_name,
                device.product_id,
            )

        # Create coordinator
        coordinator = JianfaIotDataCoordinator(hass, http_client, room_config)

        # Register devices
        for device in devices:
            coordinator.register_device(
                device_id=device.device_id,
                device_name=device.device_name,
                product_id=device.product_id,
            )

        # Refresh coordinator
        await coordinator.async_config_entry_first_refresh()

        # Store in runtime_data (NEW HA 2024 pattern)
        entry.runtime_data = JianfaIotData(
            http_client=http_client,
            coordinator=coordinator,
            room_config=room_config,
            devices=devices,
        )

        # Setup platforms
        _LOGGER.debug("Setting up platforms: %s", PLATFORMS)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        return True

    except Exception as error:
        _LOGGER.error("Failed to set up C&D Iot integration: %s", error)
        raise ConfigEntryNotReady from error


async def async_unload_entry(
    hass: HomeAssistant,
    entry: JianfaIotConfigEntry,
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )

    # runtime_data is automatically cleaned up by HA
    return unload_ok
