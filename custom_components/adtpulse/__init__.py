"""
ADT Pulse for Home Assistant
See https://github.com/rsnodgrass/hass-adtpulse
"""
import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import (DataUpdateCoordinator,
                                                      UpdateFailed)
from pyadtpulse import PyADTPulse
from pyadtpulse.const import ADT_DEFAULT_HTTP_HEADERS

from homeassistant import exceptions

from .const import ADTPULSE_DOMAIN  # pylint:disable=unused-import
from .const import (CONF_FINGERPRINT, CONF_HOSTNAME, CONF_PASSWORD,
                    CONF_POLLING, CONF_USERNAME)

LOG = logging.getLogger(__name__)

ADTPULSE_SERVICE = "adtpulse_service"

SIGNAL_ADTPULSE_UPDATED = "adtpulse_updated"

EVENT_ALARM = "adtpulse_alarm"
EVENT_ALARM_END = "adtpulse_alarm_end"

NOTIFICATION_TITLE = "ADT Pulse"
NOTIFICATION_ID = "adtpulse_notification"

ATTR_SITE_ID = "site_id"
ATTR_DEVICE_ID = "device_id"

SUPPORTED_PLATFORMS = ["alarm_control_panel", "binary_sensor"]


async def async_setup(hass: HomeAssistant, config: dict):
    hass.data.setdefault(ADTPULSE_DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    polling = 3

    adtpulse = await hass.async_add_executor_job(
        PyADTPulse,
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data[CONF_FINGERPRINT],
        entry.data[CONF_HOSTNAME],
        ADT_DEFAULT_HTTP_HEADERS,
        None,
        True,
        polling,
        False,
    )
    hass.data[ADTPULSE_DOMAIN][entry.entry_id] = adtpulse

    coordinator = ADTPulseDataUpdateCoordinator(hass, adtpulse, int(polling))
    await coordinator.async_refresh()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady

    hass.data.setdefault(ADTPULSE_DOMAIN, {})
    hass.data[ADTPULSE_DOMAIN][entry.entry_id] = coordinator

    # This creates each HA object for each platform your device requires.
    # It's done by calling the `async_setup_entry` function in each platform module.
    for component in SUPPORTED_PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    # This is called when an entry/configured device is to be removed. The class
    # needs to unload itself, and remove callbacks. See the classes for further
    # details
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in SUPPORTED_PLATFORMS
            ]
        )
    )
    if unload_ok:
        hass.data[ADTPULSE_DOMAIN].pop(entry.entry_id)

    return unload_ok


class ADTPulseDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage the refresh of the ADT Pulse data api"""

    def __init__(self, hass, adtpulse, polling_rate):
        self._hass = hass
        self._adtpulse = adtpulse
        self._polling_rate = polling_rate

        super().__init__(
            hass,
            LOG,
            name=ADTPULSE_DOMAIN,
            update_interval=timedelta(seconds=polling_rate),
        )

    @property
    def adtpulse(self):
        return self._adtpulse

    @property
    def polling_rate(self):
        return self._polling_rate

    async def _async_update_data(self):
        """Update data via library."""
        try:
            LOG.debug(f"Updating ADT status")
            await self._hass.async_add_executor_job(self.adtpulse.update)
            # await self._hass.async_add_executor_job(self.adtpulse.wait_for_update)
            LOG.debug(f"Finished updating ADT status")

        except Exception as e:
            LOG.exception(e)
            raise UpdateFailed(e) from e

        return self.adtpulse


class ADTPulseEntity(Entity):
    # Base Entity class for ADT Pulse devices

    def __init__(self, hass, service, name):
        self.hass = hass
        self._service = service
        self._name = name

        self._state = None
        self._attrs = {}

    @property
    def name(self):
        # Return the display name for this sensor
        return self._name

    @property
    def icon(self):
        return "mdi:gauge"

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        # Return the device state attributes.
        return self._attrs

    async def async_added_to_hass(self):
        # Register callbacks.
        # register callback when cached ADTPulse data has been updated
        async_dispatcher_connect(
            self.hass, SIGNAL_ADTPULSE_UPDATED, self._update_callback
        )

    @callback
    def _update_callback(self):
        # Call update method.

        # inform HASS that ADT Pulse data for this entity has been updated
        self.async_schedule_update_ha_state()


async def async_connect_or_timeout(hass, adtpulse):
    try:
        LOG.info(f"Connected to ADTPulse with user {adtpulse._userId}")
    except Exception as e:
        LOG.exception(e)
        raise CannotConnect from e


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidPolling(exceptions.HomeAssistantError):
    """Error to indicate polling is incorrect value."""
