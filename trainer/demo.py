"""Simulated devices for `ride --demo` (no Bluetooth needed)."""

import asyncio
import random
import time
from typing import Callable

from trainer.devices import Devices

FREE_RIDE_POWER = 150
PM_SCALE = 0.97  # simulated power meter reads ~3 % below the trainer


class DemoSensor:
    def __init__(self, name: str) -> None:
        self.name = name
        self.status = "ok"
        self.values: dict[str, float] = {}

    def value(self, key: str) -> float | None:
        return self.values.get(key)

    async def run(self) -> None:
        await asyncio.Event().wait()


class DemoTrainer(DemoSensor):
    """Hits the target with some noise and drives the other simulated sensors."""

    def __init__(self, power_meter: DemoSensor, heart_rate: DemoSensor, rng: random.Random) -> None:
        super().__init__("D100 (demo)")
        self._pm, self._hr, self._rng = power_meter, heart_rate, rng
        self._heart_rate = 90.0

    async def set_target(self, watts: int | None) -> None:
        gauss = self._rng.gauss
        power = max(0.0, (FREE_RIDE_POWER if watts is None else watts) + gauss(0, 5))
        cadence = 90 + gauss(0, 2)
        self.values = {
            "power": round(power),
            "cadence": round(cadence),
            "speed": round(5.5 * power ** (1 / 3), 1),
        }
        self._pm.values = {
            "power": round(power * PM_SCALE + gauss(0, 4)),
            "cadence": round(cadence + gauss(0, 1)),
            "balance_left": round(49 + gauss(0, 0.5), 1),
        }
        self._heart_rate += (70 + 0.35 * power - self._heart_rate) * 0.05
        self._hr.values = {"heart_rate": round(self._heart_rate)}


class SimClock:
    """Monotonic and wall clocks running `speed` times faster than real time."""

    def __init__(
        self, speed: float, clock: Callable[[], float] = time.monotonic, wall: Callable[[], float] = time.time
    ) -> None:
        self._speed, self._clock = speed, clock
        self._start, self._wall_start = clock(), wall()

    def now(self) -> float:
        return self._start + (self._clock() - self._start) * self._speed

    def wall(self) -> float:
        return self._wall_start + self.now() - self._start


class DemoDevices:
    """Strategy for simulated devices, running `speed` times faster than real time."""

    def __init__(self, speed: float = 1.0, rng: random.Random | None = None) -> None:
        self.speed = speed
        self.rng = rng or random.Random()

    def build(self, on_action: Callable[[str], None]) -> Devices:
        # on_action is unused: the simulated Click has no buttons, the keyboard stands in for it
        pm, hr = DemoSensor("4iiii (demo)"), DemoSensor("HR (demo)")
        sim = SimClock(self.speed)
        return Devices(
            DemoTrainer(pm, hr, self.rng),
            pm,
            hr,
            DemoSensor("Click (keys)"),
            clock=sim.now,
            wall=sim.wall,
            tick_interval=1.0 / self.speed,
        )
