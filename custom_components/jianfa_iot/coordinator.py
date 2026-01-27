"""Data coordinator for C&D Iot integration."""

import logging
from datetime import timedelta
from typing import Any, Dict, Optional, Set

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import QUERY_INTERVAL
from .exceptions import BatchQueryError, DeviceError, AuthenticationError
from .http_client import HttpClient
from .models import DeviceList, Room

_LOGGER = logging.getLogger(__name__)


class JianfaIotDataCoordinator(DataUpdateCoordinator[DeviceList]):
    """Jianfa IoT Data Update Coordinator."""

    def __init__(
        self,
        hass: HomeAssistant,
        http_client: HttpClient,
        room: Room,
        update_interval: int = QUERY_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Jianfa IoT",
            update_interval=timedelta(seconds=update_interval),
            always_update=True,  # 确保总是通知监听者
        )

        self._http_client = http_client
        self._room = room  # Store room config
        self._device_ids: Set[str] = set()  # No default device ID
        self._device_info: Dict[str, Dict[str, str]] = {}  # Store device info
        self._pending_updates: Dict[str, Any] = {}  # Track pending commands by property

        # For storing the last known value separately from the data
        self._previous_data: Dict[str, Any] = {}

    @callback
    def async_get_device_state(self, device_id: str) -> Dict[str, Any]:
        """Get the current state of a specific device."""
        if self.data is None:
            return {}

        for device in self.data.devices:
            if device.device_id == device_id:
                if device.state:
                    return {
                        "PowerSwitch": device.state.power_switch,
                        "TemperatureSet": device.state.temperature_set,
                        "WorkMode": device.state.work_mode,
                        "Windspeed": device.state.wind_speed,
                    }
                return {}
        return {}

    @callback
    def async_get_device_property(self, device_id: str, property_code: str) -> Any:
        """Get a specific property for a device."""
        device_state = self.async_get_device_state(device_id)
        return device_state.get(property_code)

    @callback
    def async_get_previous_property(self, device_id: str, property_code: str) -> Any:
        """Get the previous value of a property."""
        device_key = f"{device_id}_{property_code}"
        return self._previous_data.get(device_key)

    async def _async_update_data(self) -> DeviceList:
        """Fetch data from API endpoint."""
        try:
            # Store current data as previous
            if self.data:
                for device in self.data.devices:
                    device_id = device.device_id
                    if device.state:
                        for property_code in [
                            "PowerSwitch",
                            "TemperatureSet",
                            "WorkMode",
                            "Windspeed",
                        ]:
                            value = None
                            if property_code == "PowerSwitch":
                                value = device.state.power_switch
                            elif property_code == "TemperatureSet":
                                value = device.state.temperature_set
                            elif property_code == "WorkMode":
                                value = device.state.work_mode
                            elif property_code == "Windspeed":
                                value = device.state.wind_speed

                            if value is not None:
                                device_key = f"{device_id}_{property_code}"
                                self._previous_data[device_key] = value

            # Fetch new data using room config
            _LOGGER.debug("Fetching device data...")
            response = await self._http_client.get_device_list(self._room)

            # 添加日志记录获取到的数据
            if response and hasattr(response, "devices") and response.devices:
                _LOGGER.debug("Successfully fetched %d devices", len(response.devices))

                # 遍历并记录每个设备的状态，便于调试
                for device in response.devices:
                    if device.device_id in self._device_ids:
                        if device.state:
                            _LOGGER.debug(
                                "设备 %s (注册设备) 状态: %s",
                                device.device_id,
                                {
                                    "PowerSwitch": device.state.power_switch,
                                    "TemperatureSet": (
                                        device.state.temperature_set
                                        if hasattr(device.state, "temperature_set")
                                        else None
                                    ),
                                    "WorkMode": (
                                        device.state.work_mode
                                        if hasattr(device.state, "work_mode")
                                        else None
                                    ),
                                    "Windspeed": (
                                        device.state.wind_speed
                                        if hasattr(device.state, "wind_speed")
                                        else None
                                    ),
                                },
                            )
                        else:
                            _LOGGER.debug(
                                "设备 %s (注册设备) 没有状态数据", device.device_id
                            )
            elif not response:
                _LOGGER.warning("API返回空响应")
            elif not hasattr(response, "devices"):
                _LOGGER.warning("API响应缺少devices属性")
            elif not response.devices:
                _LOGGER.warning("API响应中devices列表为空")

            return response

        except AuthenticationError as error:
            _LOGGER.error("鉴权失败，触发重新登录: %s", error)
            # 触发标准 Reauth 流（在 setup 阶段会引导用户重新登录）
            raise ConfigEntryAuthFailed from error
        except BatchQueryError as error:
            _LOGGER.error("获取设备数据失败: %s", error)
            raise UpdateFailed(f"Error communicating with API: {error}")

    async def async_send_command(
        self, device_id: str, property_code: str, value: Any
    ) -> bool:
        """Send command to device and update state."""
        pending_key = f"{device_id}_{property_code}"

        if device_id not in self._device_ids:
            _LOGGER.error("设备 %s 未注册到协调器", device_id)
            return False

        if device_id not in self._device_info:
            _LOGGER.error("设备 %s 信息不完整", device_id)
            return False

        device_info = self._device_info[device_id]

        try:
            _LOGGER.debug(
                "Sending command for property %s with value %s to device %s",
                property_code,
                value,
                device_id,
            )

            # Record pending update
            self._pending_updates[pending_key] = value

            # Send command with room config and device-specific information
            success = await self._http_client.send_command(
                room=self._room,
                property_code=property_code,
                value=value,
                device_id=device_id,
                device_name=device_info.get("device_name", ""),
                product_id=device_info.get("product_id", ""),
            )

            if success:
                # Trigger an immediate data update to refresh states
                await self.async_request_refresh()

                _LOGGER.debug(
                    "Successfully sent command for property %s to %s for device %s",
                    property_code,
                    value,
                    device_id,
                )
                return True

            return False
        except DeviceError as error:
            _LOGGER.error(
                "Failed to send command for property %s with value %s: %s",
                property_code,
                value,
                error,
            )
            return False
        finally:
            # Clear the pending update regardless of outcome
            if pending_key in self._pending_updates:
                del self._pending_updates[pending_key]

    def register_device(
        self, device_id: str, device_name: str = "", product_id: str = ""
    ) -> None:
        """Register a device to be included in updates."""
        self._device_ids.add(device_id)

        # Store device info for later use in commands
        self._device_info[device_id] = {
            "device_name": device_name,
            "product_id": product_id,
        }

        _LOGGER.debug(
            "Registered device: %s (%s) to coordinator", device_id, device_name
        )

    def unregister_device(self, device_id: str) -> None:
        """Unregister a device from updates."""
        if device_id in self._device_ids:
            self._device_ids.remove(device_id)

        if device_id in self._device_info:
            del self._device_info[device_id]

        # Clean up previous data for this device
        keys_to_remove = []
        for key in self._previous_data:
            if key.startswith(f"{device_id}_"):
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self._previous_data[key]

    @callback
    def get_current_data(self) -> Optional[DeviceList]:
        """Return the current data."""
        return self.data

    def is_device_property_pending(self, device_id: str, property_code: str) -> bool:
        """Check if a device property has a pending update."""
        pending_key = f"{device_id}_{property_code}"
        return pending_key in self._pending_updates

    def get_pending_value(self, device_id: str, property_code: str) -> Any:
        """Get the pending value for a property, if any."""
        pending_key = f"{device_id}_{property_code}"
        return self._pending_updates.get(pending_key)

    async def async_get_remote_state(self, device_id: str, property_code: str) -> Any:
        """获取设备的远程状态，专门用于验证本地状态与远程状态是否一致。

        Args:
            device_id: 设备ID
            property_code: 要获取的属性代码

        Returns:
            当前属性的远程状态值，如果无法获取则返回None

        Raises:
            DeviceError: 如果无法获取设备状态
        """
        try:
            pending_key = f"{device_id}_{property_code}"

            # 如果有待处理的更新，优先返回本地状态
            if pending_key in self._pending_updates:
                _LOGGER.debug(
                    "Using pending update value for %s: %s (command in progress)",
                    property_code,
                    self._pending_updates[pending_key],
                )
                return self._pending_updates[pending_key]

            # Force refresh data
            await self.async_refresh()

            # Return the property value from refreshed data
            return self.async_get_device_property(device_id, property_code)

        except Exception as error:
            _LOGGER.error("Failed to get remote state for %s: %s", property_code, error)
            raise DeviceError(f"Failed to get remote state: {error}") from error

    async def async_force_refresh(self) -> None:
        """Force a refresh and immediately notify listeners."""
        _LOGGER.debug("强制刷新数据并立即通知监听者")
        await self.async_refresh()
        # 确保即使数据没有变化，也会通知监听者
        self.async_update_listeners()
