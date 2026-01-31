"""Device coordinator for C&D Iot integration.

Each device has its own coordinator instance that manages:
- Device state from DataFetcher
- Verification state for optimistic updates
- Command sending with background verification
"""

import asyncio
import logging
from typing import Any, Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .http_client import HttpClient
from .models import Device, Room

_LOGGER = logging.getLogger(__name__)

# Verification status constants
VERIFICATION_PENDING = "pending"
VERIFICATION_CONFIRMED = "confirmed"
VERIFICATION_TIMEOUT = "timeout"


class DeviceCoordinator(DataUpdateCoordinator[Device]):
    """Per-device coordinator that receives data from DataFetcher.

    This coordinator does not poll the API directly. Instead, it receives
    device data from the centralized DataFetcher and manages verification
    state for optimistic updates.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        http_client: HttpClient,
        room: Room,
        device_id: str,
        device_name: str,
        product_id: str,
    ) -> None:
        """Initialize the device coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"Jianfa IoT {device_name}",
            # No update_interval - we receive data from DataFetcher
            update_interval=None,
        )

        self._hass = hass
        self._http_client = http_client
        self._room = room
        self._device_id = device_id
        self._device_name = device_name
        self._product_id = product_id

        # Verification state: {property_code: "pending" | "confirmed" | "timeout"}
        self._verification_status: dict[str, str] = {}

        # Verification queue and task
        self._verification_queue: asyncio.Queue = asyncio.Queue()
        self._verification_task: asyncio.Task | None = None

        # Availability flag
        self._available = True

    @property
    def device_id(self) -> str:
        """Return the device ID."""
        return self._device_id

    @property
    def available(self) -> bool:
        """Return if the device is available."""
        return self._available

    async def async_update_from_fetcher(self, device: Device) -> None:
        """Receive device data from DataFetcher.

        This is called by DataFetcher when new data is available.
        """
        self._available = True
        self.async_set_updated_data(device)
        _LOGGER.debug(
            "Device %s received update from fetcher, power=%s",
            self._device_id,
            device.state.power_switch if device.state else "unknown",
        )

    async def async_set_unavailable(self) -> None:
        """Mark the device as unavailable."""
        self._available = False
        self.async_update_listeners()
        _LOGGER.warning("Device %s marked as unavailable", self._device_id)

    async def async_set_update_error(self, error: Exception) -> None:
        """Handle update error from DataFetcher."""
        _LOGGER.error("Device %s update error: %s", self._device_id, error)
        # Don't mark unavailable on transient errors, just log

    @callback
    def async_get_device_state(self) -> dict[str, Any]:
        """Get the current state of the device."""
        if self.data is None or self.data.state is None:
            return {}

        return {
            "PowerSwitch": self.data.state.power_switch,
            "TemperatureSet": self.data.state.temperature_set,
            "WorkMode": self.data.state.work_mode,
            "Windspeed": self.data.state.wind_speed,
        }

    @callback
    def async_get_device_property(self, property_code: str) -> Any:
        """Get a specific property for the device."""
        state = self.async_get_device_state()
        return state.get(property_code)

    def get_verification_status(self, property_code: str) -> str | None:
        """Get verification status for a property.

        Returns:
            "pending" - Command sent, verification in progress (ignore updates)
            "confirmed" - Verification successful (accept updates)
            "timeout" - Verification timed out (accept updates)
            None - No pending verification (accept updates)
        """
        return self._verification_status.get(property_code)

    def set_verification_pending(self, property_code: str) -> None:
        """Set verification status to pending for a property."""
        self._verification_status[property_code] = VERIFICATION_PENDING
        _LOGGER.debug(
            "Device %s property %s verification set to pending",
            self._device_id,
            property_code,
        )

    def clear_verification_status(self, property_code: str) -> None:
        """Clear verification status for a property."""
        if property_code in self._verification_status:
            del self._verification_status[property_code]

    async def async_send_command_with_verify(
        self,
        property_code: str,
        value: Any,
    ) -> bool:
        """Send command and start background verification.

        Args:
            property_code: Property to control
            value: Value to set

        Returns:
            True if command was sent successfully
        """
        try:
            # Set pending status BEFORE sending command
            self.set_verification_pending(property_code)

            # Send the command
            success = await self._http_client.send_command(
                room=self._room,
                property_code=property_code,
                value=value,
                device_id=self._device_id,
                device_name=self._device_name,
                product_id=self._product_id,
            )

            if success:
                # Queue verification task
                await self._verification_queue.put((property_code, value))

                # Ensure queue processor is running
                if self._verification_task is None or self._verification_task.done():
                    self._verification_task = asyncio.create_task(
                        self._verification_queue_processor()
                    )

                _LOGGER.debug(
                    "Device %s command sent for %s=%s, verification queued",
                    self._device_id,
                    property_code,
                    value,
                )
                return True

            # Command failed, clear pending status
            self.clear_verification_status(property_code)
            return False

        except Exception as error:
            _LOGGER.error(
                "Device %s failed to send command %s=%s: %s",
                self._device_id,
                property_code,
                value,
                error,
            )
            self.clear_verification_status(property_code)
            return False

    async def _verification_queue_processor(self) -> None:
        """Background task: Process verification queue sequentially."""
        _LOGGER.debug("Device %s verification processor started", self._device_id)

        while True:
            try:
                property_code, expected_value = await asyncio.wait_for(
                    self._verification_queue.get(),
                    timeout=60.0,  # Exit if idle for 60 seconds
                )
            except asyncio.TimeoutError:
                _LOGGER.debug(
                    "Device %s verification processor idle, exiting",
                    self._device_id,
                )
                break

            await self._verify_with_exponential_backoff(property_code, expected_value)
            self._verification_queue.task_done()

    async def _verify_with_exponential_backoff(
        self,
        property_code: str,
        expected_value: Any,
    ) -> None:
        """Verify device state change using exponential backoff polling.

        Polls at intervals: 2s, 4s, 8s, 16s (total ~30s timeout)
        """
        delays = [2, 4, 8, 16]

        _LOGGER.debug(
            "Device %s starting verification for %s: expected %s",
            self._device_id,
            property_code,
            expected_value,
        )

        for delay in delays:
            await asyncio.sleep(delay)

            # Check current state from coordinator data
            actual_value = self.async_get_device_property(property_code)

            if actual_value == expected_value:
                self._verification_status[property_code] = VERIFICATION_CONFIRMED
                _LOGGER.info(
                    "Device %s verification confirmed: %s=%s",
                    self._device_id,
                    property_code,
                    expected_value,
                )
                # Notify listeners that verification is complete
                self.async_update_listeners()
                return

            _LOGGER.debug(
                "Device %s verification pending: %s expected %s, got %s",
                self._device_id,
                property_code,
                expected_value,
                actual_value,
            )

        # Timeout
        self._verification_status[property_code] = VERIFICATION_TIMEOUT
        _LOGGER.warning(
            "Device %s verification timeout: %s=%s not confirmed",
            self._device_id,
            property_code,
            expected_value,
        )
        # Notify listeners that verification timed out
        self.async_update_listeners()

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
        if self._verification_task is not None:
            self._verification_task.cancel()
            try:
                await self._verification_task
            except asyncio.CancelledError:
                pass
            self._verification_task = None


# Keep old name as alias for backwards compatibility during migration
JianfaIotDataCoordinator = DeviceCoordinator
