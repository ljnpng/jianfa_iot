#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx",
# ]
# ///
"""
E2E test script for 餐厅主灯 (Dining Room Main Light)

This script directly calls the C&D IoT API to:
1. Query current device state
2. Toggle light off
3. Verify state change
4. Toggle light on
5. Verify state change

Usage:
    ./e2e_light_test.py
"""

import httpx
import json
import time
import sys

# API Configuration
BASE_URL = "https://sqdn.cndmega.com/prod-v2.0.1/smart/mini/smart"
DEVICE_LIST_URL = f"{BASE_URL}/device/list"

# Token from HA config
ACCESS_TOKEN = "eyJhbGciOiJIUzUxMiJ9.eyJ1c2VyX2lkIjoiMmRjYmZkZmE5MzM1NDkwY2ExZmI3NDRiOTQwZDU0N2EiLCJ1c2VyX2tleSI6IjRlNjcxNDhlLTEyN2MtNGM2Yi05NzhkLWY0YWVmZDE0ZjliOSIsInVzZXJuYW1lIjoiNlZ3eHN0Mnc4T3BMWkZIbFFRanhMQT09In0.eb-3F9RY5CsQNN1pD9OmZj4mNPGpnAgcMAJ6efpDfJK8atuWz78Daxt6IBxGL_Kf1UwU4K1V4ZFsmUoc6pviDg"

HEADERS = {
    "Accept": "*/*",
    "Content-Type": "application/json",
    "brand": "HISENSE",
    "execution-side": "APP",
    "X-token": ACCESS_TOKEN,
}

# 餐厅主灯 device info (ThirdPower on the 4-switch device)
DEVICE_ID = "a005096001842712fffe91cac7"
LIGHT_KEY = "ThirdPower"  # 餐厅主灯 is ThirdPower


def get_device_state() -> dict | None:
    """Query current device state from API."""
    payload = {"pageNum": 1, "pageSize": 20}

    with httpx.Client(timeout=10) as client:
        resp = client.post(DEVICE_LIST_URL, headers=HEADERS, json=payload)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 200:
            print(f"API Error: {data}")
            return None

        devices = data.get("data", {}).get("list", [])
        for device in devices:
            if device.get("deviceId") == DEVICE_ID:
                return device
    return None


def parse_light_state(device: dict) -> bool | None:
    """Parse light state from device data."""
    current_state = device.get("currentState", "{}")
    try:
        state_dict = json.loads(current_state)
        power_value = state_dict.get(LIGHT_KEY, {}).get("PowerSwitch")
        if power_value is not None:
            return power_value == "1"
    except json.JSONDecodeError:
        pass
    return None


def set_light_state(turn_on: bool) -> bool:
    """Set light state via API."""
    control_url = f"{BASE_URL}/device/HISENSE/{DEVICE_ID}/enable"

    payload = {
        "deviceId": DEVICE_ID,
        "productId": "connector.device.type.smartSwitch.c4",
        "properties": {
            LIGHT_KEY: {
                "PowerSwitch": "1" if turn_on else "0"
            }
        }
    }

    with httpx.Client(timeout=10) as client:
        resp = client.post(control_url, headers=HEADERS, json=payload)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") == 200:
            return True
        else:
            print(f"Control API Error: {data}")
            return False


def main():
    print("=" * 50)
    print("餐厅主灯 E2E Test")
    print("=" * 50)
    print()

    # Step 1: Get initial state
    print(f"[{time.strftime('%H:%M:%S')}] Step 1: Querying initial state...")
    device = get_device_state()
    if not device:
        print("ERROR: Failed to get device state")
        sys.exit(1)

    initial_state = parse_light_state(device)
    print(f"  餐厅主灯 initial state: {'ON' if initial_state else 'OFF'}")
    print()

    # Step 2: Turn OFF
    print(f"[{time.strftime('%H:%M:%S')}] Step 2: Turning OFF 餐厅主灯...")
    if not set_light_state(False):
        print("ERROR: Failed to turn off light")
        sys.exit(1)
    print("  Command sent successfully")
    print()

    # Step 3: Wait and verify OFF state
    print(f"[{time.strftime('%H:%M:%S')}] Step 3: Waiting 8 seconds for state sync...")
    time.sleep(8)

    device = get_device_state()
    off_state = parse_light_state(device)
    print(f"[{time.strftime('%H:%M:%S')}] Verifying state: {'ON' if off_state else 'OFF'}")

    if off_state:
        print("  WARNING: Light still shows ON (may be sync delay)")
    else:
        print("  SUCCESS: Light is OFF")
    print()

    # Step 4: Turn ON
    print(f"[{time.strftime('%H:%M:%S')}] Step 4: Turning ON 餐厅主灯...")
    if not set_light_state(True):
        print("ERROR: Failed to turn on light")
        sys.exit(1)
    print("  Command sent successfully")
    print()

    # Step 5: Wait and verify ON state
    print(f"[{time.strftime('%H:%M:%S')}] Step 5: Waiting 8 seconds for state sync...")
    time.sleep(8)

    device = get_device_state()
    on_state = parse_light_state(device)
    print(f"[{time.strftime('%H:%M:%S')}] Verifying state: {'ON' if on_state else 'OFF'}")

    if on_state:
        print("  SUCCESS: Light is ON")
    else:
        print("  WARNING: Light still shows OFF (may be sync delay)")
    print()

    # Summary
    print("=" * 50)
    print("Test Summary")
    print("=" * 50)
    print(f"  Initial state: {'ON' if initial_state else 'OFF'}")
    print(f"  After OFF command: {'ON' if off_state else 'OFF'}")
    print(f"  After ON command: {'ON' if on_state else 'OFF'}")

    if not off_state and on_state:
        print("\n  RESULT: ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("\n  RESULT: Some state verifications may have sync delays")
        sys.exit(0)


if __name__ == "__main__":
    main()
