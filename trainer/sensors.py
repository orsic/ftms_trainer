"""BLE sensors: GATT payload parsers and a self-reconnecting notification wrapper."""

import asyncio
import logging
import struct
import time
from typing import Any, Callable

from bleak import BleakClient

log = logging.getLogger(__name__)

STALE_AFTER = 3.0  # s without a notification -> value is treated as missing
CONNECT_TIMEOUT = 15.0
CADENCE_TIMEOUT = 2.5  # s without a new crank event -> cadence 0

INDOOR_BIKE_DATA = "00002ad2-0000-1000-8000-00805f9b34fb"
CYCLING_POWER_MEASUREMENT = "00002a63-0000-1000-8000-00805f9b34fb"
HEART_RATE_MEASUREMENT = "00002a37-0000-1000-8000-00805f9b34fb"

Parser = Callable[[bytes, float], dict[str, float]]


def parse_indoor_bike_data(data: bytes, now: float = 0.0) -> dict[str, float]:
    """FTMS Indoor Bike Data (0x2AD2): speed, cadence and power."""
    flags = struct.unpack_from("<H", data)[0]
    off, out = 2, {}
    if not flags & 0x0001:  # "More Data" clear -> instantaneous speed present
        out["speed"] = struct.unpack_from("<H", data, off)[0] / 100
        off += 2
    if flags & 0x0002:  # average speed
        off += 2
    if flags & 0x0004:
        out["cadence"] = struct.unpack_from("<H", data, off)[0] / 2
        off += 2
    if flags & 0x0008:  # average cadence
        off += 2
    if flags & 0x0010:  # total distance (uint24)
        off += 3
    if flags & 0x0020:  # resistance level
        off += 2
    if flags & 0x0040:
        out["power"] = struct.unpack_from("<h", data, off)[0]
    return out


class CyclingPower:
    """Cycling Power Measurement (0x2A63) parser; keeps crank state to derive cadence."""

    def __init__(self) -> None:
        self._prev: tuple[int, int] | None = None
        self._cadence: float | None = None
        self._last_event = 0.0

    def __call__(self, data: bytes, now: float) -> dict[str, float]:
        flags, power = struct.unpack_from("<Hh", data)
        off, out = 4, {"power": power}
        if flags & 0x01:
            if flags & 0x02:  # reference is the left pedal
                out["balance_left"] = data[off] / 2
            off += 1
        if flags & 0x04:  # accumulated torque
            off += 2
        if flags & 0x10:  # wheel revolution data
            off += 6
        if flags & 0x20:
            revs, t = struct.unpack_from("<HH", data, off)
            if self._prev is None:
                self._last_event = now
            else:
                d_revs = (revs - self._prev[0]) & 0xFFFF
                d_t = (t - self._prev[1]) & 0xFFFF
                if d_t:
                    self._cadence = d_revs * 60 * 1024 / d_t
                    self._last_event = now
                elif now - self._last_event > CADENCE_TIMEOUT:
                    self._cadence = 0.0
            self._prev = (revs, t)
            if self._cadence is not None:
                out["cadence"] = self._cadence
        return out


def parse_heart_rate(data: bytes, now: float = 0.0) -> dict[str, float]:
    """Heart Rate Measurement (0x2A37)."""
    if data[0] & 0x01:
        return {"heart_rate": struct.unpack_from("<H", data, 1)[0]}
    return {"heart_rate": data[1]}


class FatalSensorError(Exception):
    """Raised from on_connected when retrying cannot help (e.g. trainer lacks ERG)."""


class Sensor:
    """Connects to one BLE device, keeps the latest parsed values, reconnects forever.

    status: off (no address configured) | connecting | ok | missing | reconnecting
    """

    def __init__(
        self,
        name: str,
        address: str,
        char_uuid: str,
        parser: Parser,
        client_factory: Callable[..., Any] = BleakClient,
        clock: Callable[[], float] = time.monotonic,
        retry_delay: float = 5.0,
    ) -> None:
        self.name = name
        self.address = address
        self.char_uuid = char_uuid
        self.parser = parser
        self.status = "connecting" if address else "off"
        self.client: Any = None
        self._client_factory = client_factory
        self._clock = clock
        self._retry_delay = retry_delay
        self._values: dict[str, float] = {}
        self._updated = float("-inf")

    def value(self, key: str) -> float | None:
        if self._clock() - self._updated > STALE_AFTER:
            return None
        return self._values.get(key)

    def _on_notify(self, _char: Any, data: bytearray) -> None:
        now = self._clock()
        self._values.update(self.parser(bytes(data), now))
        self._updated = now

    async def on_connected(self, client: Any) -> None:
        await client.start_notify(self.char_uuid, self._on_notify)

    def on_disconnected(self) -> None:
        pass

    async def run(self) -> None:
        if not self.address:
            return
        ever_connected = False
        while True:
            disconnected = asyncio.Event()
            try:
                async with self._client_factory(
                    self.address,
                    disconnected_callback=lambda _: disconnected.set(),
                    timeout=CONNECT_TIMEOUT,
                ) as client:
                    await self.on_connected(client)
                    self.client = client
                    self.status = "ok"
                    ever_connected = True
                    log.info("%s connected", self.name)
                    await disconnected.wait()
            except FatalSensorError:
                raise
            except Exception as e:  # BLE stacks raise a zoo of errors; keep retrying
                log.warning("%s: %s: %s", self.name, type(e).__name__, e)
            finally:
                self.client = None
                self.on_disconnected()
            self.status = "reconnecting" if ever_connected else "missing"
            log.info("%s %s, retrying", self.name, self.status)
            await asyncio.sleep(self._retry_delay)
