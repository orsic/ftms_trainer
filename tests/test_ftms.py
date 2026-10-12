import struct

import pytest

from trainer.ftms import (
    CONTROL_POINT,
    FEATURE,
    INDOOR_BIKE_DATA,
    REQUEST_CONTROL,
    START,
    Trainer,
    set_simulation,
    set_target_power,
    supports_power_target,
)
from trainer.sensors import FatalSensorError


def test_encoders() -> None:
    assert REQUEST_CONTROL == b"\x00"
    assert START == b"\x07"
    assert set_target_power(248) == b"\x05\xf8\x00"
    assert set_simulation(0.0) == struct.pack("<BhhBB", 0x11, 0, 0, 40, 51)
    assert set_simulation(2.5)[3:5] == struct.pack("<h", 250)


def test_power_target_feature_bit() -> None:
    assert supports_power_target(struct.pack("<II", 0, 1 << 3))
    assert not supports_power_target(struct.pack("<II", 0xFFFFFFFF, 0))


class FakeClient:
    def __init__(self, features: bytes) -> None:
        self.features = features
        self.writes: list[bytes] = []
        self.notified: list[str] = []

    async def read_gatt_char(self, uuid: str) -> bytes:
        assert uuid == FEATURE
        return self.features

    async def start_notify(self, uuid: str, cb) -> None:
        self.notified.append(uuid)

    async def write_gatt_char(self, uuid: str, data: bytes, response: bool) -> None:
        assert uuid == CONTROL_POINT
        self.writes.append(bytes(data))


ERG = struct.pack("<II", 0, 1 << 3)


async def test_connect_takes_control_and_replays_last_target() -> None:
    t = Trainer("AA")
    await t.set_target(200)  # before connection: remembered only
    c = FakeClient(ERG)
    await t.on_connected(c)
    t.client = c
    assert c.notified == [CONTROL_POINT, INDOOR_BIKE_DATA]
    assert c.writes == [REQUEST_CONTROL, START, set_target_power(200)]


async def test_set_target_only_sends_changes_and_none_means_sim() -> None:
    t = Trainer("AA")
    c = FakeClient(ERG)
    await t.on_connected(c)
    t.client = c
    c.writes.clear()
    await t.set_target(200)
    await t.set_target(200)
    await t.set_target(None)
    assert c.writes == [set_target_power(200), set_simulation(0.0)]


async def test_no_erg_is_fatal() -> None:
    with pytest.raises(FatalSensorError):
        await Trainer("AA").on_connected(FakeClient(struct.pack("<II", 0, 0)))
