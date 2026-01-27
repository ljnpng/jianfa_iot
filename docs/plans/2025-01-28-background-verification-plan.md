# Background Silent Verification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the 10-second protection window with an active background verification mechanism that polls device state after commands are sent, using exponential backoff (2s, 4s, 8s, 16s) until confirmation or 30-second timeout.

**Architecture:**
- Coordinator layer manages verification queue and state tracking
- Verification tasks run independently in background using asyncio
- Entity layer checks verification status before accepting coordinator updates
- No user-facing changes - verification is silent and optimistic

**Tech Stack:**
- Python asyncio for concurrent background tasks
- Home Assistant Coordinator pattern
- Existing aiohttp-based HTTP client

---

## Overview

### Current State
- 10-second "protection window" after commands prevents stale API state from overriding optimistic UI updates
- No confirmation that commands actually executed on devices
- Fixed window time is arbitrary and may be too short or too long

### Desired State
- Commands trigger immediate UI update (optimistic)
- Background verification polls device state with exponential backoff
- Verification results tracked per-device, per-property
- Entities only accept coordinator updates after verification confirmed
- Silent logging for timeout cases - no user disruption

### Key Design Decisions
1. **Verification failure**: Silent logging, maintain optimistic state (user experience priority)
2. **Verification flow**: Independent of coordinator polling (decoupled design)
3. **Backoff strategy**: Exponential (2s, 4s, 8s, 16s) with 30s total timeout
4. **After confirmation**: Keep full protection period (conservative, prevents delayed responses)
5. **After timeout**: Silent marking, maintain optimistic state
6. **Logic placement**: Coordinator layer (HA best practice)
7. **Concurrency**: Queue-based verification (sequential, avoids races)
8. **State tracking**: Simple dictionary + queue (YAGNI)
9. **Protection window**: Remove entirely, replaced by verification status check
10. **Sync mechanism**: Entity queries verification status on coordinator update

---

## Task 1: Add Verification State Management to Coordinator

**Files:**
- Modify: `custom_components/jianfa_iot/coordinator.py`

**Step 1: Add verification state attributes to __init__**

Add to `JianfaIotDataCoordinator.__init__` after existing attributes:

```python
# Verification state management
self._verification_results: Dict[str, str] = {}  # {f"{device_id}_{property}": "confirmed" | "timeout"}
self._verification_queue: asyncio.Queue = asyncio.Queue()
self._verification_task: asyncio.Task | None = None
self._verification_lock = asyncio.Lock()
```

**Step 2: Run tests to verify no regressions**

Run: `pytest tests/ -v`
Expected: All existing tests pass

**Step 3: Commit**

```bash
git add custom_components/jianfa_iot/coordinator.py
git commit -m "feat: add verification state attributes to coordinator"
```

---

## Task 2: Implement Verification Queue Processor

**Files:**
- Modify: `custom_components/jianfa_iot/coordinator.py`

**Step 1: Add queue processor method**

Add after `async_force_refresh` method:

```python
async def _verification_queue_processor(self) -> None:
    """Background task: Process verification queue sequentially.

    Only one verification runs at a time to avoid API flooding.
    Tasks are processed in FIFO order.
    """
    _LOGGER.info("Verification queue processor started")

    while True:
        # Get verification task from queue
        device_id, property_code, expected_value = await self._verification_queue.get()

        async with self._verification_lock:
            await self._verify_with_exponential_backoff(
                device_id, property_code, expected_value
            )

        # Mark task as done
        self._verification_queue.task_done()

        # If queue is empty and we want to stop the processor, break here
        # For now, keep it running indefinitely
```

**Step 2: Add exponential backoff verification method**

Add after the queue processor:

