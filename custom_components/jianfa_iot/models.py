"""Data models for C&D Iot integration."""
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

_LOGGER = logging.getLogger(__name__)

class DeviceState:
    """Model representing device state."""

    def __init__(self, state_data: Optional[Dict[str, Any]] = None):
        """Initialize device state from parsed state data."""
        if state_data is None:
            state_data = {}
            
        self.power_switch = state_data.get("PowerSwitch", 0)
        self.temperature_set = state_data.get("TemperatureSet")
        self.work_mode = state_data.get("WorkMode")
        self.wind_speed = state_data.get("Windspeed")
        
    @property
    def is_on(self) -> bool:
        """Return if device is on.

        Note: API returns PowerSwitch as string "0" or "1", or int 0/1.
        We need to handle both cases correctly.
        """
        # Handle string "0"/"1" and int 0/1
        if isinstance(self.power_switch, str):
            return self.power_switch == "1"
        return bool(self.power_switch)


class Device:
    """Model representing a device."""

    def __init__(self, device_data: Optional[Dict[str, Any]] = None):
        """Initialize from device data dictionary."""
        if device_data is None:
            _LOGGER.warning("Empty device data provided")
            device_data = {}
        
        self.product_id = device_data.get("productId", "")
        self.id = device_data.get("id", "")
        self.brand = device_data.get("brand", "")
        self.device_id = device_data.get("deviceId", "")
        self.device_type = device_data.get("deviceType", "")
        self.address = device_data.get("address", "")
        self.device_name = device_data.get("deviceName", "")
        self.suit_name = device_data.get("suitName", "")  # Room name
        self.suit_id = device_data.get("suitId", "")
        self.device_status = device_data.get("deviceStatus", "")
        
        # Parse current state
        self.state = None
        try:
            current_state = device_data.get("currentState")
            if current_state:
                if isinstance(current_state, str):
                    try:
                        state_data = json.loads(current_state)
                        self.state = DeviceState(state_data)
                        _LOGGER.debug(
                            "Parsed state for device %s: %s", 
                            self.device_id, 
                            state_data
                        )
                    except json.JSONDecodeError as error:
                        _LOGGER.error(
                            "Failed to parse state string for device %s: %s - %s",
                            self.device_id,
                            current_state,
                            error
                        )
                        self.state = DeviceState()
                elif isinstance(current_state, dict):
                    # Handle the case where state is already a dict
                    self.state = DeviceState(current_state)
                    _LOGGER.debug(
                        "Using dict state for device %s: %s",
                        self.device_id,
                        current_state
                    )
                else:
                    _LOGGER.warning(
                        "Current state for device %s is not a string or dict: %s",
                        self.device_id,
                        current_state
                    )
                    self.state = DeviceState()
            else:
                _LOGGER.debug("No state data for device %s, using default state", self.device_id)
                self.state = DeviceState()
        except Exception as error:
            _LOGGER.error(
                "Unexpected error parsing state for device %s: %s",
                self.device_id,
                error
            )
            self.state = DeviceState()

    @property
    def is_light(self) -> bool:
        """Check if device is a light."""
        from .const import DEVICE_TYPE_LIGHT
        return self.product_id == DEVICE_TYPE_LIGHT
    
    @property
    def is_climate(self) -> bool:
        """Check if device is an air conditioner."""
        from .const import DEVICE_TYPE_AIRCONDITION
        return self.product_id == DEVICE_TYPE_AIRCONDITION


class DeviceList:
    """Model representing a list of devices."""

    def __init__(self, response_data: Optional[Dict[str, Any]] = None):
        """Initialize from API response data."""
        if response_data is None:
            _LOGGER.warning("Empty response data provided")
            response_data = {}
            
        self.code = response_data.get("code")
        self.message = response_data.get("msg", "")
        self.total = int(response_data.get("total", 0))
        self.current_page = response_data.get("current", "0")
        
        # Parse device data
        self.devices: List[Device] = []
        rows = response_data.get("rows", [])
        
        for device_data in rows:
            try:
                device = Device(device_data)
                self.devices.append(device)
            except Exception as error:
                _LOGGER.error("Error creating device from data: %s - %s", device_data, error)
            
    @property
    def light_devices(self) -> List[Device]:
        """Return all light devices."""
        return [device for device in self.devices if device.is_light]
    
    @property
    def climate_devices(self) -> List[Device]:
        """Return all climate devices."""
        return [device for device in self.devices if device.is_climate]


@dataclass
class Room:
    """Room configuration model.

    Contains all configuration needed to make API requests
    for devices in this room.
    """
    room_id: str
    community_id: str
    community_code: str
    community_name: str
    gateway: str
    eas_id: str
    room_name: str
    building_name: str | None = None

    def build_headers(self, token: str, phone: str) -> dict[str, str]:
        """Build HTTP headers for API requests.

        Args:
            token: Access token from login
            phone: User's phone number

        Returns:
            Dictionary of HTTP headers
        """
        return {
            "X-token": token,
            "space-phone": phone,
            "roomid": self.room_id,
            "communityId": self.community_id,
            "communityCode": self.community_code,
            "communityName": self.community_name,
            "space-yr": self.community_id,  # Same as communityId
            "easId": self.eas_id,
            "gateway": self.gateway,
        }


@dataclass
class RoomList:
    """Room list API response model."""
    total: int
    rooms: list[Room]

    @property
    def first_room(self) -> Room | None:
        """Get the first room from the list.

        Returns:
            First Room if available, None otherwise
        """
        return self.rooms[0] if self.rooms else None 