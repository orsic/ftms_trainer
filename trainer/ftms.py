"""FTMS smart trainer: Indoor Bike Data + Control Point (ERG / simulation)."""

import logging
import struct
from typing import Any

from trainer.sensors import INDOOR_BIKE_DATA, FatalSensorError, Sensor, parse_indoor_bike_data

log = logging.getLogger(__name__)

FEATURE = "00002acc-0000-1000-8000-00805f9b34fb"
CONTROL_POINT = "00002ad9-0000-1000-8000-00805f9b34fb"

REQUEST_CONTROL = b"\x00"
START = b"\x07"
POWER_TARGET_SUPPORTED = 1 << 3  # bit in Target Setting Features


def set_target_power(watts: int) -> bytes:
    return struct.pack("<Bh", 0x05, watts)


def set_simulation(grade_percent: float) -> bytes:
    # wind 0 m/s, grade in 0.01 %, Crr 0.0040, CwA 0.51 kg/m
    return struct.pack("<BhhBB", 0x11, 0, round(grade_percent * 100), 40, 51)


def supports_power_target(features: bytes) -> bool:
    _, target_features = struct.unpack_from("<II", features)
    return bool(target_features & POWER_TARGET_SUPPORTED)


class Trainer(Sensor):
    def __init__(self, address: str, **kwargs: Any) -> None:
        super().__init__("D100", address, INDOOR_BIKE_DATA, parse_indoor_bike_data, **kwargs)
        self._command: bytes | None = None

    async def on_connected(self, client: Any) -> None:
        if not supports_power_target(await client.read_gatt_char(FEATURE)):
            raise FatalSensorError("Trainer does not support FTMS target power (ERG)")
        await client.start_notify(CONTROL_POINT, self._on_control_point)
        await client.start_notify(INDOOR_BIKE_DATA, self._on_notify)
        for cmd in (REQUEST_CONTROL, START):
            await client.write_gatt_char(CONTROL_POINT, cmd, response=True)
        if self._command is not None:
            await client.write_gatt_char(CONTROL_POINT, self._command, response=True)

    def _on_control_point(self, _char: Any, data: bytearray) -> None:
        # Response: 0x80, request opcode, result (1 = success)
        if len(data) >= 3 and data[0] == 0x80 and data[2] != 0x01:
            log.warning("FTMS opcode 0x%02x failed with result %d", data[1], data[2])

    async def set_target(self, watts: int | None) -> None:
        """ERG at `watts`, or flat simulation (free ride) when None."""
        cmd = set_simulation(0.0) if watts is None else set_target_power(watts)
        if cmd == self._command:
            return
        self._command = cmd
        if self.client is not None:
            try:
                await self.client.write_gatt_char(CONTROL_POINT, cmd, response=True)
            except Exception as e:
                log.warning("FTMS write failed: %s", e)