```python
async def _verify_with_exponential_backoff(
    self,
    device_id: str,
    property_code: str,
    expected_value: Any,
) -> None:
    """Verify device state change using exponential backoff polling.

    Polls at intervals: 2s, 4s, 8s, 16s (total ~30s timeout)

    Args:
        device_id: Device identifier
        property_code: Property being changed
        expected_value: Expected value after command
    """
    key = f"{device_id}_{property_code}"
    delays = [2, 4, 8, 16]

    _LOGGER.debug(
        "Starting verification for %s: expected %s",
        key,
        expected_value,
    )

    for delay in delays:
        await asyncio.sleep(delay)

        try:
            # Force refresh to get latest state
            await self.async_refresh()

            # Check remote state
            actual_value = self.async_get_device_property(device_id, property_code)

            if actual_value == expected_value:
                # Verification successful
                self._verification_results[key] = "confirmed"
                _LOGGER.info(
                    "Verification confirmed: %s = %s after %d seconds",
                    key,
                    expected_value,
                    sum(delays[:delays.index(delay) + 1]),
                )
                return
            else:
                _LOGGER.debug(
                    "Verification pending for %s: expected %s, got %s",
                    key,
                    expected_value,
                    actual_value,
                )

        except Exception as e:
            _LOGGER.warning("Verification query failed for %s: %s", key, e)

    # Timeout - all delays exhausted
    self._verification_results[key] = "timeout"
    _LOGGER.warning(
        "Verification timeout for %s: expected %s not confirmed after 30s",
        key,
        expected_value,
    )
```

**Step 3: Run tests**

Run: `pytest tests/ -v`
Expected: All tests pass (new code not yet called)

**Step 4: Commit**

```bash
git add custom_components/jianfa_iot/coordinator.py
git commit -m "feat: add verification queue processor with exponential backoff"
```

---

## Task 3: Implement Public Verification API

**Files:**
- Modify: `custom_components/jianfa_iot/coordinator.py`

**Step 1: Add async_send_command_with_verify method**

Modify existing `async_send_command` method to also support verification, or add new method. Add new method:

```python
async def async_send_command_with_verify(
    self,
    device_id: str,
    property_code: str,
    value: Any,
) -> bool:
    """Send command and start background verification.

    Args:
        device_id: Device identifier
        property_code: Property to control
        value: Value to set

    Returns:
        True if command was sent successfully (does not wait for verification)
    """
    if device_id not in self._device_ids:
        _LOGGER.error("Device %s not registered to coordinator", device_id)
        return False

    if device_id not in self._device_info:
        _LOGGER.error("Device %s info incomplete", device_id)
        return False

    device_info = self._device_info[device_id]
    key = f"{device_id}_{property_code}"

    try:
        # Send the command
        success = await self._http_client.send_command(
            property_code=property_code,
            value=value,
            device_id=device_id,
            device_name=device_info.get("device_name", ""),
            product_id=device_info.get("product_id", ""),
        )

        if success:
            # Queue verification task
            await self._verification_queue.put((device_id, property_code, value))

            # Ensure queue processor is running
            if self._verification_task is None or self._verification_task.done():
                self._verification_task = asyncio.create_task(
                    self._verification_queue_processor()
                )
                _LOGGER.debug("Started verification queue processor")

            _LOGGER.debug(
                "Command sent for %s, verification queued",
                key,
            )
            return True

        return False

    except Exception as error:
        _LOGGER.error(
            "Failed to send command for %s with value %s: %s",
            key,
            value,
            error,
        )
        return False
```

**Step 2: Add verification status query methods**

Add after `get_pending_value` method:

```python
def is_verification_confirmed(
    self,
    device_id: str,
    property_code: str,
) -> bool:
    """Check if verification has been confirmed successful.

    Args:
        device_id: Device identifier
        property_code: Property code

    Returns:
        True if verification confirmed, False otherwise
    """
    key = f"{device_id}_{property_code}"
    return self._verification_results.get(key) == "confirmed"


def get_verification_status(
    self,
    device_id: str,
    property_code: str,
) -> str | None:
    """Get verification status for a device property.

    Args:
        device_id: Device identifier
        property_code: Property code

    Returns:
        "confirmed" | "timeout" | None (not yet verified)
    """
    key = f"{device_id}_{property_code}"
    return self._verification_results.get(key)
```

