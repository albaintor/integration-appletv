"""Regression tests for Apple TV app launching."""

import asyncio
from pathlib import Path
import sys
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

import pyatv
from pyatv.const import FeatureName, Protocol
from ucapi import StatusCodes

sys.path.insert(0, str(Path(__file__).parents[1] / "intg-appletv"))

from config import AtvDevice
from tv import AppleTv


def _device() -> AtvDevice:
    return AtvDevice(
        identifier="test-device",
        name="Test Apple TV",
        credentials=[
            {"protocol": "airplay", "credentials": "airplay-creds"},
            {"protocol": "companion", "credentials": "companion-creds"},
        ],
    )


class AppLaunchTests(IsolatedAsyncioTestCase):
    """Cover incomplete discovery and app-launch error handling."""

    async def test_partial_discovery_is_retried_instead_of_connected(self) -> None:
        apple_tv = AppleTv(_device(), asyncio.get_running_loop())
        conf = MagicMock()
        conf.name = "Test Apple TV"
        conf.get_service.side_effect = lambda protocol: object() if protocol is Protocol.AirPlay else None
        apple_tv._apple_tv_conf = conf  # noqa: SLF001

        with patch("tv.pyatv.connect", new_callable=AsyncMock) as connect:
            await apple_tv._connect(conf)  # noqa: SLF001

        connect.assert_not_awaited()
        self.assertIsNone(apple_tv._apple_tv_conf)  # noqa: SLF001

    async def test_stale_app_list_is_cleared_when_companion_is_unavailable(self) -> None:
        apple_tv = AppleTv(_device(), asyncio.get_running_loop())
        apple_tv._app_list = {"YouTube": "com.google.ios.youtube"}  # noqa: SLF001
        apple_tv._atv = MagicMock()  # noqa: SLF001
        apple_tv._atv.apps.app_list = AsyncMock(side_effect=pyatv.exceptions.NotSupportedError())  # noqa: SLF001

        await apple_tv._update_app_list()  # noqa: SLF001

        self.assertEqual(apple_tv.app_names, [])

    async def test_launch_app_returns_service_unavailable_when_feature_is_missing(self) -> None:
        apple_tv = AppleTv(_device(), asyncio.get_running_loop())
        apple_tv._atv = MagicMock()  # noqa: SLF001
        apple_tv._atv.features.in_state.return_value = False  # noqa: SLF001

        result = await apple_tv.launch_app("YouTube")

        self.assertEqual(result, StatusCodes.SERVICE_UNAVAILABLE)
        apple_tv._atv.apps.launch_app.assert_not_called()  # noqa: SLF001
        apple_tv._atv.features.in_state.assert_called_once_with(  # noqa: SLF001
            pyatv.const.FeatureState.Available,
            FeatureName.LaunchApp,
        )

    async def test_launch_app_uses_bundle_id(self) -> None:
        apple_tv = AppleTv(_device(), asyncio.get_running_loop())
        apple_tv._app_list = {"YouTube": "com.google.ios.youtube"}  # noqa: SLF001
        apple_tv._atv = MagicMock()  # noqa: SLF001
        apple_tv._atv.features.in_state.return_value = True  # noqa: SLF001
        apple_tv._atv.apps.launch_app = AsyncMock()  # noqa: SLF001

        result = await apple_tv.launch_app("YouTube")

        self.assertEqual(result, StatusCodes.OK)
        apple_tv._atv.apps.launch_app.assert_awaited_once_with("com.google.ios.youtube")  # noqa: SLF001
