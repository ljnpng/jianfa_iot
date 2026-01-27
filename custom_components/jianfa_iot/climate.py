"""Support for HISENSE Air Conditioner."""

import asyncio
import logging
import time
from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MANUFACTURER,
    MODEL_AIRCONDITION,
)
from .coordinator import JianfaIotDataCoordinator
from .models import Room
from . import JianfaIotConfigEntry

_LOGGER = logging.getLogger(__name__)

# 空调属性代码
PROPERTY_POWER = "PowerSwitch"
PROPERTY_TEMPERATURE = "TemperatureSet"
PROPERTY_MODE = "WorkMode"
PROPERTY_FAN_SPEED = "Windspeed"

# 工作模式
MODE_COOL = 0  # 制冷
MODE_HEAT = 1  # 制热
MODE_DRY = 2  # 除湿
MODE_FAN = 3  # 送风

# 风速模式
FAN_SPEED_AUTO = 0  # 自动
FAN_SPEED_LOW = 1  # 低速
FAN_SPEED_MEDIUM = 2  # 中速
FAN_SPEED_HIGH = 3  # 高速

# HVAC 模式映射
HVAC_MODE_TO_HISENSE = {
    HVACMode.COOL: MODE_COOL,
    HVACMode.HEAT: MODE_HEAT,
    HVACMode.DRY: MODE_DRY,
    HVACMode.FAN_ONLY: MODE_FAN,
    HVACMode.OFF: None,
}

HISENSE_TO_HVAC_MODE = {
    MODE_COOL: HVACMode.COOL,
    MODE_HEAT: HVACMode.HEAT,
    MODE_DRY: HVACMode.DRY,
    MODE_FAN: HVACMode.FAN_ONLY,
}

# 风速映射
FAN_MODE_TO_HISENSE = {
    FAN_AUTO: FAN_SPEED_AUTO,
    FAN_LOW: FAN_SPEED_LOW,
    FAN_MEDIUM: FAN_SPEED_MEDIUM,
    FAN_HIGH: FAN_SPEED_HIGH,
}

HISENSE_TO_FAN_MODE = {
    FAN_SPEED_AUTO: FAN_AUTO,
    FAN_SPEED_LOW: FAN_LOW,
    FAN_SPEED_MEDIUM: FAN_MEDIUM,
    FAN_SPEED_HIGH: FAN_HIGH,
}

