"""HASS ADT Pulse Config Flow."""
from __future__ import annotations

from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import CONN_CLASS_CLOUD_PUSH, ConfigEntry, ConfigFlow
from homeassistant.const import CONF_DEVICE_ID, CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from pyadtpulse import PyADTPulse

from .const import (
    ADTPULSE_DOMAIN,
    ADTPULSE_URL_CA,
    ADTPULSE_URL_US,
    CONF_FINGERPRINT,
    CONF_HOSTNAME,
    LOG,
)

# This is the schema that used to display the UI to the user. This simple
# schema has a single required host field, but it could include a number of fields
# such as username, password etc. See other components in the HA core code for
# further examples.
# Note the input displayed to the user will be translated. See the
# translations/<lang>.json file and strings.json. See here for further information:
# https://developers.home-assistant.io/docs/config_entries_config_flow_handler/#translations
# At the time of writing I found the translations created by the scaffold didn't
# quite work as documented and always gave me the "Lokalise key references" string
# (in square brackets), rather than the actual translated value. I did not attempt to
# figure this out or look further into it.


def _get_data_schema(previous_input: dict[str, Any] | None) -> vol.Schema:
    if previous_input is None:
        new_input = {}
    else:
        new_input = previous_input
    DATA_SCHEMA = vol.Schema(
        {
            vol.Required(
                CONF_USERNAME,
                description={"suggested_value": new_input.get(CONF_USERNAME)},
            ): cv.string,
            vol.Required(
                CONF_PASSWORD,
                description={"suggested_value": new_input.get(CONF_PASSWORD)},
            ): cv.string,
            vol.Required(
                CONF_FINGERPRINT,
                description={"suggested_value", new_input.get(CONF_FINGERPRINT)},
            ): cv.string,
            vol.Required(
                CONF_HOSTNAME,
                description={
                    "suggested_value": new_input.get(CONF_HOSTNAME, ADTPULSE_URL_US)
                },
            ): vol.In([ADTPULSE_URL_US, ADTPULSE_URL_CA]),
        }
    )
    return DATA_SCHEMA


async def validate_input(hass: HomeAssistant, data: dict[str, str]) -> dict[str, str]:
    """Validate form input.

    Args:
        hass (core.HomeAssistant): hass object
        data (Dict): voluptuous Schema

    Raises:
        CannotConnect: Cannot connect to ADT Pulse site
        InvalidAuth: login failed

    Returns:
        Dict[str, str | bool]: "title" : username used to validate
                               "login result": True if login succeeded
    """
    result = False
    adtpulse = PyADTPulse(
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
        data[CONF_FINGERPRINT],
        service_host=data[CONF_HOSTNAME],
        do_login=False,
        create_task_cb=hass.async_create_background_task,  # type: ignore
    )
    try:
        result = await adtpulse.async_login()
        site_id = adtpulse.sites[0]
    except Exception as ex:
        LOG.error("ERROR VALIDATING INPUT")
        raise CannotConnect from ex
    finally:
        await adtpulse.async_logout()
    if not result:
        LOG.error("Could not validate login info for ADT Pulse")
        raise InvalidAuth("Could not validate ADT Pulse login info")
    return {"title": f"ADT: Site {site_id}"}


class PulseConfigFlow(ConfigFlow, domain=ADTPULSE_DOMAIN):  # type: ignore
    """Handle a config flow for ADT Pulse."""

    VERSION = 1
    # Pick one of the available connection classes in homeassistant/config_entries.py
    # This tells HA if it should be asking for updates, or it'll be notified of updates
    # automatically. This example uses PUSH, as the dummy hub will notify HA of
    # changes.
    CONNECTION_CLASS = CONN_CLASS_CLOUD_PUSH

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.username: str | None = None
        self.reauth = False

    # FIXME: this isn't being called for some reason
    async def async_step_import(self, import_config: dict[str, Any]) -> FlowResult:
        """Import a config entry from configuration.yaml."""
        new_config = {**import_config}
        if self.hass.data[CONF_HOST] is not None:
            new_config.update({CONF_HOSTNAME: self.hass.data[CONF_HOST]})
            new_config.pop(CONF_HOST)
        if self.hass.data[CONF_DEVICE_ID] is not None:
            new_config.update({CONF_FINGERPRINT: self.hass.data[CONF_DEVICE_ID]})
            new_config.pop(CONF_DEVICE_ID)
        return await self.async_step_user(new_config)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step.

        Args:
            user_input (Optional[Dict[str, Any]], optional): user input.
                    Defaults to None.

        Returns:
            FlowResult: the flow result
        """
        # This goes through the steps to take the user through the setup process.
        # Using this it is possible to update the UI and prompt for additional
        # information. This example provides a single form (built from `DATA_SCHEMA`),
        # and when that has some validated input, it calls `async_create_entry` to
        # actually create the HA config entry. Note the "title" value is returned by
        # `validate_input` above.
        errors = info = {}
        if user_input is not None:
            existing_entry = self._async_entry_for_username(user_input[CONF_USERNAME])
            if existing_entry and not self.reauth:
                return self.async_abort(reason="already_configured")
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                LOG.exception("Unexpected exception")
                errors["base"] = "unknown"
            if not errors:
                if existing_entry:
                    self.hass.config_entries.async_update_entry(
                        existing_entry, data=info
                    )
                    await self.hass.config_entries.async_reload(existing_entry.entry_id)
                    return self.async_abort(reason="reauth_successful")

                return self.async_create_entry(title=info["title"], data=user_input)

        # If there is no user input or there were errors, show the form again,
        # including any errors that were found with the input.
        if user_input is None and self.init_data is not None:
            data_schema = _get_data_schema(self.init_data)
        else:
            data_schema = _get_data_schema(user_input)
        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    async def async_step_reauth(self, data: dict[str, str]) -> FlowResult:
        """Handle configuration by re-auth."""
        self.username = data.get(CONF_USERNAME)
        self.reauth = True
        return await self.async_step_user()

    @callback
    def _async_entry_for_username(self, username: str) -> ConfigEntry | None:
        """Find an existing entry for a username."""
        for entry in self._async_current_entries():
            if entry.data.get(CONF_USERNAME) == username:
                return entry
        return None


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
