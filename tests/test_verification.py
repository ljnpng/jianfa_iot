"""Tests for background verification logic."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.jianfa_iot.coordinator import DeviceCoordinator


@pytest.mark.asyncio
async def test_send_command_with_verify_queues_verification():
    """Test that send_command_with_verify queues a verification task."""
    # Setup
    hass = MagicMock()
    http_client = MagicMock()
    http_client.send_command = AsyncMock(return_value=True)
    room = MagicMock()

    coordinator = DeviceCoordinator(
        hass, http_client, room,
        device_id="test_device",
        device_name="Test Device",
        product_id="product_123",
    )

    # Act
    result = await coordinator.async_send_command_with_verify("PowerSwitch", 1)

    # Assert
    assert result is True
    assert not coordinator._verification_queue.empty()

    property_code, value = coordinator._verification_queue.get_nowait()
    assert property_code == "PowerSwitch"
    assert value == 1


@pytest.mark.asyncio
async def test_send_command_with_verify_starts_processor():
    """Test that verification queue processor is started."""
    # Setup
    hass = MagicMock()
    http_client = MagicMock()
    http_client.send_command = AsyncMock(return_value=True)
    room = MagicMock()

    coordinator = DeviceCoordinator(
        hass, http_client, room,
        device_id="test_device",
        device_name="Test Device",
        product_id="product_123",
    )

    # Act
    await coordinator.async_send_command_with_verify("PowerSwitch", 1)
    await asyncio.sleep(0.1)  # Let task start

    # Assert
    assert coordinator._verification_task is not None
    assert not coordinator._verification_task.done()


@pytest.mark.asyncio
async def test_verification_status_pending():
    """Test verification status is set to pending when command is sent."""
    # Setup
    hass = MagicMock()
    http_client = MagicMock()
    http_client.send_command = AsyncMock(return_value=True)
    room = MagicMock()

    coordinator = DeviceCoordinator(
        hass, http_client, room,
        device_id="device1",
        device_name="Test Device",
        product_id="product_123",
    )

    # Act & Assert - not set yet
    assert coordinator.get_verification_status("PowerSwitch") is None

    # Send command - should set to pending
    await coordinator.async_send_command_with_verify("PowerSwitch", 1)

    # Assert - now pending
    assert coordinator.get_verification_status("PowerSwitch") == "pending"


@pytest.mark.asyncio
async def test_get_verification_status():
    """Test get_verification_status returns correct status."""
    # Setup
    hass = MagicMock()
    http_client = MagicMock()
    room = MagicMock()

    coordinator = DeviceCoordinator(
        hass, http_client, room,
        device_id="device1",
        device_name="Test Device",
        product_id="product_123",
    )

    # Act & Assert - None when not set
    assert coordinator.get_verification_status("PowerSwitch") is None

    # Set to pending
    coordinator.set_verification_pending("PowerSwitch")
    assert coordinator.get_verification_status("PowerSwitch") == "pending"

    # Manually set to confirmed
    coordinator._verification_status["PowerSwitch"] = "confirmed"
    assert coordinator.get_verification_status("PowerSwitch") == "confirmed"

    # Manually set to timeout
    coordinator._verification_status["PowerSwitch"] = "timeout"
    assert coordinator.get_verification_status("PowerSwitch") == "timeout"
