"""Config flow for the VW Group EU Data Act integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
)

from .api import ApiError, AuthError, EudaApiClient
from .brands import DEFAULT_BRAND, brand_options, get_brand
from .const import (
    CONF_BRAND,
    CONF_EMAIL,
    CONF_IDENTIFIER,
    CONF_NICKNAME,
    CONF_PASSWORD,
    CONF_VIN,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

_BRAND_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=[
            SelectOptionDict(value=slug, label=title) for slug, title in brand_options()
        ]
    )
)


class EudaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._brand: str = DEFAULT_BRAND
        self._email: str | None = None
        self._password: str | None = None
        self._vehicles: list[dict] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._brand = user_input[CONF_BRAND]
            self._email = user_input[CONF_EMAIL]
            self._password = user_input[CONF_PASSWORD]
            error = await self._async_try_login()
            if error:
                errors["base"] = error
            elif not self._vehicles:
                errors["base"] = "no_vehicles"
            else:
                return await self.async_step_vehicle()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BRAND, default=DEFAULT_BRAND): _BRAND_SELECTOR,
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_vehicle(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            vin = user_input[CONF_VIN]
            await self.async_set_unique_id(vin, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            try:
                identifier, nickname = await self._async_fetch_identifier(vin)
            except AuthError:
                return self.async_abort(reason="auth")
            else:
                veh = next((v for v in self._vehicles if v["vin"] == vin), {})
                title = veh.get("nickname") or nickname or vin
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_BRAND: self._brand,
                        CONF_EMAIL: self._email,
                        CONF_PASSWORD: self._password,
                        CONF_VIN: vin,
                        CONF_IDENTIFIER: identifier or "",
                        CONF_NICKNAME: title,
                    },
                )

        options = [
            SelectOptionDict(
                value=v["vin"],
                label=f"{v['nickname']} ({v['vin']})" if v.get("nickname") else v["vin"],
            )
            for v in self._vehicles
        ]
        return self.async_show_form(
            step_id="vehicle",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_VIN): SelectSelector(
                        SelectSelectorConfig(options=options)
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        self._email = entry_data[CONF_EMAIL]
        self._brand = entry_data.get(CONF_BRAND, DEFAULT_BRAND)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._password = user_input[CONF_PASSWORD]
            error = await self._async_try_login()
            if error:
                errors["base"] = error
            else:
                entry = self._get_reauth_entry()
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_EMAIL: self._email,
                        CONF_PASSWORD: self._password,
                    },
                )
        brand = get_brand(self._brand)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={
                "email": self._email or "",
                "brand": brand.title,
            },
            errors=errors,
        )

    def _client(self, session: aiohttp.ClientSession) -> EudaApiClient:
        return EudaApiClient(
            session,
            self._email,
            self._password,
            get_brand(self._brand),
        )

    async def _async_try_login(self) -> str | None:
        """Attempt login + vehicle discovery; return an error key or None."""
        session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar())
        client = self._client(session)
        try:
            await client.async_login()
            self._vehicles = await client.async_list_vehicles()
        except AuthError:
            return "invalid_auth"
        except ApiError as err:
            _LOGGER.warning("Login or vehicle list failed during setup: %s", err)
            return "cannot_connect"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error during login")
            return "unknown"
        finally:
            await session.close()
        return None

    async def _async_fetch_identifier(self, vin: str) -> tuple[str | None, str | None]:
        """Return portal metadata; ``None`` identifier means subscription not ready yet."""
        session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar())
        client = self._client(session)
        try:
            await client.async_login()
            meta = await client.async_get_metadata(vin)
        except AuthError:
            raise
        except ApiError as err:
            _LOGGER.warning(
                "Could not fetch metadata for %s during setup: %s", vin, err
            )
            return None, None
        finally:
            await session.close()
        identifier = meta.get("Identifier") or meta.get("identifier")
        if not identifier:
            _LOGGER.info(
                "No data-request identifier for %s yet; finishing setup and waiting "
                "for the portal subscription",
                vin,
            )
        return identifier, meta.get("Name")
