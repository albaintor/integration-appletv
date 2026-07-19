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


@property
def patched_protocol_pairing_handler_device_provides_pin(self) -> bool:
    """Return True if remote device presents PIN code, else False."""
    return self.service.password is None


def patched_protocol_pairing_handler_pin(self, pin) -> None:
    """Pin code or password used for pairing."""
    pin_str = str(pin)
    self.pin_code = pin_str if pin_str == self.service.password else pin_str.zfill(4)