**Step 3: Run tests**

Run: `pytest tests/ -v`
Expected: All tests pass

**Step 4: Commit**

```bash
git add custom_components/jianfa_iot/coordinator.py
git commit -m "feat: add public verification API (send_command_with_verify, status queries)"
```

---

## Task 4: Update Light Entity to Use Verification

**Files:**
- Modify: `custom_components/jianfa_iot/light.py`

**Step 1: Remove protection window attributes**

Remove these attributes from `HisenseLight.__init__`:
- `self._last_command_time = 0`
- `self._state_protection_window = STATE_PROTECTION_WINDOW`

Also remove the constant at top of file:
- Remove `STATE_PROTECTION_WINDOW = 10.0`

**Step 2: Simplify async_turn_on method**

Replace entire `async_turn_on` method with:

```python
async def async_turn_on(self, **kwargs: Any) -> None:
    """Turn the light on."""
    # Debounce: if already on locally, skip
    if self._attr_is_on:
        _LOGGER.debug(
            "Light %s is already ON locally, skipping",
            self._device_id,
        )
        return

    coordinator = cast(JianfaIotDataCoordinator, self.coordinator)

    # Optimistic update - update UI immediately
    _LOGGER.debug("Turning on light %s", self._device_id)
    self._attr_is_on = True
    self.async_write_ha_state()

    # Send command with background verification
    await coordinator.async_send_command_with_verify(
        self._device_id, PROPERTY_POWER, 1
    )
```

**Step 3: Simplify async_turn_off method**

Replace entire `async_turn_off` method with:

```python
async def async_turn_off(self, **kwargs: Any) -> None:
    """Turn the light off."""
    # Debounce: if already off locally, skip
    if not self._attr_is_on:
        _LOGGER.debug(
            "Light %s is already OFF locally, skipping",
            self._device_id,
        )
        return

    coordinator = cast(JianfaIotDataCoordinator, self.coordinator)

    # Optimistic update - update UI immediately
    _LOGGER.debug("Turning off light %s", self._device_id)
    self._attr_is_on = False
    self.async_write_ha_state()

    # Send command with background verification
    await coordinator.async_send_command_with_verify(
        self._device_id, PROPERTY_POWER, 0
    )
```

**Step 4: Update _handle_coordinator_update to check verification status**

Replace the method with:

```python
@callback
def _handle_coordinator_update(self) -> None:
    """Handle updated data from the coordinator."""
    _LOGGER.debug(
        "Received coordinator update for light %s",
        self._device_id,
    )

    coordinator = cast(JianfaIotDataCoordinator, self.coordinator)

    # Check verification status before accepting update
    verification_status = coordinator.get_verification_status(
        self._device_id, PROPERTY_POWER
    )

    # If verification is still pending or hasn't started, ignore update
    if verification_status is None:
        _LOGGER.debug(
            "Skipping coordinator update for %s: verification not started",
            self._device_id,
        )
        return

    # If verification confirmed, accept the update
    if verification_status == "confirmed":
        _LOGGER.debug(
            "Accepting coordinator update for %s: verification confirmed",
            self._device_id,
        )
        old_state = self._attr_is_on
        self._update_state_from_coordinator()
        new_state = self._attr_is_on

        if old_state != new_state:
            _LOGGER.debug(
                "Light %s state updated: %s -> %s",
                self._device_id,
                "ON" if old_state else "OFF",
                "ON" if new_state else "OFF",
            )

        self.async_write_ha_state()
        return

    # If verification timed out, still update but log warning
    # (maintain optimistic state but eventually sync)
    _LOGGER.debug(
        "Accepting coordinator update for %s: verification timed out, syncing to actual state",
        self._device_id,
    )
    self._update_state_from_coordinator()
    self.async_write_ha_state()
```

