import asyncio
import struct

import pytest

from trainer.sensors import CyclingPower, Sensor, parse_heart_rate, parse_indoor_bike_data


def test_indoor_bike_data_speed_cadence_power() -> None:
    # flags: speed present (bit0 clear), cadence (bit2), power (bit6)
    data = struct.pack("<HHHh", 0x0044, 3420, 182, 251)
    assert parse_indoor_bike_data(data) == {"speed": 34.2, "cadence": 91.0, "power": 251}


def test_indoor_bike_data_skips_optional_fields() -> None:
    # avg speed (bit1), avg cadence (bit3), distance (bit4, 3 bytes), resistance (bit5)
    flags = 0x0002 | 0x0004 | 0x0008 | 0x0010 | 0x0020 | 0x0040
    data = struct.pack("<HHHHH", flags, 1000, 999, 160, 999) + b"\x01\x02\x03" + struct.pack("<hh", 7, -3)
    assert parse_indoor_bike_data(data) == {"speed": 10.0, "cadence": 80.0, "power": -3}


def test_indoor_bike_data_more_data_without_power() -> None:
    assert parse_indoor_bike_data(struct.pack("<H", 0x0001)) == {}


def cps(power: int, balance: int | None = None, crank: tuple[int, int] | None = None) -> bytes:
    flags, body = 0, b""
    if balance is not None:
        flags |= 0x03  # balance present, reference = left
        body += bytes([balance])
    if crank is not None:
        flags |= 0x20
        body += struct.pack("<HH", *crank)
    return struct.pack("<Hh", flags, power) + body


def test_cycling_power_balance_and_power() -> None:
    p = CyclingPower()
    assert p(cps(244, balance=98), 0.0) == {"power": 244, "balance_left": 49.0}


def test_cycling_power_balance_without_left_reference_ignored() -> None:
    data = struct.pack("<HhB", 0x01, 200, 100)
    assert CyclingPower()(data, 0.0) == {"power": 200}


def test_cycling_power_cadence_from_crank_revs() -> None:
    p = CyclingPower()
    assert p(cps(200, crank=(10, 1000)), 0.0) == {"power": 200}
    assert p(cps(200, crank=(13, 1000 + 2048)), 2.0)["cadence"] == pytest.approx(90.0)


def test_cycling_power_cadence_rollover() -> None:
    p = CyclingPower()
    p(cps(200, crank=(0xFFFF, 0xFC00)), 0.0)
    # +2 revs, +1024 ticks (1 s) across both rollovers -> 120 rpm
    assert p(cps(200, crank=(1, 0x0000)), 1.0)["cadence"] == pytest.approx(120.0)


def test_cycling_power_cadence_drops_to_zero_when_coasting() -> None:
    p = CyclingPower()
    p(cps(0, crank=(10, 1000)), 0.0)
    p(cps(0, crank=(12, 2024)), 1.0)
    assert p(cps(0, crank=(12, 2024)), 2.0)["cadence"] > 0  # repeated event, still recent
    assert p(cps(0, crank=(12, 2024)), 5.0)["cadence"] == 0.0


def test_heart_rate_uint8_and_uint16() -> None:
    assert parse_heart_rate(bytes([0x00, 152]), 0.0) == {"heart_rate": 152}
    assert parse_heart_rate(bytes([0x01]) + struct.pack("<H", 301), 0.0) == {"heart_rate": 301}


class FakeClient:
    """Stands in for BleakClient; `attempts` decides which connects fail."""

    def __init__(self, attempts: list[bool], address: str, disconnected_callback, timeout: float) -> None:
        self.ok = attempts.pop(0)
        self.disconnect_cb = disconnected_callback
        self.notify = None

    async def __aenter__(self) -> "FakeClient":
        if not self.ok:
            raise TimeoutError("not found")
        FakeClient.last = self
        return self

    async def __aexit__(self, *exc) -> None:
        pass

    async def start_notify(self, uuid: str, cb) -> None:
        self.notify = cb


async def test_sensor_retries_then_reports_values_and_staleness() -> None:
    attempts = [False, True]
    now = [0.0]
    s = Sensor(
        "HR",
        "AA:BB",
        "2a37",
        parse_heart_rate,
        client_factory=lambda *a, **kw: FakeClient(attempts, *a, **kw),
        clock=lambda: now[0],
        retry_delay=0,
    )
    task = asyncio.create_task(s.run())
    for _ in range(20):
        await asyncio.sleep(0)
    assert s.status == "ok"
    FakeClient.last.notify(None, bytearray([0, 140]))
    assert s.value("heart_rate") == 140
    now[0] = 10.0
    assert s.value("heart_rate") is None
    FakeClient.last.disconnect_cb(None)
    await asyncio.sleep(0)
    assert s.status == "reconnecting"
    task.cancel()


async def test_sensor_without_address_is_off() -> None:
    s = Sensor("HR", "", "2a37", parse_heart_rate)
    await s.run()
    assert s.status == "off"
    assert s.value("heart_rate") is None
