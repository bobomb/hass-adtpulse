"""HASS ADT Pulse Config Flow."""
from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries, core, exceptions
from homeassistant.const import (
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_DEVICE_ID,
    CONF_SCAN_INTERVAL,
)
from homeassistant.core import callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.config_entry_flow import FlowResult
from pyadtpulse import PyADTPulse
from typing import Dict, Any, Optional

from .const import ADTPULSE_DOMAIN, LOG

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
DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_DEVICE_ID): str,
        vol.Optional(CONF_SCAN_INTERVAL): int,
    }
)


async def validate_input(
    hass: core.HomeAssistant, data: Dict[str, str]
) -> Dict[str, str]:
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
        data[CONF_USERNAME], data[CONF_PASSWORD], data[CONF_DEVICE_ID], do_login=False
    )
    try:
        result = await adtpulse.async_login()
    except Exception as ex:
        LOG.error("ERROR VALIDATING INPUT")
        raise CannotConnect from ex
    if not result:
        LOG.error("Could not validate login info for ADT Pulse")
        raise InvalidAuth("Could not validate ADT Pulse login info")
    await adtpulse.async_logout()
    return {"title": data[CONF_USERNAME]}


class PulseConfigFlow(config_entries.ConfigFlow, domain=ADTPULSE_DOMAIN):
    """Handle a config flow for ADT Pulse."""

    VERSION = 1
    # Pick one of the available connection classes in homeassistant/config_entries.py
    # This tells HA if it should be asking for updates, or it'll be notified of updates
    # automatically. This example uses PUSH, as the dummy hub will notify HA of
    # changes.
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_PUSH

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.username = None
        self.reauth = False

    async def async_step_import(self, import_config: Dict[str, Any]) -> FlowResult:
        """Import a config entry from configuration.yaml."""
        return await self.async_step_user(import_config)

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
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

                return self.async_create_entry(
                    title=user_input[CONF_USERNAME], data=info
                )

        # If there is no user input or there were errors, show the form again,
        # including any errors that were found with the input.
        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    async def async_step_reauth(self, data: Dict[str, str]) -> FlowResult:
        """Handle configuration by re-auth."""
        self.username = data[CONF_USERNAME]
        self.reauth = True
        return await self.async_step_user()

    @callback
    def _async_entry_for_username(self, username: str) -> Optional[ConfigEntry]:
        """Find an existing entry for a username."""
        for entry in self._async_current_entries():
            if entry.data.get(CONF_USERNAME) == username:
                return entry
        return None


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""
