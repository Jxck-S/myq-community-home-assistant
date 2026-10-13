"""Config flow for myQ Community: email/password, then the SMS/email one-time code."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlow, ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers.httpx_client import get_async_client
from myqcommunity import AuthSession, MyQAuthError, MyQOtpError, MyQRequestError, PendingMfa, Token

from .const import CONF_CODE, CONF_EMAIL, CONF_PASSWORD, CONF_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)
REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): str})
OTP_SCHEMA = vol.Schema({vol.Required(CONF_CODE): str})


class MyQCommunityConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for myQ Community.

    myQ requires a one-time code on most accounts, so login is two steps:
    ``start_login`` sends the code, and the in-progress login (``PendingMfa``)
    is kept on the flow until the user enters it in the ``otp`` step. Only the
    resulting refresh token is stored, never the password.
    """

    VERSION = 1

    def __init__(self) -> None:
        self._auth: AuthSession | None = None
        self._pending: PendingMfa | None = None
        self._email: str | None = None

    async def _start_login(self, password: str) -> tuple[ConfigFlowResult | None, dict[str, str]]:
        """Submit credentials. Returns (next step result, errors)."""
        if self._auth is None:
            self._auth = AuthSession(http=get_async_client(self.hass))
        await self._discard_pending()
        try:
            result = await self._auth.start_login(self._email, password)
        except MyQAuthError:
            return None, {"base": "invalid_auth"}
        except MyQRequestError:
            return None, {"base": "cannot_connect"}
        except Exception:
            _LOGGER.exception("Unexpected error logging in to myQ Community")
            return None, {"base": "unknown"}
        if isinstance(result, Token):  # account without MFA
            return self._finish(result), {}
        self._pending = result
        return await self.async_step_otp(), {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for email and password."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._email = user_input[CONF_EMAIL].strip()
            await self.async_set_unique_id(self._email.lower())
            self._abort_if_unique_id_configured()
            result, errors = await self._start_login(user_input[CONF_PASSWORD])
            if result:
                return result

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA, {CONF_EMAIL: (user_input or {}).get(CONF_EMAIL)}
            ),
            errors=errors,
        )

    async def async_step_otp(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the one-time code myQ just sent."""
        assert self._auth is not None and self._pending is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                token = await self._auth.finish_login(self._pending, user_input[CONF_CODE])
            except MyQOtpError:
                errors["base"] = "invalid_code"  # same pending login, try another code
            except (MyQAuthError, MyQRequestError) as err:
                # The login itself broke (expired, network); start over from credentials
                _LOGGER.debug("myQ one-time code step failed: %s", err)
                self._pending = None
                return self._show_credentials_form({"base": "login_expired"})
            else:
                self._pending = None
                return self._finish(token)

        challenge = self._pending.challenge
        return self.async_show_form(
            step_id="otp",
            data_schema=OTP_SCHEMA,
            description_placeholders={
                "method": "text message" if challenge.method == "sms" else "email",
                "destination": challenge.masked_phone or challenge.masked_email or "your device",
            },
            errors=errors,
        )

    def _finish(self, token: Token) -> ConfigFlowResult:
        if self.source == SOURCE_REAUTH:
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data_updates={CONF_TOKEN: token.to_dict()}
            )
        return self.async_create_entry(title=self._email, data={CONF_EMAIL: self._email, CONF_TOKEN: token.to_dict()})

    def _show_credentials_form(self, errors: dict[str, str]) -> ConfigFlowResult:
        if self.source == SOURCE_REAUTH:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=REAUTH_SCHEMA,
                description_placeholders={"email": self._email},
                errors=errors,
            )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, {CONF_EMAIL: self._email}),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start reauth when the stored refresh token stops working."""
        self._email = entry_data[CONF_EMAIL]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the password again; a new one-time code follows."""
        errors: dict[str, str] = {}
        if user_input is not None:
            result, errors = await self._start_login(user_input[CONF_PASSWORD])
            if result:
                return result
        return self._show_credentials_form(errors)

    async def _discard_pending(self) -> None:
        if self._pending is not None:
            pending, self._pending = self._pending, None
            await pending.aclose()

    @callback
    def async_remove(self) -> None:
        """Close the in-progress login if the user abandons the flow."""
        if self._pending is not None:
            self.hass.async_create_task(self._discard_pending())
