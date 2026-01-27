"""Support for HISENSE HTTP controlled lights."""

import logging
import time
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

# 命令后状态保护时间（秒）
STATE_PROTECTION_WINDOW = 10.0


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
        self._last_command_time = 0
        self._state_protection_window = STATE_PROTECTION_WINDOW

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
        # 如果在保护窗口内，跳过状态更新
        if time.time() - self._last_command_time < self._state_protection_window:
            _LOGGER.debug(
                "忽略协调器状态更新：设备 %s 处于命令保护窗口内 (%.2f 秒前发送了命令)",
                self._device_id,
                time.time() - self._last_command_time,
            )
            return

        coordinator = cast(JianfaIotDataCoordinator, self.coordinator)

        # 检查协调器数据完整性并记录日志
        if coordinator.data is None:
            _LOGGER.warning("从协调器获取数据失败: 协调器数据为空")
            return

        # 检查设备是否存在于协调器数据中
        device_found = False
        for device in coordinator.data.devices:
            if device.device_id == self._device_id:
                device_found = True
                if device.state is None:
                    _LOGGER.warning(
                        "设备 %s 存在于数据中但没有状态信息", self._device_id
                    )
                break

        if not device_found:
            _LOGGER.warning("设备 %s 不存在于协调器返回的数据中", self._device_id)

        # 获取设备状态
        state = coordinator.async_get_device_property(self._device_id, PROPERTY_POWER)

        if state is not None:
            old_state = self._attr_is_on
            self._attr_is_on = bool(state)

            if old_state != self._attr_is_on:
                _LOGGER.debug(
                    "已更新灯 %s 的状态: %s -> %s",
                    self._device_id,
                    "ON" if old_state else "OFF",
                    "ON" if self._attr_is_on else "OFF",
                )
            else:
                _LOGGER.debug(
                    "灯 %s 状态未变化: %s",
                    self._device_id,
                    "ON" if self._attr_is_on else "OFF",
                )
        else:
            _LOGGER.warning("无法获取灯 %s 的电源状态", self._device_id)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        try:
            _LOGGER.debug(
                "Turning on light %s - checking current state first", self._device_id
            )

            # 命令防抖：如果已经是开启状态，直接返回，避免不必要的检查
            if self._attr_is_on:
                _LOGGER.debug(
                    "Light %s is already ON locally, skipping operation",
                    self._device_id,
                )
                return

            coordinator = cast(JianfaIotDataCoordinator, self.coordinator)

            # 使用专门的方法获取当前远程状态
            current_remote_state = await coordinator.async_get_remote_state(
                self._device_id, PROPERTY_POWER
            )

            # 如果远程已经是开启状态，不做任何操作
            if bool(current_remote_state):
                _LOGGER.debug(
                    "Light %s is already ON remotely, updating local state only",
                    self._device_id,
                )
                # 确保本地状态与远程一致
                self._attr_is_on = True
                self.async_write_ha_state()
                return

            _LOGGER.debug("Sending ON command to light %s", self._device_id)

            # 立即更新本地状态，提高响应性
            self._attr_is_on = True
            # 记录命令发送时间，进入状态保护窗口
            self._last_command_time = time.time()
            self.async_write_ha_state()

            # 发送开灯命令
            success = await coordinator.async_send_command(
                self._device_id, PROPERTY_POWER, 1
            )

            if not success:
                _LOGGER.error("Failed to turn on light %s", self._device_id)
                # 对于失败的命令，我们仍然保持UI为"开启"状态，因为用户已看到灯已打开
                # 下一个正常的状态同步周期会自动纠正，如果需要的话

        except Exception as error:
            _LOGGER.error("Error turning on light %s: %s", self._device_id, error)
            # 出现异常时，我们也保持用户已经看到的状态，避免UI闪烁

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        try:
            _LOGGER.debug(
                "Turning off light %s - checking current state first", self._device_id
            )

            # 防抖：如果已经是关闭状态，直接返回
            if not self._attr_is_on:
                _LOGGER.debug(
                    "Light %s is already OFF locally, skipping operation",
                    self._device_id,
                )
                return

            coordinator = cast(JianfaIotDataCoordinator, self.coordinator)

            # 使用专门的方法获取当前远程状态
            current_remote_state = await coordinator.async_get_remote_state(
                self._device_id, PROPERTY_POWER
            )

            # 如果远程已经是关闭状态，不做任何操作
            if current_remote_state is not None and not bool(current_remote_state):
                _LOGGER.debug(
                    "Light %s is already OFF remotely, updating local state only",
                    self._device_id,
                )
                # 确保本地状态与远程一致
                self._attr_is_on = False
                self.async_write_ha_state()
                return

            _LOGGER.debug("Sending OFF command to light %s", self._device_id)

            # 立即更新本地状态，提高响应性
            self._attr_is_on = False
            # 记录命令发送时间，进入状态保护窗口
            self._last_command_time = time.time()
            self.async_write_ha_state()

            # 发送关灯命令
            success = await coordinator.async_send_command(
                self._device_id, PROPERTY_POWER, 0
            )

            if not success:
                _LOGGER.error("Failed to turn off light %s", self._device_id)
                # 对于失败的命令，我们仍然保持UI为"关闭"状态，因为用户已看到灯已关闭
                # 下一个正常的状态同步周期会自动纠正，如果需要的话

        except Exception as error:
            _LOGGER.error("Error turning off light %s: %s", self._device_id, error)
            # 出现异常时，我们也保持用户已经看到的状态，避免UI闪烁

    async def async_update(self) -> None:
        """Update the entity."""
        _LOGGER.debug("手动更新灯 %s 的状态", self._device_id)

        # 如果在保护窗口内，跳过手动更新
        if time.time() - self._last_command_time < self._state_protection_window:
            _LOGGER.debug(
                "跳过手动更新，因为设备 %s 处于命令保护窗口内 (%.2f 秒前发送了命令)",
                self._device_id,
                time.time() - self._last_command_time,
            )
            return

        coordinator = cast(JianfaIotDataCoordinator, self.coordinator)

        # 使用force_refresh方法强制刷新数据并立即通知监听者
        if hasattr(coordinator, "async_force_refresh"):
            await coordinator.async_force_refresh()
        else:
            # 如果方法不存在，使用标准刷新流程
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
            "收到协调器更新通知，准备更新灯状态: device_id=%s", self._device_id
        )

        # 如果在保护窗口内，跳过协调器更新处理
        if time.time() - self._last_command_time < self._state_protection_window:
            _LOGGER.debug(
                "跳过协调器更新处理，因为设备 %s 处于命令保护窗口内 (%.2f 秒前发送了命令)",
                self._device_id,
                time.time() - self._last_command_time,
            )
            return

        # 记录更新前的状态
        old_state = self._attr_is_on

        # 更新实体状态
        self._update_state_from_coordinator()

        # 记录更新后的状态
        new_state = self._attr_is_on

        # 比较状态变化
        if old_state != new_state:
            _LOGGER.debug(
                "灯状态已更新: %s -> %s",
                "ON" if old_state else "OFF",
                "ON" if new_state else "OFF",
            )
        else:
            _LOGGER.debug("灯状态未变化: %s", "ON" if new_state else "OFF")

        # 无论如何都通知HA更新UI
        self.async_write_ha_state()
