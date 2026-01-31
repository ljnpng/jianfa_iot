"""Data fetcher for C&D Iot integration.

Centralized data fetching service that polls the API once and distributes
device data to individual device coordinators.
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed

from .const import QUERY_INTERVAL
from .exceptions import AuthenticationError, BatchQueryError
from .http_client import HttpClient
from .models import DeviceList, Room

if TYPE_CHECKING:
    from .coordinator import DeviceCoordinator

_LOGGER = logging.getLogger(__name__)


class DataFetcher:
    """Centralized data fetcher that polls API and distributes to coordinators.

    This class is responsible for:
    - Polling the device list API at regular intervals
    - Distributing device data to registered coordinators
    - Handling API errors without affecting individual coordinators
    """

    def __init__(
        self,
        hass: HomeAssistant,
        http_client: HttpClient,
        room: Room,
        update_interval: int = QUERY_INTERVAL,
    ) -> None:
        """Initialize the data fetcher."""
        self._hass = hass
        self._http_client = http_client
        self._room = room
        self._update_interval = update_interval

        # Registered coordinators by device_id
        self._coordinators: dict[str, "DeviceCoordinator"] = {}

        # Polling task
        self._polling_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

        # Last fetched data for initial coordinator setup
        self._last_device_list: DeviceList | None = None

    def register_coordinator(
        self,
        device_id: str,
        coordinator: "DeviceCoordinator",
    ) -> None:
        """Register a coordinator to receive updates for a device."""
        self._coordinators[device_id] = coordinator
        _LOGGER.debug("Registered coordinator for device %s", device_id)

        # If we have cached data, send it immediately
        if self._last_device_list:
            for device in self._last_device_list.devices:
                if device.device_id == device_id:
                    self._hass.async_create_task(
                        coordinator.async_update_from_fetcher(device)
                    )
                    break

    def unregister_coordinator(self, device_id: str) -> None:
        """Unregister a coordinator."""
        if device_id in self._coordinators:
            del self._coordinators[device_id]
            _LOGGER.debug("Unregistered coordinator for device %s", device_id)

    async def async_start(self) -> None:
        """Start the polling loop."""
        if self._polling_task is not None and not self._polling_task.done():
            _LOGGER.warning("Polling task already running")
            return

        self._stop_event.clear()
        self._polling_task = asyncio.create_task(self._polling_loop())
        _LOGGER.info("Data fetcher started with %ds interval", self._update_interval)

    async def async_stop(self) -> None:
        """Stop the polling loop."""
        self._stop_event.set()

        if self._polling_task is not None:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
            self._polling_task = None

        _LOGGER.info("Data fetcher stopped")

    async def async_fetch_once(self) -> DeviceList | None:
        """Fetch device list once (for initial setup)."""
        try:
            device_list = await self._http_client.get_device_list(self._room)
            self._last_device_list = device_list
            return device_list
        except AuthenticationError as error:
            _LOGGER.error("Authentication failed: %s", error)
            raise ConfigEntryAuthFailed from error
        except Exception as error:
            _LOGGER.error("Failed to fetch device list: %s", error)
            return None

    async def _polling_loop(self) -> None:
        """Main polling loop."""
        while not self._stop_event.is_set():
            try:
                await self._fetch_and_distribute()
            except ConfigEntryAuthFailed:
                _LOGGER.error("Authentication failed, stopping data fetcher")
                break
            except Exception as error:
                _LOGGER.error("Unexpected error in polling loop: %s", error)

            # Wait for next interval or stop event
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._update_interval,
                )
                break
            except asyncio.TimeoutError:
                pass

    async def _fetch_and_distribute(self) -> None:
        """Fetch data from API and distribute to coordinators."""
        try:
            device_list = await self._http_client.get_device_list(self._room)
            self._last_device_list = device_list

            if not device_list or not device_list.devices:
                _LOGGER.warning("Empty device list from API")
                return

            _LOGGER.debug(
                "Fetched %d devices, distributing to %d coordinators",
                len(device_list.devices),
                len(self._coordinators),
            )

            # Distribute to coordinators
            for device in device_list.devices:
                coordinator = self._coordinators.get(device.device_id)
                if coordinator:
                    try:
                        await coordinator.async_update_from_fetcher(device)
                    except Exception as error:
                        _LOGGER.error(
                            "Error updating coordinator for device %s: %s",
                            device.device_id,
                            error,
                        )

            # Check for devices that disappeared from API
            api_device_ids = {d.device_id for d in device_list.devices}
            for device_id, coordinator in self._coordinators.items():
                if device_id not in api_device_ids:
                    _LOGGER.warning(
                        "Device %s not found in API response, marking unavailable",
                        device_id,
                    )
                    try:
                        await coordinator.async_set_unavailable()
                    except Exception as error:
                        _LOGGER.error(
                            "Error marking device %s unavailable: %s",
                            device_id,
                            error,
                        )

        except AuthenticationError as error:
            _LOGGER.error("Authentication failed during fetch: %s", error)
            raise ConfigEntryAuthFailed from error
        except BatchQueryError as error:
            _LOGGER.error("Batch query error: %s", error)
            for device_id, coordinator in self._coordinators.items():
                try:
                    await coordinator.async_set_update_error(error)
                except Exception as coord_error:
                    _LOGGER.error(
                        "Error notifying coordinator %s of error: %s",
                        device_id,
                        coord_error,
                    )

    @property
    def last_device_list(self) -> DeviceList | None:
        """Return the last fetched device list."""
        return self._last_device_list
