# Dynamic Configuration from API Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove hardcoded configuration from `const.py` and dynamically fetch room configuration from API after login.

**Architecture:** Login with SMS → Get token → Fetch room list → Use room config for device operations. Store auth in `entry.data`, runtime objects in `entry.runtime_data` following HA 2024 best practices.

**Tech Stack:** Home Assistant 2024.12+, Python 3.12, aiohttp, dataclasses, type hints

---

## Task 1: Add Room and RoomList Data Models

**Files:**
- Modify: `models.py`

**Step 1: Write failing test for Room model**

Create test file: `tests/test_models.py`

```python
"""Test data models."""
import pytest
from custom_components.jianfa_iot.models import Room, RoomList

def test_room_creation():
    """Test Room dataclass creation."""
    room = Room(
        room_id="test-room-123",
        community_id="comm-456",
        community_code="35020369",
        community_name="Test Community",
        gateway="XMSLYL-TEST:123",
        eas_id="test-eas",
        room_name="Test Room",
        building_name="Building 1",
    )

    assert room.room_id == "test-room-123"
    assert room.community_id == "comm-456"
    assert room.community_code == "35020369"
    assert room.room_name == "Test Room"

def test_room_build_headers():
    """Test building headers from room config."""
    room = Room(
        room_id="room-1",
        community_id="comm-1",
        community_code="001",
        community_name="Community 1",
        gateway="gw-1",
        eas_id="eas-1",
        room_name="Room 1",
    )

    headers = room.build_headers(
        token="test-token",
        phone="13800138000"
    )

    assert headers["X-token"] == "test-token"
    assert headers["space-phone"] == "13800138000"
    assert headers["roomid"] == "room-1"
    assert headers["communityId"] == "comm-1"
    assert headers["communityCode"] == "001"
    assert headers["communityName"] == "Community 1"
    assert headers["space-yr"] == "comm-1"
    assert headers["easId"] == "eas-1"
    assert headers["gateway"] == "gw-1"

def test_room_list_first_room():
    """Test RoomList.first_room property."""
    room1 = Room(
        room_id="room-1",
        community_id="comm-1",
        community_code="001",
        community_name="Community 1",
        gateway="gw-1",
        eas_id="eas-1",
        room_name="Room 1",
    )

    room2 = Room(
        room_id="room-2",
        community_id="comm-2",
        community_code="002",
        community_name="Community 2",
        gateway="gw-2",
        eas_id="eas-2",
        room_name="Room 2",
    )

    room_list = RoomList(total=2, rooms=[room1, room2])

    assert room_list.first_room == room1
    assert room_list.first_room.room_id == "room-1"

def test_room_list_empty():
    """Test RoomList with no rooms."""
    room_list = RoomList(total=0, rooms=[])

    assert room_list.first_room is None
    assert room_list.total == 0
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_models.py -v
```

Expected: `ImportError: cannot import name 'Room' from 'custom_components.jianfa_iot.models'`

**Step 3: Implement Room and RoomList models**

Add to `models.py` (after existing DeviceState class):

```python
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
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_models.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add models.py tests/test_models.py
git commit -m "feat: add Room and RoomList data models"
```

---

## Task 2: Update const.py to Remove Hardcoded Configuration

**Files:**
- Modify: `const.py`

**Step 1: Update const.py**

Replace entire `const.py` with:

```python
"""Constants for the C&D Iot integration."""

DOMAIN = "jianfa_iot"

# API URLs
BASE_URL = "https://sqdn.cndmega.com/prod-v2.0.1/smart/mini/smart"
DEVICE_LIST_URL = f"{BASE_URL}/device/list"
ROOM_LIST_URL = "https://sqdn.cndmega.com/prod-v2.0.1/system/mini/smart/rooms"

# Authentication URLs
AUTH_BASE_URL = "https://sqdn.cndmega.com/prod-v2.0.1/auth/owner"
AUTH_GET_CODE_URL = f"{AUTH_BASE_URL}/code"
AUTH_LOGIN_URL = f"{AUTH_BASE_URL}/login"

# Fixed headers (not including user-specific data)
FIXED_HEADERS = {
    "Accept": "*/*",
    "Content-Type": "application/json",
    "brand": "HISENSE",
    "execution-side": "APP",
}

# Device types
DEVICE_TYPE_LIGHT = "connector.device.type.smartSwitch.c4"
DEVICE_TYPE_AIRCONDITION = "connector.device.type.aircondition"

# Device info
MANUFACTURER = "HISENSE"
MODEL_LIGHT = "Smart Light"
MODEL_AIRCONDITION = "Smart Air Conditioner"

# Configuration
DEFAULT_TIMEOUT = 10
QUERY_INTERVAL = 5
DEFAULT_MAX_RETRIES = 3
DEFAULT_PAGE_SIZE = 20
DEFAULT_PAGE_NUM = 1
```