**Step 5: Update _update_state_from_coordinator to remove protection window check**

Remove the protection window check at the beginning of the method. The method should now simply update state from coordinator:

```python
def _update_state_from_coordinator(self) -> None:
    """Update state from coordinator data."""
    coordinator = cast(JianfaIotDataCoordinator, self.coordinator)

    if coordinator.data is None:
        _LOGGER.warning("Coordinator data is empty")
        return

    # Get device state
    state = coordinator.async_get_device_property(self._device_id, PROPERTY_POWER)

    if state is not None:
        self._attr_is_on = bool(state)
        _LOGGER.debug(
            "Updated light %s state to: %s",
            self._device_id,
            "ON" if self._attr_is_on else "OFF",
        )
    else:
        _LOGGER.warning("Could not get power state for light %s", self._device_id)
```

**Step 6: Update async_update to remove protection window check**

Remove the protection window check from `async_update` method:

```python
async def async_update(self) -> None:
    """Update the entity."""
    _LOGGER.debug("Manual update for light %s", self._device_id)

    coordinator = cast(JianfaIotDataCoordinator, self.coordinator)

    # Force refresh and update
    if hasattr(coordinator, "async_force_refresh"):
        await coordinator.async_force_refresh()
    else:
        await coordinator.async_request_refresh()

    self._update_state_from_coordinator()
    self.async_write_ha_state()
```

**Step 7: Run tests**

Run: `pytest tests/ -v`
Expected: All tests pass

**Step 8: Commit**

```bash
git add custom_components/jianfa_iot/light.py
git commit -m "refactor(light): use verification status instead of protection window"
```

---

## Task 5: Update Climate Entity to Use Verification

**Files:**
- Modify: `custom_components/jianfa_iot/climate.py`

**Step 1: Remove protection window attributes**

Remove from `HisenseClimate.__init__`:
- `self._last_command_time = {}`
- Remove `self._state_protection_window = COMMAND_PROTECTION_WINDOW`

Also remove constants:
- `COMMAND_PROTECTION_WINDOW = 10.0`
- `COMMAND_DEBOUNCE_TIME = 1.0` (if not used elsewhere)

**Step 2: Simplify async_turn_on method**

Replace with:

```python
async def async_turn_on(self, **kwargs: Any) -> None:
    """Turn the climate device on."""
    if self._attr_hvac_mode != HVACMode.OFF:
        _LOGGER.debug("Device %s is already ON", self._device_id)
        return

    # Optimistic update
    _LOGGER.debug("Turning on device %s", self._device_id)
    old_mode = self._attr_hvac_mode
    self._attr_hvac_mode = HVACMode.COOL
    self._update_hvac_action()
    self._local_state[PROPERTY_POWER] = True
    self.async_write_ha_state()

    # Send command with verification
    success = await self.coordinator.async_send_command_with_verify(
        self._device_id, PROPERTY_POWER, 1
    )

    if not success:
        # Revert on failure
        _LOGGER.error("Failed to turn ON device %s", self._device_id)
        self._attr_hvac_mode = old_mode
        self._update_hvac_action()
        self._local_state[PROPERTY_POWER] = False
        self.async_write_ha_state()
```

**Step 3: Simplify async_turn_off method**

Replace with:

```python
async def async_turn_off(self, **kwargs: Any) -> None:
    """Turn the climate device off."""
    if self._attr_hvac_mode == HVACMode.OFF:
        _LOGGER.debug("Device %s is already OFF", self._device_id)
        return

    # Optimistic update
    _LOGGER.debug("Turning off device %s", self._device_id)
    old_mode = self._attr_hvac_mode
    self._attr_hvac_mode = HVACMode.OFF
    self._attr_hvac_action = HVACAction.OFF
    self._local_state[PROPERTY_POWER] = False
    self.async_write_ha_state()

    # Send command with verification
    success = await self.coordinator.async_send_command_with_verify(
        self._device_id, PROPERTY_POWER, 0
    )

    if not success:
        # Revert on failure
        _LOGGER.error("Failed to turn OFF device %s", self._device_id)
        self._attr_hvac_mode = old_mode
        self._update_hvac_action()
        self._local_state[PROPERTY_POWER] = True
        self.async_write_ha_state()
```

