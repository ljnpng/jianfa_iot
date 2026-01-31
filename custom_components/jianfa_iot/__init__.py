"""The C&D Iot integration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import DeviceCoordinator
from .data_fetcher import DataFetcher
from .http_client import HttpClient
from .auth_client import AuthClient
from .models import Device, Room

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["light", "climate"]


@dataclass
class JianfaIotData:
    """Runtime data for the integration."""
    http_client: HttpClient
    data_fetcher: DataFetcher
    coordinators: dict[str, DeviceCoordinator]
    room_config: Room
    devices: list[Device]


if TYPE_CHECKING:
    # Type alias for ConfigEntry with runtime data
    JianfaIotConfigEntry = ConfigEntry[JianfaIotData]
else:
    JianfaIotConfigEntry = ConfigEntry


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

        # Create DataFetcher
        data_fetcher = DataFetcher(hass, http_client, room_config)

        # Fetch initial device list
        device_list = await data_fetcher.async_fetch_once()
        devices = device_list.devices if device_list else []

        if not devices:
            _LOGGER.warning("No devices found, will retry on next poll")

        # Log devices
        for device in devices:
            _LOGGER.info(
                "Device: id=%s, name=%s, product_id=%s",
                device.device_id,
                device.device_name,
                device.product_id,
            )

        # Create per-device coordinators
        coordinators: dict[str, DeviceCoordinator] = {}
        for device in devices:
            coordinator = DeviceCoordinator(
                hass=hass,
                http_client=http_client,
                room=room_config,
                device_id=device.device_id,
                device_name=device.device_name,
                product_id=device.product_id,
            )
            coordinators[device.device_id] = coordinator

            # Register coordinator with data fetcher
            data_fetcher.register_coordinator(device.device_id, coordinator)

            _LOGGER.debug(
                "Created coordinator for device: %s (%s)",
                device.device_id,
                device.device_name,
            )

        # Start data fetcher polling
        await data_fetcher.async_start()

        # Store in runtime_data (NEW HA 2024 pattern)
        entry.runtime_data = JianfaIotData(
            http_client=http_client,
            data_fetcher=data_fetcher,
            coordinators=coordinators,
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
    # Stop data fetcher
    if entry.runtime_data and entry.runtime_data.data_fetcher:
        await entry.runtime_data.data_fetcher.async_stop()

    # Shutdown coordinators
    if entry.runtime_data and entry.runtime_data.coordinators:
        for coordinator in entry.runtime_data.coordinators.values():
            await coordinator.async_shutdown()

    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )

    return unload_ok
