"""Integration tests for background verification."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.jianfa_iot.coordinator import DeviceCoordinator
from custom_components.jianfa_iot.light import HisenseLight
from custom_components.jianfa_iot.models import Device, DeviceState


def create_mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.data = {}
    return hass


@pytest.mark.asyncio
async def test_light_turn_on_with_verification():
    """Test complete flow: turn on light with verification."""
    # Setup
    hass = create_mock_hass()
    http_client = MagicMock()
    http_client.send_command = AsyncMock(return_value=True)
    room = MagicMock()

    coordinator = DeviceCoordinator(
        hass, http_client, room,
        device_id="light_1",
        device_name="Test Light",
        product_id="connector.device.type.smartSwitch.c4",
    )

    # Create mock device data
    device_data = {
        "deviceId": "light_1",
        "deviceName": "Test Light",
        "productId": "connector.device.type.smartSwitch.c4",
        "currentState": '{"PowerSwitch": 0}',
    }
    device = Device(device_data)
    coordinator.data = device

    # Create light entity
    light = HisenseLight(
        coordinator,
        room,
        "Test Light",
        "light_1",
        "Test Light",
        "Living Room",
    )
    # Mock hass attribute to avoid RuntimeError
    light.hass = hass

    # Act - turn on
    await light.async_turn_on()

    # Assert - UI updated immediately
    assert light.is_on is True

    # Assert - command sent
    http_client.send_command.assert_called_once()

    # Assert - verification status is pending
    assert coordinator.get_verification_status("PowerSwitch") == "pending"


@pytest.mark.asyncio
async def test_light_skips_update_when_verification_pending():
    """Test that entity ignores coordinator updates when verification is pending."""
    # Setup
    hass = create_mock_hass()
    http_client = MagicMock()
    http_client.send_command = AsyncMock(return_value=True)
    room = MagicMock()

    coordinator = DeviceCoordinator(
        hass, http_client, room,
        device_id="light_1",
        device_name="Test Light",
        product_id="connector.device.type.smartSwitch.c4",
    )

    # Create device with OFF state
    device_data = {
        "deviceId": "light_1",
        "deviceName": "Test Light",
        "productId": "connector.device.type.smartSwitch.c4",
        "currentState": '{"PowerSwitch": 0}',
    }
    device = Device(device_data)
    coordinator.data = device

    light = HisenseLight(
        coordinator,
        room,
        "Test Light",
        "light_1",
        "Test Light",
        "Living Room",
    )
    light.hass = hass

    # Turn on (verification starts, status becomes "pending")
    await light.async_turn_on()
    assert light.is_on is True

    # Verification is pending
    assert coordinator.get_verification_status("PowerSwitch") == "pending"

    # Trigger coordinator update - should be ignored because pending
    light._handle_coordinator_update()

    # Assert - entity ignores the update, maintains optimistic state
    assert light.is_on is True


@pytest.mark.asyncio
async def test_light_accepts_update_when_no_verification():
    """Test that entity accepts coordinator updates when no verification is pending."""
    # Setup
    hass = create_mock_hass()
    http_client = MagicMock()
    room = MagicMock()

    coordinator = DeviceCoordinator(
        hass, http_client, room,
        device_id="light_1",
        device_name="Test Light",
        product_id="connector.device.type.smartSwitch.c4",
    )

    # Create device with ON state
    device_data = {
        "deviceId": "light_1",
        "deviceName": "Test Light",
        "productId": "connector.device.type.smartSwitch.c4",
        "currentState": '{"PowerSwitch": 1}',
    }
    device = Device(device_data)
    coordinator.data = device

    light = HisenseLight(
        coordinator,
        room,
        "Test Light",
        "light_1",
        "Test Light",
        "Living Room",
    )
    light.hass = hass

    # Initially off (from init before data was set)
    light._attr_is_on = False

    # No verification pending (status is None)
    assert coordinator.get_verification_status("PowerSwitch") is None

    # Trigger coordinator update - should be accepted
    light._handle_coordinator_update()

    # Assert - entity accepts the update from coordinator
    assert light.is_on is True