**Step 4: Simplify async_set_hvac_mode method**

Replace method with:

```python
async def async_set_hvac_mode(self, hvac_mode: str) -> None:
    """Set new target hvac mode."""
    # Handle OFF
    if hvac_mode == HVACMode.OFF:
        await self.async_turn_off()
        return

    # Skip if same mode
    if hvac_mode == self._attr_hvac_mode:
        return

    # Ensure device is on
    if not await self._async_ensure_device_on():
        return

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
        success = await self.coordinator.async_send_command_with_verify(
            self._device_id, PROPERTY_MODE, hisense_mode
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
```

**Step 5: Simplify async_set_fan_mode method**

Replace method with:

```python
async def async_set_fan_mode(self, fan_mode: str) -> None:
    """Set new target fan mode."""
    # Skip if same mode
    if fan_mode == self._attr_fan_mode:
        return

    # Ensure device is on
    if not await self._async_ensure_device_on():
        return

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
        success = await self.coordinator.async_send_command_with_verify(
            self._device_id, PROPERTY_FAN_SPEED, hisense_fan_speed
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
```

**Step 6: Simplify async_set_temperature method**

Replace method with:

```python
async def async_set_temperature(self, **kwargs: Any) -> None:
    """Set new target temperature."""
    temperature = kwargs.get("temperature")
    if temperature is None:
        return

    # Clamp temperature
    temperature = max(
        min(int(temperature), self._attr_max_temp), self._attr_min_temp
    )

    # Skip if same temperature
    if temperature == self._attr_target_temperature:
        return

    # Ensure device is on
    if not await self._async_ensure_device_on():
        return

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
    success = await self.coordinator.async_send_command_with_verify(
        self._device_id, PROPERTY_TEMPERATURE, temperature
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
```

**Step 7: Update _handle_coordinator_update to check verification status**

Replace the method with:

```python
@callback
def _handle_coordinator_update(self) -> None:
    """Handle updated data from the coordinator."""
    _LOGGER.debug(
        "Received coordinator update for climate %s",
        self._device_id,
    )

    # Check if any property has pending verification
    has_pending = False
    for property_code in [
        PROPERTY_POWER,
        PROPERTY_MODE,
        PROPERTY_TEMPERATURE,
        PROPERTY_FAN_SPEED,
    ]:
        status = self.coordinator.get_verification_status(
            self._device_id, property_code
        )
        if status is None:  # Verification not started or in progress
            has_pending = True
            _LOGGER.debug(
                "Property %s has pending verification for device %s",
                property_code,
                self._device_id,
            )
            break

    if has_pending:
        # Has pending verifications, skip update to maintain optimistic state
        _LOGGER.debug(
            "Skipping coordinator update for %s: pending verifications",
            self._device_id,
        )
        return

    # All verifications complete (confirmed or timeout), accept update
    _LOGGER.debug(
        "Accepting coordinator update for %s: all verifications complete",
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
```

**Step 8: Simplify _async_update_from_coordinator**

Remove all protection window checks. The method should now be:

