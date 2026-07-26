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
from pyatv.support.http import HttpConnection, http_connect
from pyatv.protocols.airplay.pairing import AuthenticationType, pair_setup, AirPlayMajorVersion
from pyatv import exceptions
from pyatv.auth.hap_pairing import PairSetupProcedure
from pyatv.const import Protocol
from pyatv.core import Core
from pyatv.interface import PairingHandler
from pyatv.support import error_handler
from pyatv.support.http import HttpConnection, http_connect
from pyatv.protocols.airplay.pairing import AirPlayPairingHandler
from pyatv.auth import hap_tlv8
from pyatv.auth.hap_pairing import (
    HapCredentials,
    PairSetupProcedure,
    PairVerifyProcedure,
)
from pyatv.auth.hap_srp import SRPAuthHandler
from pyatv.exceptions import InvalidResponseError
from pyatv.support import log_binary
from pyatv.support.http import HttpConnection, HttpResponse
from copy import copy
from typing import Any, Dict, Optional, Tuple
from pyatv.protocols.airplay.auth.hap import _AIRPLAY_HEADERS, _get_pairing_data, AirPlayHapPairSetupProcedure
from pyatv.protocols.airplay.srp import LegacySRPAuthHandler, new_credentials
from pyatv.protocols.airplay.auth.legacy import (
    AirPlayLegacyPairSetupProcedure,
    AirPlayLegacyPairVerifyProcedure,
)

_LOG = logging.getLogger(__name__)


@property
def patched_protocol_pairing_handler_device_provides_pin(self) -> bool:
    """Return True if remote device presents PIN code, else False."""
    return self.service.password is None

def patched_protocol_pairing_handler_pin(self, pin) -> None:
    """Pin code or password used for pairing."""
    pin_str = str(pin)
    self.pin_code = pin_str if pin_str == self.service.password else pin_str.zfill(4)

def patched_airplay_hap_pair_setup(
    auth_type: AuthenticationType,
    connection: HttpConnection,
    display_name: Optional[str] = None,
    ) -> PairSetupProcedure:
    """Return Pair-Setup procedure with an optional receiver-visible name."""
    _LOG.debug("Setting up new AirPlay Pair-Setup procedure with type %s", auth_type)

    if auth_type == AuthenticationType.Legacy:
        legacy_srp = LegacySRPAuthHandler(new_credentials())
        legacy_srp.initialize()
        return AirPlayLegacyPairSetupProcedure(connection, legacy_srp)
    if auth_type == AuthenticationType.HAP:
        srp = SRPAuthHandler()
        srp.initialize()
        return AirPlayHapPairSetupProcedure(connection, srp, display_name)

    raise exceptions.NotSupportedError(
        f"authentication type {auth_type} does not support Pair-Setup"
    )



def patched_airplay_hap_pair_setup_procedure_init(
            self: AirPlayHapPairSetupProcedure,
            http: HttpConnection,
            auth_handler: SRPAuthHandler,
            display_name: Optional[str] = None,
    ):
    """Initialize HAP pairing with an optional receiver-visible name."""
    self.http = http
    self.srp = auth_handler
    self._headers = copy(_AIRPLAY_HEADERS)
    if display_name:
        self._headers["X-Apple-Client-Name"] = display_name
    self._atv_salt = None
    self._atv_pub_key = None

async def patched_airplay_hap_pair_setup_procedure_start_pairing(self: AirPlayHapPairSetupProcedure) -> None:
        """Start the authentication process.

        This method will show the expected PIN on screen.
        """
        self.srp.initialize()

        await self.http.post("/pair-pin-start", headers=self._headers)

        data = {hap_tlv8.TlvValue.Method: b"\x00", hap_tlv8.TlvValue.SeqNo: b"\x01"}
        resp = await self.http.post(
            "/pair-setup", body=hap_tlv8.write_tlv(data), headers=self._headers
        )
        pairing_data = _get_pairing_data(resp)

        self._atv_salt = pairing_data[hap_tlv8.TlvValue.Salt]
        self._atv_pub_key = pairing_data[hap_tlv8.TlvValue.PublicKey]

async def patched_airplay_pairing_begin(self: AirPlayPairingHandler) -> None:
    """Start pairing process."""
    self.http = await http_connect(self.address, self.service.port)
    self.pairing_procedure = pair_setup(
        (
            AuthenticationType.HAP
            if self.airplay_version == AirPlayMajorVersion.AirPlayV2
            else AuthenticationType.Legacy
        ),
        self.http,
        self._name,
    )
    self._has_paired = False
    return await error_handler(
        self.pairing_procedure.start_pairing, exceptions.PairingError
    )