**Step 2: Verify existing tests still pass**

```bash
pytest tests/ -v
```

Expected: Existing tests still pass (no tests should be checking removed constants)

**Step 3: Commit**

```bash
git add const.py
git commit -m "refactor: remove hardcoded config, add FIXED_HEADERS"
```

---

## Task 3: Add get_room_list() Method to HttpClient

**Files:**
- Modify: `http_client.py`
- Create: `tests/test_http_client.py`

**Step 1: Write failing test for get_room_list**

Create `tests/test_http_client.py`:

```python
"""Test HttpClient."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from custom_components.jianfa_iot.http_client import HttpClient
from custom_components.jianfa_iot.models import Room, RoomList

@pytest.mark.asyncio
async def test_get_room_list_success(hass):
    """Test successful room list retrieval."""
    # Mock the HTTP response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.headers = {}
    mock_response.json = AsyncMock(return_value={
        "code": 200,
        "msg": "操作成功",
        "total": "1",
        "rows": [{
            "roomId": "test-room-id-1234567890abcdef",
            "communityId": "test-community-id-1234567890",
            "communityCode": "001",
            "communityName": "测试社区服务中心",
            "gateway": "TEST-GATEWAY:86100c00fffe008000000040e2501a1f",
            "easId": "test-eas-id",
            "roomName": "测试10号楼 B梯 303",
            "buildingName": "10#",
        }]
    })
    mock_response.raise_for_status = MagicMock()

    with patch.object(hass.helpers.aiohttp_client.async_get_clientsession(), 'get') as mock_get:
        mock_get.return_value.__aenter__.return_value = mock_response

        client = HttpClient(hass, x_token="test-token", phone="13800138000")
        room_list = await client.get_room_list()

        assert isinstance(room_list, RoomList)
        assert room_list.total == 1
        assert len(room_list.rooms) == 1
        assert room_list.first_room is not None
        assert room_list.first_room.room_id == "test-room-id-1234567890abcdef"
        assert room_list.first_room.community_id == "test-community-id-1234567890"
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_http_client.py -v
```

Expected: `AttributeError: 'HttpClient' object has no attribute 'get_room_list'`

**Step 3: Implement get_room_list method**

Add to `http_client.py` (after `__init__` method):

```python
async def get_room_list(self) -> RoomList:
    """Get user's room list.

    This endpoint only requires token and phone number.
    Called after login to retrieve room configuration.

    Returns:
        RoomList with user's rooms

    Raises:
        AuthenticationError: If token is invalid
        InvalidResponseError: If response is invalid
        NetworkError: If network error occurs
    """
    from .const import ROOM_LIST_URL, FIXED_HEADERS
    from .models import Room

    try:
        headers = {
            **FIXED_HEADERS,
            "X-token": self._token,
            "space-phone": self._phone,
        }
        params = {
            "pageSize": "9999",
            "pageNum": "1",
            "roomStatus": "Binding",
        }

        async with async_timeout.timeout(DEFAULT_TIMEOUT):
            response = await self._session.get(
                ROOM_LIST_URL,
                headers=headers,
                params=params,
            )

            if response.status == 401:
                from .exceptions import AuthenticationError
                raise AuthenticationError("Authentication failed")

            response.raise_for_status()
            response_data = await response.json()

            if response_data.get("code") != 200:
                from .exceptions import InvalidResponseError
                error_msg = response_data.get("msg", "Unknown error")
                raise InvalidResponseError(
                    f"Room list error: {error_msg}"
                )

            room_list = RoomList(
                total=int(response_data.get("total", 0)),
                rooms=[],
            )

            # Parse rooms
            for room_data in response_data.get("rows", []):
                room = Room(
                    room_id=room_data["roomId"],
                    community_id=room_data["communityId"],
                    community_code=room_data["communityCode"],
                    community_name=room_data["communityName"],
                    gateway=room_data["gateway"],
                    eas_id=room_data["easId"],
                    room_name=room_data["roomName"],
                    building_name=room_data.get("buildingName"),
                )
                room_list.rooms.append(room)

            _LOGGER.info(
                "Found %d room(s), using: %s",
                len(room_list.rooms),
                room_list.first_room.room_name if room_list.first_room else "None"
            )

            return room_list

    except asyncio.TimeoutError as error:
        from .exceptions import DeviceTimeoutError
        raise DeviceTimeoutError("Timeout") from error
    except AuthenticationError:
        raise
    except Exception as error:
        from .exceptions import InvalidResponseError
        raise InvalidResponseError(f"Invalid response: {error}") from error
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_http_client.py::test_get_room_list_success -v
```

