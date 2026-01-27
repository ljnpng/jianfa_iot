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
