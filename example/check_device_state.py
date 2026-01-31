#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx",
# ]
# ///
"""
Device state checker - queries C&D IoT API directly to verify real device state.

This script is used alongside agent-browser E2E tests to verify that
UI operations actually affect the physical devices.

Usage:
    ./check_device_state.py              # Show all devices
    ./check_device_state.py 餐厅主灯      # Show specific device
"""

import httpx
import json
import sys
import time

# API Configuration (same as integration)
BASE_URL = "https://sqdn.cndmega.com/prod-v2.0.1/smart/mini/smart"
DEVICE_LIST_URL = f"{BASE_URL}/device/list"
ROOM_LIST_URL = "https://sqdn.cndmega.com/prod-v2.0.1/system/mini/smart/rooms"

# Token from HA config
ACCESS_TOKEN = "eyJhbGciOiJIUzUxMiJ9.eyJ1c2VyX2lkIjoiMmRjYmZkZmE5MzM1NDkwY2ExZmI3NDRiOTQwZDU0N2EiLCJ1c2VyX2tleSI6IjRlNjcxNDhlLTEyN2MtNGM2Yi05NzhkLWY0YWVmZDE0ZjliOSIsInVzZXJuYW1lIjoiNlZ3eHN0Mnc4T3BMWkZIbFFRanhMQT09In0.eb-3F9RY5CsQNN1pD9OmZj4mNPGpnAgcMAJ6efpDfJK8atuWz78Daxt6IBxGL_Kf1UwU4K1V4ZFsmUoc6pviDg"
PHONE = "15606958805"

FIXED_HEADERS = {
    "Accept": "*/*",
    "Content-Type": "application/json",
    "brand": "HISENSE",
    "execution-side": "APP",
    "X-token": ACCESS_TOKEN,
    "space-phone": PHONE,
}

# Device name mapping (from 4-switch device)
LIGHT_NAMES = {
    "FirstPower": "客厅主灯",
    "SecondPower": "客餐灯带",
    "ThirdPower": "餐厅主灯",
    "FourthPower": "过道筒灯",
}


def get_room_info() -> dict | None:
    """Get room configuration needed for device API."""
    params = {
        "pageSize": "9999",
        "pageNum": "1",
        "roomStatus": "Binding",
    }

    with httpx.Client(timeout=10) as client:
        resp = client.get(ROOM_LIST_URL, headers=FIXED_HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 200:
            print(f"Room API Error: {data.get('msg')}")
            return None

        rooms = data.get("rows", [])
        if rooms:
            room = rooms[0]
            return {
                "roomid": room["roomId"],
                "communityId": room["communityId"],
                "communityCode": room["communityCode"],
                "communityName": room["communityName"],
                "space-yr": room["communityId"],
                "easId": room["easId"],
                "gateway": room["gateway"],
            }
    return None


def get_device_list(room_headers: dict) -> list:
    """Query device list from API."""
    # URL encode Chinese characters in headers
    import urllib.parse
    encoded_headers = {}
    for k, v in {**FIXED_HEADERS, **room_headers}.items():
        if isinstance(v, str):
            try:
                v.encode('ascii')
                encoded_headers[k] = v
            except UnicodeEncodeError:
                encoded_headers[k] = urllib.parse.quote(v)
        else:
            encoded_headers[k] = v

    params = {
        "pageSize": 20,
        "pageNum": 1,
        "suitId": "",
    }

    with httpx.Client(timeout=10) as client:
        resp = client.get(DEVICE_LIST_URL, headers=encoded_headers, params=params)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 200:
            print(f"Device API Error: {data}")
            return []

        # API returns devices in 'rows' field
        devices = data.get("rows", [])
        return devices


def parse_device_states(devices: list) -> dict:
    """Parse device states into readable format."""
    states = {}

    for device in devices:
        device_name = device.get("deviceName", "Unknown")
        product_id = device.get("productId", "")
        current_state = device.get("currentState", "{}")

        try:
            state_dict = json.loads(current_state)
        except json.JSONDecodeError:
            state_dict = {}

        # Handle light device (each switch is a separate device now)
        if product_id == "connector.device.type.smartSwitch.c4":
            power = state_dict.get("PowerSwitch", "?")
            states[device_name] = "ON" if power == "1" else "OFF"

        # Handle AC device
        elif product_id == "connector.device.type.aircondition":
            power = state_dict.get("PowerSwitch", "?")
            states[device_name] = "ON" if power == 1 or power == "1" else "OFF"

    return states


def main():
    filter_name = sys.argv[1] if len(sys.argv) > 1 else None

    print(f"[{time.strftime('%H:%M:%S')}] Querying C&D IoT API...")
    print()

    # Get room info first
    room_headers = get_room_info()
    if not room_headers:
        print("ERROR: Failed to get room info")
        sys.exit(1)

    # Get device list
    devices = get_device_list(room_headers)
    if not devices:
        print("ERROR: Failed to get device list")
        sys.exit(1)

    # Parse states
    states = parse_device_states(devices)

    # Display results
    print("Device States (from C&D IoT API):")
    print("-" * 35)

    for name, state in sorted(states.items()):
        if filter_name and filter_name not in name:
            continue
        indicator = "🟢" if state == "ON" else "⚫"
        print(f"  {indicator} {name}: {state}")

    print()

    # Reic device state for scripting
    if filter_name:
        for name, state in states.items():
            if filter_name in name:
                return 0 if state == "ON" else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