Expected: Test PASS

**Step 5: Commit**

```bash
git add http_client.py tests/test_http_client.py
git commit -m "feat: add get_room_list to HttpClient"
```

---

## Task 4: Update get_device_list() to Use Room Config

**Files:**
- Modify: `http_client.py`

**Step 1: Update get_device_list method signature and implementation**

Modify `get_device_list` in `http_client.py`:

```python
async def get_device_list(
    self,
    room: Room,
    page_size: int = DEFAULT_PAGE_SIZE,
    page_num: int = DEFAULT_PAGE_NUM,
) -> DeviceList:
    """Get device list using room configuration.

    Args:
        room: Room configuration for building headers
        page_size: Number of items per page
        page_num: Page number

    Returns:
        DeviceList with devices

    Raises:
        AuthenticationError: If token is invalid
        BatchQueryError: If query fails
        NetworkError: If network error occurs
    """
    try:
        headers = {
            **FIXED_HEADERS,
            "X-token": self._token,
            "space-phone": self._phone,
            # Add room-specific headers
            "roomid": room.room_id,
            "communityId": room.community_id,
            "communityCode": room.community_code,
            "communityName": room.community_name,
            "space-yr": room.community_id,
            "easId": room.eas_id,
            "gateway": room.gateway,
        }
        params = {
            "pageSize": page_size,
            "pageNum": page_num,
            "suitId": "",
        }

        async with async_timeout.timeout(DEFAULT_TIMEOUT):
            response = await self._session.get(
                DEVICE_LIST_URL,
                headers=headers,
                params=params,
            )

            if response.status == 401:
                from .exceptions import AuthenticationError
                raise AuthenticationError("Authentication failed")

            response.raise_for_status()
            response_data = await response.json()

            if response_data.get("code") != 200:
                from .exceptions import BatchQueryError
                error_msg = response_data.get("msg", "Unknown error")
                raise BatchQueryError(
                    f"Device list error: {error_msg}"
                )

            return DeviceList(response_data)

    except asyncio.TimeoutError as error:
        from .exceptions import DeviceTimeoutError
        raise DeviceTimeoutError("Timeout") from error
    except (AuthenticationError, BatchQueryError):
        raise
    except Exception as error:
        from .exceptions import InvalidResponseError
        raise InvalidResponseError(f"Invalid response: {error}") from error
```

**Step 2: Update send_command() to use Room config**

Modify `send_command` in `http_client.py`:

```python
async def send_command(
    self,
    room: Room,
    property_code: str,
    value: Any,
    device_id: str,
    device_name: str,
    product_id: str,
) -> bool:
    """Send command to device.

    Args:
        room: Room configuration for building headers
        property_code: Device property to control
        value: Value to set
        device_id: Target device ID
        device_name: Device name
        product_id: Product ID

    Returns:
        True if successful

    Raises:
        DeviceError: If command fails
        AuthenticationError: If token is invalid
        NetworkError: If network error occurs
    """
    try:
        headers = {
            **FIXED_HEADERS,
            "X-token": self._token,
            "space-phone": self._phone,
            # Add room-specific headers
            "roomid": room.room_id,
            "communityId": room.community_id,
            "communityCode": room.community_code,
            "communityName": room.community_name,
            "space-yr": room.community_id,
            "easId": room.eas_id,
            "gateway": room.gateway,
        }

        url = f"{BASE_URL}/device/HISENSE/{device_id}/enable"
        params = {
            "deviceId": device_id,
            "deviceName": device_name,
        }

        body_data = [{
            "productId": product_id,
            "action": None,
            "deviceAddress": device_id,
            "propertyCode": property_code,
            "value": int(value) if isinstance(value, bool) else value
        }]

        body = json.dumps(body_data)

        async with async_timeout.timeout(DEFAULT_TIMEOUT):
            response = await self._session.post(
                url,
                params=params,
                headers=headers,
                data=body,
            )

            if response.status == 401:
                from .exceptions import AuthenticationError
                raise AuthenticationError("Authentication failed")

            response.raise_for_status()
            return True

    except asyncio.TimeoutError as error:
        from .exceptions import DeviceTimeoutError
        raise DeviceTimeoutError("Timeout") from error
    except (AuthenticationError, DeviceTimeoutError):
        raise
    except Exception as error:
        from .exceptions import InvalidResponseError
        raise InvalidResponseError(f"Invalid response: {error}") from error
```