# 防抖时间（秒）
COMMAND_DEBOUNCE_TIME = 1.0
# 命令保护窗口（秒）- 命令发送后的这段时间内，忽略来自协调器的状态更新
COMMAND_PROTECTION_WINDOW = 10.0
# 状态更新间隔（秒）
STATE_UPDATE_INTERVAL = 30.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JianfaIotConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the HISENSE climate."""
    _LOGGER.debug("Setting up HISENSE climate devices")

    # Get data from runtime_data
    data = entry.runtime_data
    devices = data.devices
    coordinator = data.coordinator
    room = data.room_config

    _LOGGER.info("Processing devices for climate setup")

    entities = []
    climate_devices = [device for device in devices if device.is_climate]
    _LOGGER.info("Found %d climate devices", len(climate_devices))

    for device in climate_devices:
        try:
            _LOGGER.info(
                "Creating climate entity: id=%s, name=%s",
                device.device_id,
                device.device_name,
            )

            climate = HisenseClimate(
                coordinator,
                room,
                device.device_name,
                device.device_id,
                device.device_name,
                device.suit_name,
            )
            entities.append(climate)

        except Exception as error:
            _LOGGER.error(
                "Failed to set up air conditioner for device %s: %s",
                device.device_id,
                error,
            )
            continue

    if entities:
        _LOGGER.info("Adding %d climate entities", len(entities))
        async_add_entities(entities, True)
    else:
        _LOGGER.warning("No climate entities found")


class HisenseClimate(CoordinatorEntity[JianfaIotDataCoordinator], ClimateEntity):
    """Representation of a HISENSE air conditioner."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 16
    _attr_max_temp = 30
    _attr_target_temperature_step = 1
    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: JianfaIotDataCoordinator,
        room: Room,
        name: str,
        device_id: str,
        device_name: str,
        room_name: str = "",
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)

        self._device_id = device_id
        self._device_name = device_name
        self._room_name = room_name
        self._room = room  # Store room config

        # 生成有效的实体ID和唯一ID
        safe_device_id = (
            device_id.replace("-", "_").replace(".", "_").replace(":", "_").lower()
        )
        self.entity_id = f"{DOMAIN}.{safe_device_id}"
        self._attr_unique_id = f"{DOMAIN}_{device_id}"
        self._attr_name = name

        # 支持的功能
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
        )

        # 支持的模式和风速
        self._attr_hvac_modes = list(HVAC_MODE_TO_HISENSE.keys())
        self._attr_fan_modes = list(FAN_MODE_TO_HISENSE.keys())

        # 设备信息
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._attr_unique_id)},
            "name": name,
            "manufacturer": MANUFACTURER,
            "model": MODEL_AIRCONDITION,
            "suggested_area": room_name,
        }

        # 初始化状态
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_hvac_action = HVACAction.OFF
        self._attr_fan_mode = FAN_AUTO
        self._attr_current_temperature = None
        self._attr_target_temperature = 25

        # 状态管理 - 确保所有变量都在初始化时正确定义
        self._last_command_time = {}  # 记录每个属性最后命令时间
        self._local_state = {  # 本地状态跟踪
            PROPERTY_POWER: None,  # Can be bool
            PROPERTY_MODE: None,  # Can be int
            PROPERTY_TEMPERATURE: None,  # Can be float
            PROPERTY_FAN_SPEED: None,  # Can be int
        }  # type: dict[str, Any]

        # 添加状态保护窗口变量，参考light.py
        self._state_protection_window = COMMAND_PROTECTION_WINDOW

        self._update_lock = asyncio.Lock()  # 更新锁
        self._is_updating = False  # 正在更新标志

        # 初始化状态后，尝试从协调器更新
        self._async_update_from_coordinator()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug(
            "收到协调器更新通知，准备更新空调状态: device_id=%s", self._device_id
        )

        # 检查是否有属性在命令保护窗口内
        current_time = time.time()
        in_protection = False

        # 检查所有属性是否有至少一个在保护窗口内
        for property_code in [
            PROPERTY_POWER,
            PROPERTY_MODE,
            PROPERTY_TEMPERATURE,
            PROPERTY_FAN_SPEED,
        ]:
            if property_code in self._last_command_time:
                if (
                    current_time - self._last_command_time[property_code]
                ) < self._state_protection_window:
                    _LOGGER.debug(
                        "跳过协调器更新处理，因为设备 %s 的属性 %s 处于命令保护窗口内 (%.2f 秒前发送了命令)",
                        self._device_id,
                        property_code,
                        current_time - self._last_command_time[property_code],
                    )
                    in_protection = True
                    break

        # 如果在保护窗口内，则跳过更新
        if in_protection:
            return

        # 记录更新前的状态
        old_state = {
            "hvac_mode": self._attr_hvac_mode,
            "temperature": self._attr_target_temperature,
            "fan_mode": self._attr_fan_mode,
            "hvac_action": self._attr_hvac_action,
        }

        # 更新实体状态
        self._async_update_from_coordinator()

        # 记录更新后的状态并记录变化
        new_state = {
            "hvac_mode": self._attr_hvac_mode,
            "temperature": self._attr_target_temperature,
            "fan_mode": self._attr_fan_mode,
            "hvac_action": self._attr_hvac_action,
        }

        # 比较状态变化
        if old_state != new_state:
            _LOGGER.debug("空调状态已更新: %s -> %s", old_state, new_state)
        else:
            _LOGGER.debug("空调状态未变化")

        # 无论如何都通知HA更新UI
        self.async_write_ha_state()

    @callback
    def _async_update_from_coordinator(self) -> None:
        """Update attributes based on coordinator data."""
        # 记录更新前的状态，用于调试
        old_state = {
            "hvac_mode": self._attr_hvac_mode,
            "temperature": self._attr_target_temperature,
            "fan_mode": self._attr_fan_mode,
            "hvac_action": self._attr_hvac_action,
        }

        # 检查是否应该更新状态
        current_time = time.time()

        # 为每个属性检查保护窗口
        power_in_protection = False
        mode_in_protection = False
        temp_in_protection = False
        fan_in_protection = False

        # 检查每个属性是否在保护窗口内
        if PROPERTY_POWER in self._last_command_time:
            power_in_protection = (
                current_time - self._last_command_time[PROPERTY_POWER]
            ) < self._state_protection_window
            if power_in_protection:
                _LOGGER.debug(
                    "忽略电源状态更新：设备 %s 处于命令保护窗口内 (%.2f 秒前发送了命令)",
                    self._device_id,
                    current_time - self._last_command_time[PROPERTY_POWER],
                )

        if PROPERTY_MODE in self._last_command_time:
            mode_in_protection = (
                current_time - self._last_command_time[PROPERTY_MODE]
            ) < self._state_protection_window
            if mode_in_protection:
                _LOGGER.debug(
                    "忽略模式状态更新：设备 %s 处于命令保护窗口内 (%.2f 秒前发送了命令)",
                    self._device_id,
                    current_time - self._last_command_time[PROPERTY_MODE],
                )

        if PROPERTY_TEMPERATURE in self._last_command_time:
            temp_in_protection = (
                current_time - self._last_command_time[PROPERTY_TEMPERATURE]
            ) < self._state_protection_window
            if temp_in_protection:
                _LOGGER.debug(
                    "忽略温度状态更新：设备 %s 处于命令保护窗口内 (%.2f 秒前发送了命令)",
                    self._device_id,
                    current_time - self._last_command_time[PROPERTY_TEMPERATURE],
                )

        if PROPERTY_FAN_SPEED in self._last_command_time:
            fan_in_protection = (
                current_time - self._last_command_time[PROPERTY_FAN_SPEED]
            ) < self._state_protection_window
            if fan_in_protection:
                _LOGGER.debug(
                    "忽略风速状态更新：设备 %s 处于命令保护窗口内 (%.2f 秒前发送了命令)",
                    self._device_id,
                    current_time - self._last_command_time[PROPERTY_FAN_SPEED],
                )

        # 获取电源状态
        power_state = self.coordinator.async_get_device_property(
            self._device_id, PROPERTY_POWER
        )

        # 更新各属性时检查命令保护窗口
        # 1. 电源状态更新
        if power_state is not None and not power_in_protection:
            power_bool = bool(power_state)
            self._local_state[PROPERTY_POWER] = power_bool

            # 根据电源状态更新HVAC模式
            if not power_bool:
                self._attr_hvac_mode = HVACMode.OFF
                self._attr_hvac_action = HVACAction.OFF

        # 只有在设备开启状态下才更新其他属性
        if self._attr_hvac_mode != HVACMode.OFF:
            # 2. 工作模式更新
            mode = self.coordinator.async_get_device_property(
                self._device_id, PROPERTY_MODE
            )
            if (
                mode is not None
                and not mode_in_protection
                and mode in HISENSE_TO_HVAC_MODE
            ):
                self._local_state[PROPERTY_MODE] = mode
                self._attr_hvac_mode = HISENSE_TO_HVAC_MODE[mode]
                self._update_hvac_action()

            # 3. 温度更新
            temp = self.coordinator.async_get_device_property(
                self._device_id, PROPERTY_TEMPERATURE
            )
            if temp is not None and not temp_in_protection:
                self._local_state[PROPERTY_TEMPERATURE] = float(temp)
                self._attr_target_temperature = float(temp)

            # 4. 风速更新
            fan_speed = self.coordinator.async_get_device_property(
                self._device_id, PROPERTY_FAN_SPEED
            )
            if (
                fan_speed is not None
                and not fan_in_protection
                and fan_speed in HISENSE_TO_FAN_MODE
            ):
                self._local_state[PROPERTY_FAN_SPEED] = fan_speed
                self._attr_fan_mode = HISENSE_TO_FAN_MODE[fan_speed]

        # 调试日志：记录状态变化
        new_state = {
            "hvac_mode": self._attr_hvac_mode,
            "temperature": self._attr_target_temperature,
            "fan_mode": self._attr_fan_mode,
            "hvac_action": self._attr_hvac_action,
        }

        if old_state != new_state:
            _LOGGER.debug(
                "Climate %s state updated: %s -> %s",
                self._device_id,
                old_state,
                new_state,
            )

    def _update_hvac_action(self) -> None:
        """Update the hvac action based on the current mode."""
        if self._attr_hvac_mode == HVACMode.OFF:
            self._attr_hvac_action = HVACAction.OFF
        elif self._attr_hvac_mode == HVACMode.COOL:
            self._attr_hvac_action = HVACAction.COOLING
        elif self._attr_hvac_mode == HVACMode.HEAT:
            self._attr_hvac_action = HVACAction.HEATING
        elif self._attr_hvac_mode == HVACMode.DRY:
            self._attr_hvac_action = HVACAction.DRYING
        elif self._attr_hvac_mode == HVACMode.FAN_ONLY:
            self._attr_hvac_action = HVACAction.FAN
        else:
            self._attr_hvac_action = HVACAction.IDLE

    def _should_debounce(self, property_code: str) -> bool:
        """Check if we should debounce command for this property."""
        now = time.time()
        last_time = self._last_command_time.get(property_code, 0)

        if now - last_time < COMMAND_DEBOUNCE_TIME:
            _LOGGER.debug(
                "Debouncing %s command for %s (last: %.1fs ago)",
                property_code,
                self._device_id,
                now - last_time,
            )
            return True

        self._last_command_time[property_code] = now
        return False

    async def _async_ensure_device_on(self) -> bool:
        """Ensure device is turned on before setting other properties."""
        if self._attr_hvac_mode == HVACMode.OFF:
            _LOGGER.debug(
                "Turning ON device %s before setting properties", self._device_id
            )

            # 记录命令时间，开启命令保护窗口
            self._last_command_time[PROPERTY_POWER] = time.time()

            # 发送开机命令
            if not await self.coordinator.async_send_command(
                self._device_id, PROPERTY_POWER, 1
            ):
                _LOGGER.error("Failed to turn ON device %s", self._device_id)
                return False

            # 更新内部状态以立即反映UI变化（提高响应速度）
            self._attr_hvac_mode = HVACMode.COOL  # 默认模式
            self._update_hvac_action()
            self._local_state[PROPERTY_POWER] = True
            self.async_write_ha_state()

            # 等待设备稳定
            await asyncio.sleep(1)

        return True

    async def _async_refresh_state(self) -> None:
        """Refresh device state with debounce protection."""
        async with self._update_lock:
            if self._is_updating:
                _LOGGER.debug(
                    "State refresh already in progress for %s", self._device_id
                )
                return

            try:
                self._is_updating = True
                await self.coordinator.async_request_refresh()
            except Exception as err:
                _LOGGER.error("Error refreshing state for %s: %s", self._device_id, err)
            finally:
                self._is_updating = False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the climate device on."""
        # 防抖检查
        if self._attr_hvac_mode != HVACMode.OFF:
            _LOGGER.debug("Device %s is already ON", self._device_id)
            return

        if self._should_debounce(PROPERTY_POWER):
            return

        # 记录命令时间，开启命令保护窗口
        self._last_command_time[PROPERTY_POWER] = time.time()

        # 立即更新本地状态和UI状态（提高响应速度）
        old_mode = self._attr_hvac_mode
        self._attr_hvac_mode = HVACMode.COOL  # 默认开机模式
        self._update_hvac_action()
        self._local_state[PROPERTY_POWER] = True
        self.async_write_ha_state()

        # 发送开机命令
        success = await self.coordinator.async_send_command(
            self._device_id, PROPERTY_POWER, 1
        )

        if not success:
            # 恢复原状态
            _LOGGER.error("Failed to turn ON device %s", self._device_id)
            self._attr_hvac_mode = old_mode
            self._update_hvac_action()
            self._local_state[PROPERTY_POWER] = False
            self.async_write_ha_state()
            return

        # 不立即刷新设备状态，而是依赖定期更新
        # 命令发送后，将使用命令保护窗口来确保本地状态优先

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the climate device off."""
        # 防抖检查
        if self._attr_hvac_mode == HVACMode.OFF:
            _LOGGER.debug("Device %s is already OFF", self._device_id)
            return

        if self._should_debounce(PROPERTY_POWER):
            return

        # 记录命令时间，开启命令保护窗口
        self._last_command_time[PROPERTY_POWER] = time.time()

        # 立即更新本地状态和UI状态（提高响应速度）
        old_mode = self._attr_hvac_mode
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_hvac_action = HVACAction.OFF
        self._local_state[PROPERTY_POWER] = False
        self.async_write_ha_state()

        # 发送关机命令
        success = await self.coordinator.async_send_command(
            self._device_id, PROPERTY_POWER, 0
        )

        if not success:
            # 恢复原状态
            _LOGGER.error("Failed to turn OFF device %s", self._device_id)
            self._attr_hvac_mode = old_mode
            self._update_hvac_action()
            self._local_state[PROPERTY_POWER] = True
            self.async_write_ha_state()
            return

        # 不立即刷新设备状态，而是依赖定期更新
        # 命令发送后，将使用命令保护窗口来确保本地状态优先

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set new target hvac mode."""
        # 关机请求
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
            return

        # 防抖检查
        if hvac_mode == self._attr_hvac_mode:
            if self._should_debounce(PROPERTY_MODE):
                return
        else:
            # 记录命令时间（不同模式的切换不受防抖限制）
            self._last_command_time[PROPERTY_MODE] = time.time()

        # 确保设备已开机
        if not await self._async_ensure_device_on():
            return

        # 更改模式
        if hvac_mode in HVAC_MODE_TO_HISENSE:
            hisense_mode = HVAC_MODE_TO_HISENSE[hvac_mode]

            # 立即更新本地状态和UI状态（提高响应速度）
            old_mode = self._attr_hvac_mode
            self._attr_hvac_mode = hvac_mode
            self._update_hvac_action()
            self._local_state[PROPERTY_MODE] = hisense_mode
            self.async_write_ha_state()

            # 发送模式命令
            success = await self.coordinator.async_send_command(
                self._device_id, PROPERTY_MODE, hisense_mode
            )

            if not success:
                # 恢复原状态
                _LOGGER.error(
                    "Failed to set mode %s for device %s", hvac_mode, self._device_id
                )
                self._attr_hvac_mode = old_mode
                self._update_hvac_action()
                # 还原本地状态
                if old_mode != HVACMode.OFF and old_mode in HVAC_MODE_TO_HISENSE:
                    self._local_state[PROPERTY_MODE] = HVAC_MODE_TO_HISENSE[old_mode]
                self.async_write_ha_state()
                return

            # 不立即刷新设备状态，而是依赖定期更新
            # 命令发送后，将使用命令保护窗口来确保本地状态优先

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode."""
        # 防抖检查
        if fan_mode == self._attr_fan_mode:
            if self._should_debounce(PROPERTY_FAN_SPEED):
                return
        else:
            # 记录命令时间（不同风速的切换不受防抖限制）
            self._last_command_time[PROPERTY_FAN_SPEED] = time.time()

        # 确保设备已开机
        if not await self._async_ensure_device_on():
            return

        # 更改风速
        if fan_mode in FAN_MODE_TO_HISENSE:
            hisense_fan_speed = FAN_MODE_TO_HISENSE[fan_mode]

            # 立即更新本地状态和UI状态（提高响应速度）
            old_fan_mode = self._attr_fan_mode
            self._attr_fan_mode = fan_mode
            self._local_state[PROPERTY_FAN_SPEED] = hisense_fan_speed
            self.async_write_ha_state()

            # 发送风速命令
            success = await self.coordinator.async_send_command(
                self._device_id, PROPERTY_FAN_SPEED, hisense_fan_speed
            )

            if not success:
                # 恢复原状态
                _LOGGER.error(
                    "Failed to set fan mode %s for device %s", fan_mode, self._device_id
                )
                self._attr_fan_mode = old_fan_mode
                # 还原本地状态
                if old_fan_mode in FAN_MODE_TO_HISENSE:
                    self._local_state[PROPERTY_FAN_SPEED] = FAN_MODE_TO_HISENSE[
                        old_fan_mode
                    ]
                self.async_write_ha_state()
                return

            # 不立即刷新设备状态，而是依赖定期更新
            # 命令发送后，将使用命令保护窗口来确保本地状态优先

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get("temperature")
        if temperature is None:
            return

        # 确保温度在允许的范围内
        temperature = max(
            min(int(temperature), self._attr_max_temp), self._attr_min_temp
        )

        # 防抖检查
        if temperature == self._attr_target_temperature:
            if self._should_debounce(PROPERTY_TEMPERATURE):
                return
        else:
            # 记录命令时间（不同温度的更改不受防抖限制）
            self._last_command_time[PROPERTY_TEMPERATURE] = time.time()

        # 确保设备已开机
        if not await self._async_ensure_device_on():
            return

        # 立即更新本地状态和UI状态（提高响应速度）
        old_temp = self._attr_target_temperature
        self._attr_target_temperature = temperature
        self._local_state[PROPERTY_TEMPERATURE] = float(temperature)
        self.async_write_ha_state()

        # 发送温度命令
        success = await self.coordinator.async_send_command(
            self._device_id, PROPERTY_TEMPERATURE, temperature
        )

        if not success:
            # 恢复原状态
            _LOGGER.error(
                "Failed to set temperature %s for device %s",
                temperature,
                self._device_id,
            )
            self._attr_target_temperature = old_temp
            # Handle case where old_temp might be None
            if old_temp is not None:
                self._local_state[PROPERTY_TEMPERATURE] = float(old_temp)
            else:
                self._local_state[PROPERTY_TEMPERATURE] = None
            self.async_write_ha_state()
            return

        # 不立即刷新设备状态，而是依赖定期更新
        # 命令发送后，将使用命令保护窗口来确保本地状态优先

    async def async_update(self) -> None:
        """Update the entity."""
        _LOGGER.debug("手动更新空调 %s 的状态", self._device_id)

        # 检查是否有属性在命令保护窗口内
        current_time = time.time()
        for property_code in [
            PROPERTY_POWER,
            PROPERTY_MODE,
            PROPERTY_TEMPERATURE,
            PROPERTY_FAN_SPEED,
        ]:
            if property_code in self._last_command_time:
                if (
                    current_time - self._last_command_time[property_code]
                ) < self._state_protection_window:
                    _LOGGER.debug(
                        "跳过手动更新，因为设备 %s 的属性 %s 处于命令保护窗口内 (%.2f 秒前发送了命令)",
                        self._device_id,
                        property_code,
                        current_time - self._last_command_time[property_code],
                    )
                    return

        # 使用标准刷新流程
        await self.coordinator.async_request_refresh()
