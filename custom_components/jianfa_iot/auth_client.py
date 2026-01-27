"""Auth client for SMS code login and token management."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import aiohttp
import async_timeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    AUTH_GET_CODE_URL,
    AUTH_LOGIN_URL,
    FIXED_HEADERS,
    DEFAULT_TIMEOUT,
)
from .exceptions import AuthenticationError, NetworkError, InvalidResponseError

_LOGGER = logging.getLogger(__name__)


class AuthClient:
    """Client for requesting SMS code and exchanging for X-token."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._session = async_get_clientsession(hass)
        self._headers = FIXED_HEADERS.copy()
        # 移除任何残留 token
        self._headers.pop("X-token", None)
        self._headers.pop("x-token", None)

    async def request_code(self, phone: str) -> bool:
        """请求短信验证码。返回 True 表示服务端接受请求。"""
        try:
            body = json.dumps({"ownerPhoneNumber": phone})
            _LOGGER.debug("Requesting SMS code for %s", phone)

            async with async_timeout.timeout(DEFAULT_TIMEOUT):
                resp = await self._session.post(
                    AUTH_GET_CODE_URL, headers=self._headers, data=body
                )
                text = await resp.text()
                _LOGGER.debug("SMS code resp %s: %s", resp.status, text)
                resp.raise_for_status()
                # 无需严格校验 body，只要 2xx 即认为已发送
                return 200 <= resp.status < 300
        except aiohttp.ClientError as err:
            raise NetworkError(f"Network error: {err}") from err
        except Exception as err:
            raise InvalidResponseError(f"Invalid response: {err}") from err

    async def login(self, phone: str, code: str) -> Dict[str, Any]:
        """使用验证码登录，返回 {access_token, refresh_token, expires_in}."""
        try:
            body = json.dumps({"ownerPhoneNumber": phone, "code": code})
            _LOGGER.debug("Logging in with code for %s", phone)

            async with async_timeout.timeout(DEFAULT_TIMEOUT):
                resp = await self._session.post(
                    AUTH_LOGIN_URL, headers=self._headers, data=body
                )
                text = await resp.text()
                _LOGGER.debug("Login resp %s: %s", resp.status, text)
                if resp.status == 401:
                    raise AuthenticationError("Authentication failed")
                resp.raise_for_status()
                data = await resp.json()
                if data.get("code") != 200 or "data" not in data:
                    raise AuthenticationError(data.get("msg") or "login failed")
                return data["data"]
        except aiohttp.ClientError as err:
            raise NetworkError(f"Network error: {err}") from err
        except Exception as err:
            raise InvalidResponseError(f"Invalid response: {err}") from err