**Step 3: Run existing tests to check**

```bash
pytest tests/ -v
```

Expected: Some tests may fail (need to update coordinator tests)

**Step 4: Commit**

```bash
git add http_client.py
git commit -m "refactor: update get_device_list and send_command to use Room"
```

---

## Task 5: Update __init__.py to Use entry.runtime_data

**Files:**
- Modify: `__init__.py`

**Step 1: Add type aliases and dataclass**

Add at top of `__init__.py`:

```python
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
```

**Step 2: Update async_setup_entry**

Replace `async_setup_entry` with:

```python
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
```

**Step 3: Update async_unload_entry**

Replace `async_unload_entry` with:

```python
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
```

**Step 4: Commit**

```bash
git add __init__.py
git commit -m "refactor: use entry.runtime_data following HA 2024 best practices"
```

---

## Task 6: Update Coordinator to Accept Room Config

**Files:**
- Modify: `coordinator.py`

**Step 1: Update coordinator __init__**

Modify `__init__` in `coordinator.py`:

```python
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
        always_update=True,
    )

    self._http_client = http_client
    self._room = room  # Store room config
    self._device_ids: set[str] = set()
    self._device_info: dict[str, dict[str, str]] = {}
    self._pending_updates: dict[str, Any] = {}
    self._previous_data: dict[str, Any] = {}
```

**Step 2: Update _async_update_data to use room config**

Modify `_async_update_data` in `coordinator.py`:

```python
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

        if response and hasattr(response, "devices") and response.devices:
            _LOGGER.debug(
                "Successfully fetched %d devices",
                len(response.devices)
            )
        elif not response:
            _LOGGER.warning("Empty API response")
        elif not hasattr(response, "devices"):
            _LOGGER.warning("API response missing devices attribute")
        elif not response.devices:
            _LOGGER.warning("No devices in response")

        return response

    except AuthenticationError as error:
        _LOGGER.error("Auth failed, triggering reauth: %s", error)
        raise ConfigEntryAuthFailed from error
    except BatchQueryError as error:
        _LOGGER.error("Failed to fetch device data: %s", error)
        raise UpdateFailed(f"API error: {error}") from error
```

**Step 3: Update async_send_command**

Modify `async_send_command` in `coordinator.py`:

```python
async def async_send_command(
    self, device_id: str, property_code: str, value: Any
) -> bool:
    """Send command to device."""
    pending_key = f"{device_id}_{property_code}"

    if device_id not in self._device_ids:
        _LOGGER.error("Device %s not registered", device_id)
        return False

    if device_id not in self._device_info:
        _LOGGER.error("Device %s info incomplete", device_id)
        return False

    device_info = self._device_info[device_id]

    try:
        _LOGGER.debug(
            "Sending command: %s = %s to device %s",
            property_code,
            value,
            device_id,
        )

        self._pending_updates[pending_key] = value

        # Use room config from coordinator
        success = await self._http_client.send_command(
            room=self._room,
            property_code=property_code,
            value=value,
            device_id=device_id,
            device_name=device_info.get("device_name", ""),
            product_id=device_info.get("product_id", ""),
        )

        if success:
            await self.async_request_refresh()
            _LOGGER.debug("Command sent successfully")
            return True

        return False

    except DeviceError as error:
        _LOGGER.error("Command failed: %s", error)
        return False
    finally:
        if pending_key in self._pending_updates:
            del self._pending_updates[pending_key]
```

**Step 4: Commit**

```bash
git add coordinator.py
git commit -m "refactor: coordinator uses Room config for API calls"
```

---

## Task 7: Update Entities to Use runtime_data

**Files:**
- Modify: `light.py`
- Modify: `climate.py`

**Step 1: Update light.py async_setup_entry**

Modify `async_setup_entry` in `light.py`:

```python
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
```

**Step 2: Update HisenseLight __init__**

Modify `HisenseLight.__init__` in `light.py`:

