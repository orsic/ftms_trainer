"""The device interface a ride depends on, and the strategy that builds the real BLE devices.

A DeviceStrategy builds a Devices bundle; Session only talks to that bundle, so real
Bluetooth hardware (BleDevices) and the simulation (demo.DemoDevices) are interchangeable.
"""

import os
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol

from trainer.click import Click
from trainer.ftms import Trainer
from trainer.sensors import (
    CYCLING_POWER_MEASUREMENT,
    HEART_RATE_MEASUREMENT,
    CyclingPower,
    Sensor,
    parse_heart_rate,
)


class SensorLike(Protocol):
    name: str
    status: str

    def value(self, key: str) -> float | None: ...

    async def run(self) -> None: ...


class TrainerLike(SensorLike, Protocol):
    async def set_target(self, watts: int | None) -> None: ...


@dataclass
class Devices:
    trainer: TrainerLike
    power_meter: SensorLike
    heart_rate: SensorLike
    click: SensorLike
    clock: Callable[[], float] = time.monotonic
    wall: Callable[[], float] = time.time
    tick_interval: float = 1.0  # real seconds between ticks (one tick = one workout second)


class DeviceStrategy(Protocol):
    def build(self, on_action: Callable[[str], None]) -> Devices:
        """Create the devices; Click button presses are reported through `on_action`."""
        ...


@dataclass
class BleDevices:
    """Real Bluetooth devices, addressed from vars.env."""

    trainer_addr: str
    power_meter_addr: str = ""
    heart_rate_addr: str = ""
    click_addr: str = ""

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "BleDevices":
        if not env.get("TRAINER_ADDR"):
            raise ValueError("TRAINER_ADDR is not set in vars.env (find it with `./run.sh scan`)")
        return cls(
            env["TRAINER_ADDR"],
            env.get("POWER_METER_ADDR", ""),
            env.get("HEART_RATE_ADDR", ""),
            env.get("CLICK_ADDR", ""),
        )

    def build(self, on_action: Callable[[str], None]) -> Devices:
        return Devices(
            Trainer(self.trainer_addr),
            Sensor("4iiii", self.power_meter_addr, CYCLING_POWER_MEASUREMENT, CyclingPower()),
            Sensor("HR", self.heart_rate_addr, HEART_RATE_MEASUREMENT, parse_heart_rate),
            Click(self.click_addr, on_action=on_action),
        )
