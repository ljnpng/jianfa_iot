"""Config flow for C&D Iot integration."""
import logging
import voluptuous as vol

from dataclasses import dataclass, field
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN
from .auth_client import AuthClient
from .http_client import HttpClient
from .models import Room, RoomList

_LOGGER = logging.getLogger(__name__)

@dataclass
class FlowState:
    """Config flow state."""
    phone: str
    token_bundle: dict[str, str] = field(default_factory=dict)
    room_config: Room | None = None

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for C&D Iot."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._flow_state: FlowState | None = None

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            return await self.async_step_phone()
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    async def async_step_phone(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Input phone number and request SMS code."""
        errors: dict[str, str] = {}

        if user_input is not None:
            phone = str(user_input.get("phone", "")).strip()
            if phone:
                try:
                    client = AuthClient(self.hass)
                    await client.request_code(phone)
                    self._flow_state = FlowState(phone=phone)
                    return await self.async_step_code()
                except Exception as err:
                    _LOGGER.exception("Failed to request SMS code")
                    errors["base"] = "cannot_connect"
            else:
                errors["phone"] = "required"

        return self.async_show_form(
            step_id="phone",
            data_schema=vol.Schema({vol.Required("phone"): str}),
            errors=errors,
        )

    async def async_step_code(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Input SMS code, login, and fetch room config."""
        errors: dict[str, str] = {}

        if user_input is not None:
            code = str(user_input.get("code", "")).strip()
            if not code:
                errors["code"] = "required"
            else:
                try:
                    # Login
                    client = AuthClient(self.hass)
                    token_bundle = await client.login(
                        self._flow_state.phone, code
                    )

                    # Fetch room config
                    http_client = HttpClient(
                        self.hass,
                        x_token=token_bundle["access_token"],
                        phone=self._flow_state.phone,
                    )
                    room_list = await http_client.get_room_list()

                    if not room_list.rooms:
                        errors["base"] = "no_rooms"
                    else:
                        room_config = room_list.first_room
                        self._flow_state.token_bundle = token_bundle
                        self._flow_state.room_config = room_config

                        # Create entry with only auth data
                        return self.async_create_entry(
                            title=f"C&D IoT {room_config.room_name}",
                            data={
                                "auth": {
                                    "phone": self._flow_state.phone,
                                    "access_token": token_bundle["access_token"],
                                    "refresh_token": token_bundle.get("refresh_token", ""),
                                    "expires_in": token_bundle.get("expires_in", 10080),
                                }
                            }
                        )

                except Exception as err:
                    _LOGGER.exception("Login or get room failed")
                    errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="code",
            data_schema=vol.Schema({vol.Required("code"): str}),
            errors=errors,
        )

    async def async_step_reauth(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Trigger re-authentication flow."""
        entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        phone = entry.data["auth"]["phone"]

        self._flow_state = FlowState(phone=phone)

        # Auto send code
        try:
            client = AuthClient(self.hass)
            await client.request_code(phone)
        except Exception as err:
            _LOGGER.warning("Auto send code failed: %s", err)

        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Handle re-authentication confirmation."""
        errors: dict[str, str] = {}

        if user_input is not None:
            code = str(user_input.get("code", "")).strip()
            if not code:
                errors["code"] = "required"
            else:
                try:
                    client = AuthClient(self.hass)
                    token_bundle = await client.login(
                        self._flow_state.phone, code
                    )

                    http_client = HttpClient(
                        self.hass,
                        x_token=token_bundle["access_token"],
                        phone=self._flow_state.phone,
                    )
                    room_list = await http_client.get_room_list()
                    room_config = room_list.first_room

                    # Update entry
                    entry = self.hass.config_entries.async_get_entry(
                        self.context["entry_id"]
                    )
                    new_data = {
                        **entry.data,
                        "auth": {
                            "phone": self._flow_state.phone,
                            **token_bundle,
                        }
                    }
                    self.hass.config_entries.async_update_entry(
                        entry, data=new_data
                    )

                    await self.hass.config_entries.async_reload(entry.entry_id)
                    return self.async_abort(reason="reauth_successful")

                except Exception as err:
                    _LOGGER.exception("Reauth failed")
                    errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required("code"): str}),
            errors=errors,
        )