```python
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

    self._attr_supported_color_modes = {ColorMode.ONOFF}
    self._attr_color_mode = ColorMode.ONOFF
    self._set_icon()

    self._attr_device_info = {
        "identifiers": {(DOMAIN, self._attr_unique_id)},
        "name": name,
        "manufacturer": MANUFACTURER,
        "model": MODEL_LIGHT,
        "suggested_area": room_name if room_name else None,
    }

    self._update_state_from_coordinator()
```

**Step 3: Update climate.py similarly**

Apply similar changes to `climate.py`:
- Update `async_setup_entry` to use `entry.runtime_data`
- Update `HisenseClimate.__init__` to accept and store `room` parameter

**Step 4: Commit**

```bash
git add light.py climate.py
git commit -m "refactor: entities use runtime_data and Room config"
```

---

## Task 8: Update Config Flow

**Files:**
- Modify: `config_flow.py`

**Step 1: Add flow state dataclass and update flow**

Replace `config_flow.py` with:

```python
"""Config flow for C&D Iot integration."""
import logging
import voluptuous as vol

from dataclasses import dataclass, field
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN
from .auth_client import AuthClient
from .http_client import HttpClient
from .models import Room, RoomList

_LOGGER = logging.getLogger(__name__)

@dataclass
class FlowState:
    """Config flow state."""
    phone: str
    token_bundle: dict[str, str] = field(default_factory=dict)
    room_config: Room | None = None

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for C&D Iot."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._flow_state: FlowState | None = None

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            return await self.async_step_phone()
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    async def async_step_phone(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Input phone number and request SMS code."""
        errors: dict[str, str] = {}

        if user_input is not None:
            phone = str(user_input.get("phone", "")).strip()
            if phone:
                try:
                    client = AuthClient(self.hass)
                    await client.request_code(phone)
                    self._flow_state = FlowState(phone=phone)
                    return await self.async_step_code()
                except Exception as err:
                    _LOGGER.exception("Failed to request SMS code")
                    errors["base"] = "cannot_connect"
            else:
                errors["phone"] = "required"

        return self.async_show_form(
            step_id="phone",
            data_schema=vol.Schema({vol.Required("phone"): str}),
            errors=errors,
        )

    async def async_step_code(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Input SMS code, login, and fetch room config."""
        errors: dict[str, str] = {}

        if user_input is not None:
            code = str(user_input.get("code", "")).strip()
            if not code:
                errors["code"] = "required"
            else:
                try:
                    # Login
                    client = AuthClient(self.hass)
                    token_bundle = await client.login(
                        self._flow_state.phone, code
                    )

                    # Fetch room config
                    http_client = HttpClient(
                        self.hass,
                        x_token=token_bundle["access_token"],
                        phone=self._flow_state.phone,
                    )
                    room_list = await http_client.get_room_list()

                    if not room_list.rooms:
                        errors["base"] = "no_rooms"
                    else:
                        room_config = room_list.first_room
                        self._flow_state.token_bundle = token_bundle
                        self._flow_state.room_config = room_config

                        # Create entry with only auth data
                        return self.async_create_entry(
                            title=f"C&D IoT {room_config.room_name}",
                            data={
                                "auth": {
                                    "phone": self._flow_state.phone,
                                    "access_token": token_bundle["access_token"],
                                    "refresh_token": token_bundle.get("refresh_token", ""),
                                    "expires_in": token_bundle.get("expires_in", 10080),
                                }
                            }
                        )

                except Exception as err:
                    _LOGGER.exception("Login or get room failed")
                    errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="code",
            data_schema=vol.Schema({vol.Required("code"): str}),
            errors=errors,
        )

    async def async_step_reauth(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Trigger re-authentication flow."""
        entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        phone = entry.data["auth"]["phone"]

        self._flow_state = FlowState(phone=phone)

        # Auto send code
        try:
            client = AuthClient(self.hass)
            await client.request_code(phone)
        except Exception as err:
            _LOGGER.warning("Auto send code failed: %s", err)

        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Handle re-authentication confirmation."""
        errors: dict[str, str] = {}

        if user_input is not None:
            code = str(user_input.get("code", "")).strip()
            if not code:
                errors["code"] = "required"
            else:
                try:
                    client = AuthClient(self.hass)
                    token_bundle = await client.login(
                        self._flow_state.phone, code
                    )

                    http_client = HttpClient(
                        self.hass,
                        x_token=token_bundle["access_token"],
                        phone=self._flow_state.phone,
                    )
                    room_list = await http_client.get_room_list()
                    room_config = room_list.first_room

                    # Update entry
                    entry = self.hass.config_entries.async_get_entry(
                        self.context["entry_id"]
                    )
                    new_data = {
                        **entry.data,
                        "auth": {
                            "phone": self._flow_state.phone,
                            **token_bundle,
                        }
                    }
                    self.hass.config_entries.async_update_entry(
                        entry, data=new_data
                    )

                    await self.hass.config_entries.async_reload(entry.entry_id)
                    return self.async_abort(reason="reauth_successful")

                except Exception as err:
                    _LOGGER.exception("Reauth failed")
                    errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required("code"): str}),
            errors=errors,
        )
```