```python
@callback
def _async_update_from_coordinator(self) -> None:
    """Update attributes based on coordinator data."""
    # Get power state
    power_state = self.coordinator.async_get_device_property(
        self._device_id, PROPERTY_POWER
    )

    if power_state is not None:
        power_bool = bool(power_state)
        self._local_state[PROPERTY_POWER] = power_bool

        if not power_bool:
            self._attr_hvac_mode = HVACMode.OFF
            self._attr_hvac_action = HVACAction.OFF
            return

    # Device is on, update other properties
    # Mode
    mode = self.coordinator.async_get_device_property(
        self._device_id, PROPERTY_MODE
    )
    if mode is not None and mode in HISENSE_TO_HVAC_MODE:
        self._local_state[PROPERTY_MODE] = mode
        self._attr_hvac_mode = HISENSE_TO_HVAC_MODE[mode]
        self._update_hvac_action()

    # Temperature
    temp = self.coordinator.async_get_device_property(
        self._device_id, PROPERTY_TEMPERATURE
    )
    if temp is not None:
        self._local_state[PROPERTY_TEMPERATURE] = float(temp)
        self._attr_target_temperature = float(temp)

    # Fan speed
    fan_speed = self.coordinator.async_get_device_property(
        self._device_id, PROPERTY_FAN_SPEED
    )
    if fan_speed is not None and fan_speed in HISENSE_TO_FAN_MODE:
        self._local_state[PROPERTY_FAN_SPEED] = fan_speed
        self._attr_fan_mode = HISENSE_TO_FAN_MODE[fan_speed]
```

**Step 9: Update async_update to remove protection window check**

```python
async def async_update(self) -> None:
    """Update the entity."""
    _LOGGER.debug("Manual update for climate %s", self._device_id)

    # Use standard refresh
    await self.coordinator.async_request_refresh()
```

**Step 10: Run tests**

Run: `pytest tests/ -v`
Expected: All tests pass

**Step 11: Commit**

```bash
git add custom_components/jianfa_iot/climate.py
git commit -m "refactor(climate): use verification status instead of protection window"
```

---

## Task 6: Clean Up Unused Code

**Files:**
- Modify: `custom_components/jianfa_iot/coordinator.py`

**Step 1: Remove or deprecate old async_send_command method**

The old `async_send_command` method is no longer used by entities. You can either:
- Remove it entirely, or
- Keep it but mark as deprecated

If removing, delete the method. If keeping, add deprecation notice:

```python
async def async_send_command(
    self, device_id: str, property_code: str, value: Any
) -> bool:
    """Send command to device.

    .. deprecated::
        Use async_send_command_with_verify instead.
        This method does not track verification status.
    """
    # ... existing implementation ...
```

**Step 2: Remove unused pending update tracking**

The `_pending_updates` dict and related methods are no longer needed:
- Remove `self._pending_updates: Dict[str, Any] = {}`
- Remove `is_device_property_pending` method
- Remove `get_pending_value` method (unless kept for backward compatibility)

**Step 3: Remove async_get_remote_state method**

This method is no longer used by entities. Remove it.

**Step 4: Run tests**

Run: `pytest tests/ -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add custom_components/jianfa_iot/coordinator.py
git commit -m "refactor(coordinator): remove unused code after verification implementation"
```

---

## Task 7: Add Tests for Verification Logic

**Files:**
- Create: `tests/test_verification.py`

**Step 1: Write test for verification queue processing**

```python
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

    coordinator = JianfaIotDataCoordinator(hass, http_client)
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

    coordinator = JianfaIotDataCoordinator(hass, http_client)
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
    coordinator = JianfaIotDataCoordinator(hass, http_client)

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
    coordinator = JianfaIotDataCoordinator(hass, http_client)

    # Act & Assert
    assert coordinator.get_verification_status("device1", "PowerSwitch") is None

    coordinator._verification_results["device1_PowerSwitch"] = "confirmed"
    assert coordinator.get_verification_status("device1", "PowerSwitch") == "confirmed"

    coordinator._verification_results["device1_PowerSwitch"] = "timeout"
    assert coordinator.get_verification_status("device1", "PowerSwitch") == "timeout"
```

**Step 2: Run tests**

Run: `pytest tests/test_verification.py -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/test_verification.py
git commit -m "test: add verification logic tests"
```

