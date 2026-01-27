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