**Step 2: Update translations**

Update `translations/en.json`:

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Set up C&D IoT",
        "description": "Login with SMS verification"
      },
      "phone": {
        "title": "Phone Number",
        "data": {
          "phone": "Phone Number"
        }
      },
      "code": {
        "title": "Verification Code",
        "description": "Enter the SMS code sent to your phone",
        "data": {
          "code": "Verification Code"
        }
      },
      "reauth_confirm": {
        "title": "Reauthentication Required",
        "description": "Your token has expired. Please enter the SMS code.",
        "data": {
          "code": "Verification Code"
        }
      }
    },
    "error": {
      "cannot_connect": "Failed to connect",
      "invalid_auth": "Invalid code",
      "no_rooms": "No rooms found"
    },
    "abort": {
      "reauth_successful": "Reauthentication successful"
    }
  }
}
```

**Step 3: Commit**

```bash
git add config_flow.py translations/en.json
git commit -m "feat: update config flow to fetch room config from API"
```

---

## Task 9: Update translations for Chinese

**Files:**
- Modify: `translations/zh-Hans.json`

**Step 1: Update Chinese translations**

```json
{
  "config": {
    "step": {
      "user": {
        "title": "设置 C&D IoT",
        "description": "使用短信验证码登录"
      },
      "phone": {
        "title": "手机号码",
        "data": {
          "phone": "手机号码"
        }
      },
      "code": {
        "title": "验证码",
        "description": "请输入发送到您手机的短信验证码",
        "data": {
          "code": "验证码"
        }
      },
      "reauth_confirm": {
        "title": "需要重新认证",
        "description": "您的令牌已过期，请输入短信验证码",
        "data": {
          "code": "验证码"
        }
      }
    },
    "error": {
      "cannot_connect": "连接失败",
      "invalid_auth": "验证码错误",
      "no_rooms": "未找到房间"
    },
    "abort": {
      "reauth_successful": "重新认证成功"
    }
  }
}
```

**Step 2: Commit**

```bash
git add translations/zh-Hans.json
git commit -m "i18n: update Chinese translations"
```

---

## Task 10: Clean Up Test Files

**Files:**
- Delete: `test_api.py`

**Step 1: Remove test script**

```bash
rm test_api.py
```

**Step 2: Commit**

```bash
git add test_api.py
git commit -m "chore: remove test script"
```

---

## Task 11: Run Full Test Suite

**Step 1: Run all tests**

```bash
pytest tests/ -v
```

**Step 2: Fix any failing tests**

If tests fail, update them to match new implementation.

**Step 3: Commit test fixes**

```bash
git add tests/
git commit -m "test: fix tests for new implementation"
```

---

## Task 12: Final Verification

**Step 1: Verify no hardcoded config remains**

```bash
grep -r "13800138000" --include="*.py" | grep -v "test_" | grep -v ".pyc"
```

Expected: No results (or only in tests)

**Step 2: Verify imports work**

```bash
python3 -c "from custom_components.jianfa_iot import JianfaIotConfigEntry; from custom_components.jianfa_iot.models import Room; print('Imports OK')"
```

**Step 3: Create summary commit**

```bash
git add .
git commit -m "feat: complete dynamic config from API implementation

- Removed hardcoded configuration from const.py
- Added Room and RoomList data models
- HttpClient now fetches room config after login
- Config flow retrieves room list automatically
- Uses entry.runtime_data (HA 2024 best practices)
- Only auth data stored in entry.data
- Room config fetched fresh on each setup"
```

---

## Testing Checklist

After implementation, verify:

- [ ] New integration setup works (phone → SMS code → devices discovered)
- [ ] Existing users can reload without errors
- [ ] Token expiry triggers re-auth flow
- [ ] Re-auth successfully updates config
- [ ] Light controls work
- [ ] Climate controls work
- [ ] No hardcoded credentials in code
- [ ] All tests pass