---

## Task 8: Update Design Documentation

**Files:**
- Create: `docs/design/background-verification-design.md`

**Step 1: Create design document**

```markdown
# Background Silent Verification Design

## Overview

The background silent verification mechanism replaces the fixed 10-second protection window with an active verification system that polls device state after commands are sent.

## Architecture

### Coordinator Layer

The coordinator manages:
- **Verification queue**: FIFO queue of pending verifications
- **Verification results**: Dictionary tracking verification status per-device/property
- **Queue processor**: Background task that processes verifications sequentially

### Entity Layer

Entities:
- Send commands via `async_send_command_with_verify()`
- Check verification status in `_handle_coordinator_update()`
- Only accept coordinator updates after verification is confirmed

## Verification Flow

```
1. User action → Entity command method
2. Optimistic UI update
3. coordinator.async_send_command_with_verify()
4. Command sent to device
5. Verification queued
6. Background processor:
   - Polls at 2s, 4s, 8s, 16s intervals
   - Compares actual vs expected value
   - Records "confirmed" or "timeout"
7. Entity callbacks check verification status
8. Only update UI after confirmation
```

## State Tracking

### Verification Results

```python
_verification_results: {
    "device_id_PowerSwitch": "confirmed" | "timeout",
    "device_id_TemperatureSet": "confirmed" | "timeout",
}
```

### Status Values

- `None`: Verification not started or in progress
- `"confirmed"`: State verified successfully
- `"timeout"`: Verification timed out (30s)

## Key Benefits

1. **No fixed window**: Verification completes as soon as state is confirmed
2. **User experience**: Immediate UI feedback, no waiting
3. **Resilience**: Handles API delays gracefully
4. **Observable**: Logs show verification progress and results
5. **Queue-based**: Prevents API flooding with concurrent verifications
```

**Step 2: Commit**

```bash
git add docs/design/background-verification-design.md
git commit -m "docs: add background verification design document"
```

---

## Task 9: Integration Testing

**Files:**
- Create: `tests/test_integration_verification.py`

**Step 1: Write integration test**

```python
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

    coordinator = JianfaIotDataCoordinator(hass, http_client)

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
    coordinator = JianfaIotDataCoordinator(hass, http_client)

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
```

**Step 2: Run integration tests**

Run: `pytest tests/test_integration_verification.py -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/test_integration_verification.py
git commit -m "test: add integration tests for background verification"
```

---

## Task 10: Final Verification and Cleanup

**Files:**
- Various

**Step 1: Run full test suite**

Run: `pytest tests/ -v --cov=custom_components/jianfa_iot`
Expected: All tests pass with good coverage

**Step 2: Manual smoke test**

Test in actual Home Assistant instance:
1. Install the updated integration
2. Toggle a light on/off
3. Check logs for verification progress
4. Verify light responds immediately
5. Wait for verification confirmation in logs

**Step 3: Check for TODOs or FIXMEs**

Run: `grep -r "TODO\|FIXME" custom_components/jianfa_iot/`
Resolve any found items, or create issues for future work.

**Step 4: Update project documentation**

Update any relevant README or CHANGELOG to document the new verification mechanism.

**Step 5: Final commit**

```bash
git add .
git commit -m "feat: complete background silent verification implementation"
```

---

## Summary

This implementation:

1. ✅ Adds verification queue and state tracking to coordinator
2. ✅ Implements exponential backoff polling (2s, 4s, 8s, 16s)
3. ✅ Provides verification status query APIs
4. ✅ Updates Light entity to use verification
5. ✅ Updates Climate entity to use verification
6. ✅ Removes old protection window mechanism
7. ✅ Adds comprehensive tests
8. ✅ Documents the new design

**Result**: Users get immediate UI feedback, with background confirmation that commands actually executed. No more fixed protection windows - verification completes as soon as the device state confirms.
