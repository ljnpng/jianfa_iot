"""Integration tests for background verification."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.jianfa_iot.coordinator import JianfaIotDataCoordinator
from custom_components.jianfa_iot.light import HisenseLight
from custom_components.jianfa_iot.models import Device, DeviceState


@pytest.mark.asyncio
async def test_light_turn_on_with_verification():
    """Test complete flow: turn on light with verification."""
    # Setup
    hass = MagicMock()
    http_client = MagicMock()
    http_client.send_command = AsyncMock(return_value=True)

    coordinator = JianfaIotDataCoordinator(hass, http_client, MagicMock())

    # Create mock device
    device_data = {
        "deviceId": "light_1",
        "deviceName": "Test Light",
        "productId": "connector.device.type.smartSwitch.c4",
        "currentState": '{"PowerSwitch": 0}',
    }
    device = Device(device_data)

    coordinator.data = MagicMock()
    coordinator.data.devices = [device]
    coordinator.async_get_device_property = MagicMock(return_value=0)

    # Create light entity
    light = HisenseLight(
        coordinator,
        MagicMock(),
        "Test Light",
        "light_1",
        "Test Light",
        "Living Room",
    )

    # Act - turn on
    await light.async_turn_on()

    # Assert - UI updated immediately
    assert light.is_on is True

    # Assert - command sent
    http_client.send_command.assert_called_once()

    # Assert - verification queued
    assert not coordinator._verification_queue.empty()

    # Simulate verification success
    coordinator.async_get_device_property = MagicMock(return_value=1)
    await coordinator.async_refresh()

    # Trigger coordinator update
    light._handle_coordinator_update()

    # Assert - light still on (state consistent)
    assert light.is_on is True


@pytest.mark.asyncio
async def test_light_skips_update_when_verification_pending():
    """Test that entity ignores coordinator updates when verification is pending."""
    # Setup
    hass = MagicMock()
    http_client = MagicMock()
    coordinator = JianfaIotDataCoordinator(hass, http_client, MagicMock())

    # Create device with OFF state
    device_data = {
        "deviceId": "light_1",
        "deviceName": "Test Light",
        "productId": "connector.device.type.smartSwitch.c4",
        "currentState": '{"PowerSwitch": 0}',
    }
    device = Device(device_data)

    coordinator.data = MagicMock()
    coordinator.data.devices = [device]
    coordinator.async_get_device_property = MagicMock(return_value=0)

    light = HisenseLight(
        coordinator,
        MagicMock(),
        "Test Light",
        "light_1",
        "Test Light",
        "Living Room",
    )

    # Turn on (verification starts)
    await light.async_turn_on()
    assert light.is_on is True

    # Verification is still pending (status = None)
    assert coordinator.get_verification_status("light_1", "PowerSwitch") is None

    # Coordinator returns old state (still 0)
    coordinator.async_get_device_property = MagicMock(return_value=0)

    # Trigger coordinator update
    light._handle_coordinator_update()

    # Assert - entity ignores the update, maintains optimistic state
    assert light.is_on is True
