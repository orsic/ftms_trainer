"""Zwift Click v2 (right controller) over BLE: handshake, keepalive and button decoding."""

import asyncio
import logging
from typing import Any, Callable

from trainer.sensors import Sensor

log = logging.getLogger(__name__)

ZWIFT_SERVICES = ("0000fc82-0000-1000-8000-00805f9b34fb", "00000001-19ca-4651-86e5-fa29dcdd09d1")
ASYNC_CHAR = "00000002-19ca-4651-86e5-fa29dcdd09d1"  # notify: button frames
SYNC_RX_CHAR = "00000003-19ca-4651-86e5-fa29dcdd09d1"  # write: commands
SYNC_TX_CHAR = "00000004-19ca-4651-86e5-fa29dcdd09d1"  # indicate: responses
HANDSHAKE = b"RideOn"
KEEPALIVE = 3.0  # s; the controller deep-sleeps after ~56 s without traffic
KEYPAD_STATUS = 0x23
LONG_PRESS = 0.6  # s

# Bit positions in the keypad bitmask (Zwift Ride layout). Verify with `click-learn`.
BUTTON_BITS = {"A": 4, "B": 5, "Y": 6, "Z": 7, "PLUS": 12}

ACTIONS = {
    ("A", False): "play_pause",
    ("Y", False): "volume_up",
    ("B", False): "volume_down",
    ("Z", False): "next",
    ("Z", True): "previous",
    ("PLUS", False): "ftp_up",
    ("PLUS", True): "ftp_down",
}


def encode_varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _read_varint(data: bytes, off: int) -> tuple[int, int]:
    value, shift = 0, 0
    while True:
        byte = data[off]
        off += 1
        value |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            return value, off


def parse_pressed_mask(data: bytes) -> int | None:
    """Return a bitmask of pressed buttons (1 = pressed) from a 0x23 keypad frame."""
    if not data or data[0] != KEYPAD_STATUS:
        return None
    off = 1
    while off < len(data):
        key, off = _read_varint(data, off)
        field, wire = key >> 3, key & 0x07
        if wire == 0:
            value, off = _read_varint(data, off)
            if field == 1:
                return ~value & 0xFFFFFFFF  # buttons are active-low
        elif wire == 2:
            length, off = _read_varint(data, off)
            off += length
        elif wire == 5:
            off += 4
        elif wire == 1:
            off += 8
        else:
            return None
    return None


class ButtonDecoder:
    """Turns successive pressed-masks into (button, is_long) events on release."""

    def __init__(self, bits: dict[str, int] = BUTTON_BITS, long_press: float = LONG_PRESS) -> None:
        self._bits = bits
        self._long_press = long_press
        self._down: dict[str, float] = {}

    def feed(self, pressed: int, now: float) -> list[tuple[str, bool]]:
        events = []
        for name, bit in self._bits.items():
            if pressed >> bit & 1:
                self._down.setdefault(name, now)
            elif name in self._down:
                events.append((name, now - self._down.pop(name) >= self._long_press))
        return events


def action_for(button: str, long: bool) -> str | None:
    return ACTIONS.get((button, long)) or ACTIONS.get((button, False))


def _find_char(client: Any, uuid: str, prop: str) -> Any:
    """Look up by known UUID, else by property within the Zwift service."""
    char = client.services.get_characteristic(uuid)
    if char is not None:
        return char
    for service in client.services:
        if service.uuid in ZWIFT_SERVICES:
            for c in service.characteristics:
                if prop in c.properties:
                    return c
    raise RuntimeError(f"Zwift characteristic {uuid} not found")


class Click(Sensor):
    def __init__(
        self,
        address: str,
        on_action: Callable[[str], None],
        on_mask: Callable[[int], None] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__("Click", address, ASYNC_CHAR, lambda d, n: {}, **kwargs)
        self._on_action = on_action
        self._on_mask = on_mask
        self._decoder = ButtonDecoder()
        self._keepalive: asyncio.Task | None = None

    def _on_notify(self, _char: Any, data: bytearray) -> None:
        pressed = parse_pressed_mask(bytes(data))
        if pressed is None:
            return
        if self._on_mask is not None:
            self._on_mask(pressed)
        for button, long in self._decoder.feed(pressed, self._clock()):
            action = action_for(button, long)
            if action is not None:
                self._on_action(action)

    async def on_connected(self, client: Any) -> None:
        rx = _find_char(client, SYNC_RX_CHAR, "write")
        await client.start_notify(_find_char(client, ASYNC_CHAR, "notify"), self._on_notify)
        await client.start_notify(_find_char(client, SYNC_TX_CHAR, "indicate"), self._on_notify)
        await client.write_gatt_char(rx, HANDSHAKE, response=True)
        self._keepalive = asyncio.create_task(self._send_keepalive(client, rx))

    async def _send_keepalive(self, client: Any, rx: Any) -> None:
        while True:
            await asyncio.sleep(KEEPALIVE)
            try:
                await client.write_gatt_char(rx, HANDSHAKE, response=True)
            except Exception as e:
                log.warning("Click keepalive failed: %s", e)
                return

    def on_disconnected(self) -> None:
        if self._keepalive is not None:
            self._keepalive.cancel()
            self._keepalive = None
