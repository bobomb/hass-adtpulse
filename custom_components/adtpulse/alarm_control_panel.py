"""Support for ADT Pulse alarm control panels."""
from __future__ import annotations

import logging
from typing import Coroutine, Dict, Optional

import homeassistant.components.alarm_control_panel as alarm
from homeassistant.components.alarm_control_panel.const import (
    AlarmControlPanelEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    STATE_ALARM_ARMED_AWAY,
    STATE_ALARM_ARMED_HOME,
    STATE_ALARM_ARMING,
    STATE_ALARM_DISARMED,
    STATE_ALARM_DISARMING,
)
from homeassistant.helpers.update_coordinator import callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.discovery import DiscoveryInfoType
from homeassistant.config_entries import ConfigEntry
from pyadtpulse.site import (
    ADT_ALARM_ARMING,
    ADT_ALARM_AWAY,
    ADT_ALARM_DISARMING,
    ADT_ALARM_HOME,
    ADT_ALARM_OFF,
    ADT_ALARM_UNKNOWN,
    ADTPulseSite,
)

from .const import ADTPULSE_DOMAIN

from .base_entity import ADTPulseEntity
from .coordinator import ADTPulseDataUpdateCoordinator

LOG = logging.getLogger(__name__)

ALARM_MAP = {
    ADT_ALARM_ARMING: STATE_ALARM_ARMING,
    ADT_ALARM_AWAY: STATE_ALARM_ARMED_AWAY,
    ADT_ALARM_DISARMING: STATE_ALARM_DISARMING,
    ADT_ALARM_HOME: STATE_ALARM_ARMED_HOME,
    ADT_ALARM_OFF: STATE_ALARM_DISARMED,
    ADT_ALARM_UNKNOWN: None,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType = {},
):
    """Set up an alarm control panel for ADT Pulse."""
    coordinator: ADTPulseDataUpdateCoordinator = hass.data[ADTPULSE_DOMAIN][
        config.entry_id
    ]
    if not coordinator:
        LOG.error("ADT Pulse service not initialized, cannot setup alarm platform")
        return

    if not coordinator.adtpulse.sites:
        LOG.error(f"ADT Pulse service failed to return sites: {coordinator.adtpulse}")
        return

    async_add_entities(
        [ADTPulseAlarm(coordinator, site) for site in coordinator.adtpulse.sites]
    )


class ADTPulseAlarm(ADTPulseEntity, alarm.AlarmControlPanelEntity):
    """An alarm_control_panel implementation for ADT Pulse."""

    def __init__(self, coordinator: ADTPulseDataUpdateCoordinator, site: ADTPulseSite):
        """Initialize the alarm control panel."""
        LOG.debug(f"{ADTPULSE_DOMAIN}: adding alarm control panel for {site.name}")
        name = f"ADT {site.name}"
        self._site = site
        super().__init__(coordinator, name, ALARM_MAP[self._site.status])

    @property
    def status(self) -> str:
        """Return the alarm status.

        Returns:
            str: the status
        """
        return ALARM_MAP[self._site.status]

    @property
    def icon(self) -> str:
        """Return the icon."""
        return "mdi:security"

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        return (
            AlarmControlPanelEntityFeature.ARM_AWAY
            | AlarmControlPanelEntityFeature.ARM_CUSTOM_BYPASS
            | AlarmControlPanelEntityFeature.ARM_HOME
        )

    async def _perform_alarm_action(
        self, arm_disarm_func: Coroutine[Optional[bool], None, bool], action: str
    ) -> None:
        LOG.debug(f"{ADTPULSE_DOMAIN}: Setting Alarm to  {action}")
        if await arm_disarm_func:
            await self.async_update_ha_state()
        else:
            LOG.warning(f"Could not {action} ADT Pulse alarm")

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Send disarm command."""
        await self._perform_alarm_action(self._site.async_disarm(), "disarm")

    async def async_alarm_arm_home(self, code=None):
        """Send arm home command."""
        await self._perform_alarm_action(self._site.async_arm_home(), "arm home")

    async def async_alarm_arm_away(self):
        """Send arm away command."""
        await self._perform_alarm_action(self._site.async_arm_away(), "arm away")

    # Pulse can arm away or home with bypass
    async def async_alarm_arm_custom_bypass(self) -> None:
        """Send force arm command."""
        await self._perform_alarm_action(
            self._site.async_arm_away(force_arm=True), "force arm"
        )

    @property
    def name(self) -> str:
        """Return the name of the alarm."""
        return self._name

    @property
    def extra_state_attributes(self) -> Dict:
        """Return the state attributes."""
        return {
            # FIXME: add timestamp for this state change?
            "site_id": self._site.id,
            "site_name": self._site.name,
        }

    @property
    def unique_id(self) -> str:
        """Return HA unique id.

        Returns:
            str: the unique id
        """
        return f"adt_pulse_alarm_{self._site.id}"

    @property
    def code_format(self) -> None:
        """Return code format.

        Returns:
            None (not implmented)
        """
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        LOG.debug(
            f"Updating Pulse alarm to {ALARM_MAP[self._site.status]} "
            f"for site {self._site.id}"
        )
        super()._handle_coordinator_update()
