"""Tests for background verification logic."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.jianfa_iot.coordinator import JianfaIotDataCoordinator


@pytest.mark.asyncio
async def test_send_command_with_verify_queues_verification():
    """Test that send_command_with_verify queues a verification task."""
    # Setup
    hass = MagicMock()
    http_client = MagicMock()
    http_client.send_command = AsyncMock(return_value=True)

    coordinator = JianfaIotDataCoordinator(hass, http_client, MagicMock())
    coordinator.register_device("test_device", "Test Device", "product_123")

    # Act
    result = await coordinator.async_send_command_with_verify(
        "test_device", "PowerSwitch", 1
    )

    # Assert
    assert result is True
    assert not coordinator._verification_queue.empty()

    device_id, property_code, value = coordinator._verification_queue.get_nowait()
    assert device_id == "test_device"
    assert property_code == "PowerSwitch"
    assert value == 1


@pytest.mark.asyncio
async def test_send_command_with_verify_starts_processor():
    """Test that verification queue processor is started."""
    # Setup
    hass = MagicMock()
    http_client = MagicMock()
    http_client.send_command = AsyncMock(return_value=True)

    coordinator = JianfaIotDataCoordinator(hass, http_client, MagicMock())
    coordinator.register_device("test_device", "Test Device", "product_123")

    # Act
    await coordinator.async_send_command_with_verify(
        "test_device", "PowerSwitch", 1
    )
    await asyncio.sleep(0.1)  # Let task start

    # Assert
    assert coordinator._verification_task is not None
    assert not coordinator._verification_task.done()


@pytest.mark.asyncio
async def test_is_verification_confirmed():
    """Test verification status query."""
    # Setup
    hass = MagicMock()
    http_client = MagicMock()
    coordinator = JianfaIotDataCoordinator(hass, http_client, MagicMock())

    # Act & Assert - not verified yet
    assert not coordinator.is_verification_confirmed("device1", "PowerSwitch")

    # Mark as confirmed
    coordinator._verification_results["device1_PowerSwitch"] = "confirmed"

    # Assert - now confirmed
    assert coordinator.is_verification_confirmed("device1", "PowerSwitch")


@pytest.mark.asyncio
async def test_get_verification_status():
    """Test get_verification_status returns correct status."""
    # Setup
    hass = MagicMock()
    http_client = MagicMock()
    coordinator = JianfaIotDataCoordinator(hass, http_client, MagicMock())

    # Act & Assert
    assert coordinator.get_verification_status("device1", "PowerSwitch") is None

    coordinator._verification_results["device1_PowerSwitch"] = "confirmed"
    assert coordinator.get_verification_status("device1", "PowerSwitch") == "confirmed"

    coordinator._verification_results["device1_PowerSwitch"] = "timeout"
    assert coordinator.get_verification_status("device1", "PowerSwitch") == "timeout"
