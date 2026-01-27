# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Home Assistant custom integration for C&D (HISENSE) IoT smart home devices. It provides support for smart lights and air conditioners through the cloud API.

## Development Commands

### Testing
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_specific_file.py

# Run with verbose output
pytest -v
```

### Home Assistant Development
```bash
# Copy to Home Assistant config
cp -r /path/to/jianfa_iot ~/.homeassistant/custom_components/

# Restart Home Assistant
hassctl restart
# or
sudo systemctl restart home-assistant

# Check logs
journalctl -u home-assistant -f
# or
tail -f ~/.homeassistant/home-assistant.log
```

## Architecture

### Core Components

**HttpClient** (`http_client.py`): Manages all HTTP communication with the cloud API. Handles authentication via X-token header, device state queries, and command sending. Uses `aiohttp` for async operations.

**AuthClient** (`auth_client.py`): Handles SMS-based authentication flow. Requests verification codes and exchanges them for access/refresh tokens.

**JianfaIotDataCoordinator** (`coordinator.py`): Single global coordinator that polls all device states every 5 seconds. Implements:
- State caching and change detection
- Command queuing and pending state tracking
- Per-device registration system
- Protection windows to prevent coordinator updates from overriding pending commands

**ConfigFlow** (`config_flow.py`): Multi-step authentication flow:
1. Phone number input → SMS code request
2. SMS code input → Login and token retrieval
3. Device discovery → Automatic device setup
4. Re-authentication support for expired tokens

### Data Models

**Device** (`models.py`): Core device model with state parsing. Device type determined by `product_id`:
- `connector.device.type.smartSwitch.c4` → Light
- `connector.device.type.aircondition` → Air Conditioner

**DeviceState** (`models.py`): Parses JSON state string containing:
- `PowerSwitch`: 0/1 for on/off
- `TemperatureSet`: Target temperature (AC only)
- `WorkMode`: Operating mode (AC only)
- `Windspeed`: Fan speed (AC only)

**DeviceList** (`models.py`): Container for paginated device list responses.

### Entity Implementation

**HisenseLight** (`light.py`): ON/OFF control with:
- State protection window (10s) after commands to prevent coordinator sync issues
- Remote state verification before sending commands to avoid redundant operations
- Immediate UI feedback with optimistic state updates

**HisenseClimate** (`climate.py`): Full climate control with:
- Multi-property command protection windows (power, mode, temperature, fan speed)
- HVAC mode mapping (COOL/HEAT/DRY/FAN_ONLY)
- Fan speed mapping (AUTO/LOW/MEDIUM/HIGH)
- Auto power-on when setting properties while device is off

## Key Design Patterns

### State Protection Windows
Both lights and climate implement "command protection windows" - a period after sending commands (default 10s) where coordinator updates are ignored. This prevents the cloud API's delayed state responses from overriding the user's intended changes.

### Optimistic Updates
Entities update their local state immediately when commands are sent, rather than waiting for coordinator confirmation. This provides responsive UI while the protection window prevents stale cloud data from reverting it.

### Single Coordinator Pattern
One coordinator instance manages all devices, with individual entities registering themselves via `register_device()`. The coordinator tracks pending commands per-property to prevent conflicts.

### Device Type Detection
Device type is determined by `product_id` matching constants in `const.py`, not by `deviceType` field which may be unreliable.

## Configuration

### Stored in Config Entry
```python
{
    "devices": [
        {
            "productId": "...",
            "deviceId": "...",
            "deviceName": "...",
            "suitName": "...",  # Room name
            "currentState": "{JSON state string}",
            # ... other device fields
        }
    ],
    "auth": {
        "phone": "13800138000",  # Test phone number
        "access_token": "...",
        "refresh_token": "...",
        "expires_in": ...
    }
}
```

### API Endpoints
- Base URL: `https://sqdn.cndmega.com/prod-v2.0.1/smart/mini/smart`
- Device list: `{BASE_URL}/device/list`
- Device control: `{BASE_URL}/device/HISENSE/{device_id}/enable`
- Auth base: `https://sqdn.cndmega.com/prod-v2.0.1/auth/owner`
- Get code: `{AUTH_BASE_URL}/code`
- Login: `{AUTH_BASE_URL}/login`

### Required Headers
All requests include fixed headers from `AUTH_HEADERS` in `const.py` plus the dynamic `X-token` from auth flow.

## Services

Three services are registered for manual authentication management:

1. `jianfa_iot.request_sms_code` - Triggers SMS verification for stored phone number
2. `jianfa_iot.set_access_token` - Manually update X-token
3. `jianfa_iot.login_with_code` - Complete SMS login flow

Call these via Developer Tools → Services in Home Assistant UI.

## Common Issues

**Authentication errors**: Token expires frequently. Use re-auth flow or `login_with_code` service.

**Device not responding**: Check device is online in cloud app. State queries may lag behind actual state.

**State sync issues**: The protection window (10s) helps but if cloud state is very stale, entities may temporarily show incorrect state.

**New device types**: Add new `DEVICE_TYPE_*` constant to `const.py` and corresponding platform file. Update `Device.is_*` properties in `models.py`.
