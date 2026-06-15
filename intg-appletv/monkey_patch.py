#!/usr/bin/env python3
"""
This module handles monkey patching of the pyatv library.

:copyright: (c) 2023-2024 by Unfolded Circle ApS.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

# pyright: reportPrivateUsage=false

import logging
import os
from typing import Any, cast

import pyatv
import pyatv.auth.hap_pairing
import pyatv.auth.hap_srp
import pyatv.protocols.companion.api
import pyatv.protocols.companion.connection
import pyatv.protocols.companion.protocol

_LOG = logging.getLogger(__name__)


async def patched_pyatv_companion_connect(self: pyatv.protocols.companion.api.CompanionAPI) -> None:
    """Patch connect method for pyatv Companion protocol."""
    if self._protocol:
        return
    self._connection = pyatv.protocols.companion.connection.CompanionConnection(
        self.core.loop,
        str(self.core.config.address),
        self.core.service.port,
        self.core.device_listener,
    )
    hap_srp = pyatv.auth.hap_srp
    srp_auth_handler = hap_srp.SRPAuthHandler
    self._protocol = pyatv.protocols.companion.protocol.CompanionProtocol(
        self._connection,
        srp_auth_handler(),
        self.core.service,
    )
    self._protocol.listener = self
    start = cast("Any", self._protocol.start)
    system_info = cast("Any", self.system_info)
    await start()
    await system_info()
    await self._touch_start()
    await self._session_start()
    await self._send_command("TVRCSessionStart", {"ProtocolVersionKey": "1.2"})
    await self._text_input_start()
    await self.subscribe_event("_iMC")


async def patched_pyatv_companion_system_info(self: pyatv.protocols.companion.api.CompanionAPI) -> None:
    """Patch pyatv method to send system information to device."""
    creds = pyatv.auth.hap_pairing.parse_credentials(self.core.service.credentials)
    info = self.core.settings.info
    _LOG.debug("Sending system information")
    await self._send_command(
        "_systemInfo",
        {
            "_bf": 0,
            "_cf": 512,
            "_clFl": 128,
            # A null "_i" stops the device from pushing TVSystemStatus
            # (power state) events; fall back to a stable identifier.
            # `_i` needs to be unique per client, otherwise multiple clients will get disconnected!
            "_i": info.rp_id or info.device_id.replace(":", "").lower(),
            "_idsID": creds.client_id,
            "_pubID": info.device_id,
            "_sf": 256,
            "_sv": "170.18",
            "model": info.model,
            "name": info.name,
        },
    )


@property
def patched_airplay_pairing_handler_device_provides_pin(self) -> bool:
    """Return True if remote device presents PIN code, else False."""
    return self.service.password is None


async def patched_airplay_pairing_handler_begin(self) -> None:
    """Start pairing process."""
    self.http = await pyatv.support.http.http_connect(self.address, self.service.port)
    self.pairing_procedure = pyatv.protocols.airplay.auth.pair_setup(
        (
            pyatv.auth.hap_pairing.AuthenticationType.HAP
            if self.airplay_version == pyatv.protocols.airplay.utils.AirPlayMajorVersion.AirPlayV2
            else pyatv.auth.hap_pairing.AuthenticationType.Legacy
        ),
        self.http,
    )
    self._has_paired = False
    return await pyatv.support.error_handler(self.pairing_procedure.start_pairing, pyatv.exceptions.PairingError)


def patched_airplay_pairing_handler_pin(self, pin) -> None:
    """Pin code or password used for pairing."""
    pin_str = str(pin)
    self.pin_code = pin_str if pin_str == self.service.password else pin_str.zfill(4)
