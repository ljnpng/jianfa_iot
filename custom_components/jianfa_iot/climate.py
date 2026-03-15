"""Support for HISENSE Air Conditioner."""

import asyncio
import logging
from typing import Any, cast

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
from .coordinator import DeviceCoordinator
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
    coordinators = data.coordinators
    room = data.room_config

    _LOGGER.info("Processing devices for climate setup")

    entities = []
    climate_devices = [device for device in devices if device.is_climate]
    _LOGGER.info("Found %d climate devices", len(climate_devices))

    for device in climate_devices:
        try:
            # Get the coordinator for this device
            coordinator = coordinators.get(device.device_id)
            if not coordinator:
                _LOGGER.error(
                    "No coordinator found for climate device %s",
                    device.device_id,
                )
                continue

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


class HisenseClimate(CoordinatorEntity[DeviceCoordinator], ClimateEntity):
    """Representation of a HISENSE air conditioner."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 16
    _attr_max_temp = 30
    _attr_target_temperature_step = 1
    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: DeviceCoordinator,
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

        # 状态管理
        self._local_state: dict[str, Any] = {
            PROPERTY_POWER: None,
            PROPERTY_MODE: None,
            PROPERTY_TEMPERATURE: None,
            PROPERTY_FAN_SPEED: None,
        }

        self._update_lock = asyncio.Lock()
        self._is_updating = False

        # 初始化状态后，尝试从协调器更新
        self._async_update_from_coordinator()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug(
            "Received coordinator update for climate %s",
            self._device_id,
        )

        coordinator = cast(DeviceCoordinator, self.coordinator)

        # Check if any property has pending verification
        # NEW LOGIC:
        # - None: No pending verification -> ACCEPT update (physical button sync)
        # - "pending": Verification in progress -> IGNORE update (protect optimistic state)
        # - "confirmed"/"timeout": Verification complete -> ACCEPT update
        has_pending = False
        for property_code in [
            PROPERTY_POWER,
            PROPERTY_MODE,
            PROPERTY_TEMPERATURE,
            PROPERTY_FAN_SPEED,
        ]:
            status = coordinator.get_verification_status(property_code)
            if status == "pending":
                has_pending = True
                _LOGGER.debug(
                    "Property %s has pending verification for device %s",
                    property_code,
                    self._device_id,
                )
                break

        if has_pending:
            _LOGGER.debug(
                "Skipping coordinator update for %s: pending verifications",
                self._device_id,
            )
            return

        # Accept update for None, "confirmed", or "timeout"
        _LOGGER.debug(
            "Accepting coordinator update for %s: no pending verifications",
            self._device_id,
        )

        old_state = {
            "hvac_mode": self._attr_hvac_mode,
            "temperature": self._attr_target_temperature,
            "fan_mode": self._attr_fan_mode,
            "hvac_action": self._attr_hvac_action,
        }

        self._async_update_from_coordinator()

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

        self.async_write_ha_state()

    @callback
    def _async_update_from_coordinator(self) -> None:
        """Update attributes based on coordinator data."""
        coordinator = cast(DeviceCoordinator, self.coordinator)

        # Get power state
        power_state = coordinator.async_get_device_property(PROPERTY_POWER)

        if power_state is not None:
            power_bool = bool(power_state)
            self._local_state[PROPERTY_POWER] = power_bool

            if not power_bool:
                self._attr_hvac_mode = HVACMode.OFF
                self._attr_hvac_action = HVACAction.OFF
                return

        # Device is on, update other properties
        # Mode
        mode = coordinator.async_get_device_property(PROPERTY_MODE)
        if mode is not None and mode in HISENSE_TO_HVAC_MODE:
            self._local_state[PROPERTY_MODE] = mode
            self._attr_hvac_mode = HISENSE_TO_HVAC_MODE[mode]
            self._update_hvac_action()

        # Temperature
        temp = coordinator.async_get_device_property(PROPERTY_TEMPERATURE)
        if temp is not None:
            self._local_state[PROPERTY_TEMPERATURE] = float(temp)
            self._attr_target_temperature = float(temp)

        # Fan speed
        fan_speed = coordinator.async_get_device_property(PROPERTY_FAN_SPEED)
        if fan_speed is not None and fan_speed in HISENSE_TO_FAN_MODE:
            self._local_state[PROPERTY_FAN_SPEED] = fan_speed
            self._attr_fan_mode = HISENSE_TO_FAN_MODE[fan_speed]

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

    async def _async_ensure_device_on(self) -> bool:
        """Ensure device is turned on before setting other properties."""
        coordinator = cast(DeviceCoordinator, self.coordinator)

        if self._attr_hvac_mode == HVACMode.OFF:
            _LOGGER.debug(
                "Turning ON device %s before setting properties", self._device_id
            )

            # 发送开机命令
            if not await coordinator.async_send_command_with_verify(PROPERTY_POWER, 1):
                _LOGGER.error("Failed to turn ON device %s", self._device_id)
                return False

            # 更新内部状态以立即反映UI变化
            self._attr_hvac_mode = HVACMode.COOL  # 默认模式
            self._update_hvac_action()
            self._local_state[PROPERTY_POWER] = True
            self.async_write_ha_state()

            # 等待设备稳定
            await asyncio.sleep(1)

        return True

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the climate device on."""
        coordinator = cast(DeviceCoordinator, self.coordinator)

        # Optimistic update
        _LOGGER.debug("Turning on device %s", self._device_id)
        old_mode = self._attr_hvac_mode
        self._attr_hvac_mode = HVACMode.COOL
        self._update_hvac_action()
        self._local_state[PROPERTY_POWER] = True
        self.async_write_ha_state()

        # Send command with verification
        success = await coordinator.async_send_command_with_verify(PROPERTY_POWER, 1)

        if not success:
            # Revert on failure
            _LOGGER.error("Failed to turn ON device %s", self._device_id)
            self._attr_hvac_mode = old_mode
            self._update_hvac_action()
            self._local_state[PROPERTY_POWER] = False
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the climate device off."""
        coordinator = cast(DeviceCoordinator, self.coordinator)

        # Optimistic update
        _LOGGER.debug("Turning off device %s", self._device_id)
        old_mode = self._attr_hvac_mode
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_hvac_action = HVACAction.OFF
        self._local_state[PROPERTY_POWER] = False
        self.async_write_ha_state()

        # Send command with verification
        success = await coordinator.async_send_command_with_verify(PROPERTY_POWER, 0)

        if not success:
            # Revert on failure
            _LOGGER.error("Failed to turn OFF device %s", self._device_id)
            self._attr_hvac_mode = old_mode
            self._update_hvac_action()
            self._local_state[PROPERTY_POWER] = True
            self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set new target hvac mode."""
        # Handle OFF
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
            return

        # Ensure device is on
        if not await self._async_ensure_device_on():
            return

        coordinator = cast(DeviceCoordinator, self.coordinator)

        # Change mode
        if hvac_mode in HVAC_MODE_TO_HISENSE:
            hisense_mode = HVAC_MODE_TO_HISENSE[hvac_mode]

            # Optimistic update
            _LOGGER.debug(
                "Setting mode for device %s to %s",
                self._device_id,
                hvac_mode,
            )
            old_mode = self._attr_hvac_mode
            self._attr_hvac_mode = hvac_mode
            self._update_hvac_action()
            self._local_state[PROPERTY_MODE] = hisense_mode
            self.async_write_ha_state()

            # Send command with verification
            success = await coordinator.async_send_command_with_verify(
                PROPERTY_MODE, hisense_mode
            )

            if not success:
                # Revert on failure
                _LOGGER.error(
                    "Failed to set mode %s for device %s",
                    hvac_mode,
                    self._device_id,
                )
                self._attr_hvac_mode = old_mode
                self._update_hvac_action()
                if old_mode != HVACMode.OFF and old_mode in HVAC_MODE_TO_HISENSE:
                    self._local_state[PROPERTY_MODE] = HVAC_MODE_TO_HISENSE[old_mode]
                self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode."""
        # Ensure device is on
        if not await self._async_ensure_device_on():
            return

        coordinator = cast(DeviceCoordinator, self.coordinator)

        # Change fan speed
        if fan_mode in FAN_MODE_TO_HISENSE:
            hisense_fan_speed = FAN_MODE_TO_HISENSE[fan_mode]

            # Optimistic update
            _LOGGER.debug(
                "Setting fan mode for device %s to %s",
                self._device_id,
                fan_mode,
            )
            old_fan_mode = self._attr_fan_mode
            self._attr_fan_mode = fan_mode
            self._local_state[PROPERTY_FAN_SPEED] = hisense_fan_speed
            self.async_write_ha_state()

            # Send command with verification
            success = await coordinator.async_send_command_with_verify(
                PROPERTY_FAN_SPEED, hisense_fan_speed
            )

            if not success:
                # Revert on failure
                _LOGGER.error(
                    "Failed to set fan mode %s for device %s",
                    fan_mode,
                    self._device_id,
                )
                self._attr_fan_mode = old_fan_mode
                if old_fan_mode in FAN_MODE_TO_HISENSE:
                    self._local_state[PROPERTY_FAN_SPEED] = FAN_MODE_TO_HISENSE[
                        old_fan_mode
                    ]
                self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get("temperature")
        if temperature is None:
            return

        # Clamp temperature
        temperature = max(
            min(int(temperature), self._attr_max_temp), self._attr_min_temp
        )

        # Ensure device is on
        if not await self._async_ensure_device_on():
            return

        coordinator = cast(DeviceCoordinator, self.coordinator)

        # Optimistic update
        _LOGGER.debug(
            "Setting temperature for device %s to %s",
            self._device_id,
            temperature,
        )
        old_temp = self._attr_target_temperature
        self._attr_target_temperature = temperature
        self._local_state[PROPERTY_TEMPERATURE] = float(temperature)
        self.async_write_ha_state()

        # Send command with verification
        success = await coordinator.async_send_command_with_verify(
            PROPERTY_TEMPERATURE, temperature
        )

        if not success:
            # Revert on failure
            _LOGGER.error(
                "Failed to set temperature %s for device %s",
                temperature,
                self._device_id,
            )
            self._attr_target_temperature = old_temp
            if old_temp is not None:
                self._local_state[PROPERTY_TEMPERATURE] = float(old_temp)
            else:
                self._local_state[PROPERTY_TEMPERATURE] = None
            self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update the entity."""
        _LOGGER.debug("Manual update for climate %s", self._device_id)
        self._async_update_from_coordinator()
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        coordinator = cast(DeviceCoordinator, self.coordinator)
        return coordinator.available
