"""HTTP client for C&D Iot integration."""
import logging
import json
import asyncio
from typing import Any

import aiohttp
import async_timeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .exceptions import (
    NetworkError,
    AuthenticationError,
    DeviceTimeoutError,
    InvalidResponseError,
    BatchQueryError,
)
from .const import (
    BASE_URL,
    DEVICE_LIST_URL,
    ROOM_LIST_URL,
    FIXED_HEADERS,
    DEFAULT_TIMEOUT,
    DEFAULT_MAX_RETRIES,
    DEFAULT_PAGE_SIZE,
    DEFAULT_PAGE_NUM,
)
from .models import DeviceList, Room, RoomList

_LOGGER = logging.getLogger(__name__)

class HttpClient:
    """HTTP client for C&D Iot integration."""

    def __init__(
        self,
        hass: HomeAssistant,
        max_retries: int = DEFAULT_MAX_RETRIES,
        x_token: str | None = None,
        phone: str | None = None,
    ) -> None:
        """Initialize the HTTP client."""
        self.hass = hass
        self._session = async_get_clientsession(hass)
        self._max_retries = max_retries
        self._token = x_token or ""
        self._phone = phone or ""

    def set_token(self, x_token: str | None) -> None:
        """Update X-token. Pass None to remove token."""
        self._token = x_token or ""

    def set_phone(self, phone: str | None) -> None:
        """Update phone number."""
        self._phone = phone or ""

    async def get_room_list(self) -> RoomList:
        """Get user's room list.

        This endpoint only requires token and phone number.
        Called after login to retrieve room configuration.

        Returns:
            RoomList with user's rooms

        Raises:
            AuthenticationError: If token is invalid
            InvalidResponseError: If response is invalid
            NetworkError: If network error occurs
        """
        try:
            headers = {
                **FIXED_HEADERS,
                "X-token": self._token,
                "space-phone": self._phone,
            }
            params = {
                "pageSize": "9999",
                "pageNum": "1",
                "roomStatus": "Binding",
            }

            async with async_timeout.timeout(DEFAULT_TIMEOUT):
                response = await self._session.get(
                    ROOM_LIST_URL,
                    headers=headers,
                    params=params,
                )

                if response.status == 401:
                    raise AuthenticationError("Authentication failed")

                response.raise_for_status()
                response_data = await response.json()

                if response_data.get("code") != 200:
                    error_msg = response_data.get("msg", "Unknown error")
                    raise InvalidResponseError(
                        f"Room list error: {error_msg}"
                    )

                room_list = RoomList(
                    total=int(response_data.get("total", 0)),
                    rooms=[],
                )

                # Parse rooms
                for room_data in response_data.get("rows", []):
                    room = Room(
                        room_id=room_data["roomId"],
                        community_id=room_data["communityId"],
                        community_code=room_data["communityCode"],
                        community_name=room_data["communityName"],
                        gateway=room_data["gateway"],
                        eas_id=room_data["easId"],
                        room_name=room_data["roomName"],
                        building_name=room_data.get("buildingName"),
                    )
                    room_list.rooms.append(room)

                _LOGGER.info(
                    "Found %d room(s), using: %s",
                    len(room_list.rooms),
                    room_list.first_room.room_name if room_list.first_room else "None"
                )

                return room_list

        except asyncio.TimeoutError as error:
            raise DeviceTimeoutError("Timeout") from error
        except AuthenticationError:
            raise
        except Exception as error:
            raise InvalidResponseError(f"Invalid response: {error}") from error

    async def send_command(
        self,
        room: Room,
        property_code: str,
        value: Any,
        device_id: str,
        device_name: str,
        product_id: str,
    ) -> bool:
        """Send command to device.

        Args:
            room: Room configuration for building headers
            property_code: Device property to control
            value: Value to set
            device_id: Target device ID
            device_name: Device name
            product_id: Product ID

        Returns:
            True if successful

        Raises:
            DeviceError: If command fails
            AuthenticationError: If token is invalid
            NetworkError: If network error occurs
        """
        try:
            headers = {
                **FIXED_HEADERS,
                "X-token": self._token,
                "space-phone": self._phone,
                # Add room-specific headers
                "roomid": room.room_id,
                "communityId": room.community_id,
                "communityCode": room.community_code,
                "communityName": room.community_name,
                "space-yr": room.community_id,
                "easId": room.eas_id,
                "gateway": room.gateway,
            }

            url = f"{BASE_URL}/device/HISENSE/{device_id}/enable"
            params = {
                "deviceId": device_id,
                "deviceName": device_name,
            }

            body_data = [{
                "productId": product_id,
                "action": None,
                "deviceAddress": device_id,
                "propertyCode": property_code,
                "value": int(value) if isinstance(value, bool) else value
            }]

            body = json.dumps(body_data)

            async with async_timeout.timeout(DEFAULT_TIMEOUT):
                response = await self._session.post(
                    url,
                    params=params,
                    headers=headers,
                    data=body,
                )

                if response.status == 401:
                    raise AuthenticationError("Authentication failed")

                response.raise_for_status()
                return True

        except asyncio.TimeoutError as error:
            raise DeviceTimeoutError("Timeout") from error
        except (AuthenticationError, DeviceTimeoutError):
            raise
        except Exception as error:
            raise InvalidResponseError(f"Invalid response: {error}") from error

    async def get_device_list(
        self,
        room: Room,
        page_size: int = DEFAULT_PAGE_SIZE,
        page_num: int = DEFAULT_PAGE_NUM,
    ) -> DeviceList:
        """Get device list using room configuration.

        Args:
            room: Room configuration for building headers
            page_size: Number of items per page
            page_num: Page number

        Returns:
            DeviceList with devices

        Raises:
            AuthenticationError: If token is invalid
            BatchQueryError: If query fails
            NetworkError: If network error occurs
        """
        try:
            headers = {
                **FIXED_HEADERS,
                "X-token": self._token,
                "space-phone": self._phone,
                # Add room-specific headers
                "roomid": room.room_id,
                "communityId": room.community_id,
                "communityCode": room.community_code,
                "communityName": room.community_name,
                "space-yr": room.community_id,
                "easId": room.eas_id,
                "gateway": room.gateway,
            }
            params = {
                "pageSize": page_size,
                "pageNum": page_num,
                "suitId": "",
            }

            async with async_timeout.timeout(DEFAULT_TIMEOUT):
                response = await self._session.get(
                    DEVICE_LIST_URL,
                    headers=headers,
                    params=params,
                )

                if response.status == 401:
                    raise AuthenticationError("Authentication failed")

                response.raise_for_status()
                response_data = await response.json()

                _LOGGER.debug(
                    "Device list API response:\n%s",
                    json.dumps(response_data, indent=2, ensure_ascii=False)
                )

                if response_data.get("code") != 200:
                    error_msg = response_data.get("msg", "Unknown error")
                    raise BatchQueryError(
                        f"Device list error: {error_msg}"
                    )

                return DeviceList(response_data)

        except asyncio.TimeoutError as error:
            raise DeviceTimeoutError("Timeout") from error
        except (AuthenticationError, BatchQueryError):
            raise
        except Exception as error:
            raise InvalidResponseError(f"Invalid response: {error}") from error 