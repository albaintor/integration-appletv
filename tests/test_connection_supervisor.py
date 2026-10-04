"""Tests for the Apple TV connection supervisor lifecycle."""

import asyncio

import pytest

from config import AtvDevice
from tv import AppleTv


@pytest.mark.asyncio
async def test_repeated_connect_uses_one_supervisor_and_disconnect_waits_for_cancel(monkeypatch) -> None:
    """Repeated connect calls must not create overlapping connection loops."""
    device = AtvDevice(identifier="test-atv", name="Test Apple TV", credentials=[])
    atv = AppleTv(device)
    started = asyncio.Event()
    never_complete = asyncio.Event()

    async def fake_connect_once() -> bool:
        started.set()
        await never_complete.wait()
        return False

    monkeypatch.setattr(atv, "_connect_once", fake_connect_once)

    await atv.connect()
    await asyncio.wait_for(started.wait(), timeout=1.0)

    first_task = getattr(atv, "_connect_task")
    assert first_task is not None
    assert not first_task.done()

    # A duplicate CONNECT/SUBSCRIBE event must remain idempotent.
    await atv.connect()
    assert getattr(atv, "_connect_task") is first_task

    # disconnect() must propagate cancellation into _connect_once(), await the
    # supervisor, and only then release the task slot.
    await atv.disconnect()
    assert first_task.done()
    assert first_task.cancelled()
    assert getattr(atv, "_connect_task") is None

    # The deferred reconnect callback must not restart while the device is disabled.
    await asyncio.sleep(0)
    assert getattr(atv, "_connect_task") is None
