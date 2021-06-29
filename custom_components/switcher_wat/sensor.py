import logging
import socket
import select
import struct
import binascii as ba

import voluptuous as vol

from datetime import timedelta

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_NAME, CONF_PORT, CONF_TIMEOUT, CONF_HOST, ATTR_DEVICE_ID,
    CONF_UNIT_OF_MEASUREMENT)
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.entity import Entity
import homeassistant.helpers.config_validation as cv
from homeassistant.util import Throttle

_LOGGER = logging.getLogger(__name__)

CONF_BUFFER_SIZE = 'buffer_size'

DEFAULT_BUFFER_SIZE = 1024
DEFAULT_NAME = 'Switcher Watt Sensor'
DEFAULT_TIMEOUT = 20

SCAN_INTERVAL = timedelta(seconds=4)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_PORT): cv.port,
    vol.Optional(ATTR_DEVICE_ID): cv.string,
    vol.Optional(CONF_HOST): cv.string,
    vol.Optional(CONF_BUFFER_SIZE, default=DEFAULT_BUFFER_SIZE): cv.positive_int,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int,
    vol.Optional(CONF_UNIT_OF_MEASUREMENT): cv.string,
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the UDP Sensor."""
    add_devices([UdpSensor(hass, config)])


class UdpSensor(Entity):
    """Implementation of a UDP socket based sensor."""

    required = tuple()

    def __init__(self, hass, config):
        """Set all the config values if they exist and get initial state."""

        self._hass = hass
        self._config = {
            CONF_NAME: config.get(CONF_NAME),
            ATTR_DEVICE_ID: config.get(ATTR_DEVICE_ID),
            CONF_HOST: config.get(CONF_HOST),
            CONF_PORT: config.get(CONF_PORT),
            CONF_TIMEOUT: config.get(CONF_TIMEOUT),
            CONF_UNIT_OF_MEASUREMENT: config.get(CONF_UNIT_OF_MEASUREMENT),
            CONF_BUFFER_SIZE: config.get(CONF_BUFFER_SIZE),
        }
        self._state = 0
        self._data = None

        self.update = Throttle(SCAN_INTERVAL)(self._update)

    @property
    def name(self):
        """Return the name of this sensor."""
        name = self._config[CONF_NAME]
        if name is not None:
            return name
        return super(UdpSensor, self).name

    @property
    def state(self):
        """Return the state of the device."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity."""
        return self._config[CONF_UNIT_OF_MEASUREMENT]

    def _update(self):
        """Get the latest value for this sensor."""
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(self._config[CONF_TIMEOUT])
            try:
                # sock.bind((socket.gethostbyname(socket.getfqdn()),self._config[CONF_PORT]))
                sock.bind(("0.0.0.0", self._config[CONF_PORT]))
            except socket.error as err:
                _LOGGER.error("Unable to bind on port %s: %s", self._config[CONF_PORT], err)
                return

            readable, _, _ = select.select(
                [sock], [], [], self._config[CONF_TIMEOUT])
            if not readable:
                _LOGGER.warning(
                    "Timeout (%s second(s)) waiting for data on port %s.",
                    self._config[CONF_TIMEOUT], self._config[CONF_PORT])
                return

            self._data, _ = sock.recvfrom(self._config[CONF_BUFFER_SIZE])

            b = ba.hexlify(self._data)[270:278]
            curr_wat = int(b[2:4] + b[0:2], 16)
            new_state = curr_wat

            if self._config[CONF_HOST] is not None:
                b = ba.hexlify(self._data)[152:160]
                ip_addr = int(b[6:8] + b[4:6] + b[2:4] + b[0:2], 16)
                host = str(socket.inet_ntoa(struct.pack("<L", ip_addr)))
                if host is not None and host == self._config[CONF_HOST]:
                    self._state = new_state
            elif self._config[ATTR_DEVICE_ID] is not None:
                if bytes(self._config[ATTR_DEVICE_ID], encoding='utf-8') in self._data:
                    self._state = new_state
