"""Ride orchestration: 1 Hz control/record tick, Click actions, sensor lifecycles."""

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Protocol

from trainer.media import run_media
from trainer.tui import Snapshot
from trainer.workout import FTP_STEP, position, target_watts
from trainer.zwo import Workout

log = logging.getLogger(__name__)


class SensorLike(Protocol):
    name: str
    status: str

    def value(self, key: str) -> float | None: ...

    async def run(self) -> None: ...


class TrainerMissing(Exception):
    pass


class Session:
    def __init__(
        self,
        workout: Workout,
        ftp: int,
        trainer: Any,
        power_meter: SensorLike,
        heart_rate: SensorLike,
        click: SensorLike,
        recorder: Any,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
        media: Callable[[str], Awaitable[None]] = run_media,
    ) -> None:
        self.workout = workout
        self.ftp = self.base_ftp = ftp
        self.trainer, self.power_meter, self.heart_rate, self.click = trainer, power_meter, heart_rate, click
        self.recorder = recorder
        self.last_action = ""
        self.started_at: float | None = None
        self._clock, self._wall, self._media = clock, wall, media
        self._tasks: set[asyncio.Task] = set()

    @property
    def sensors(self) -> list[SensorLike]:
        return [self.trainer, self.power_meter, self.heart_rate, self.click]

    def on_action(self, action: str) -> None:
        if action == "ftp_up":
            self.ftp += FTP_STEP
            self.last_action = f"FTP +{FTP_STEP} → {self.ftp} W"
        elif action == "ftp_down":
            self.ftp = max(FTP_STEP, self.ftp - FTP_STEP)
            self.last_action = f"FTP -{FTP_STEP} → {self.ftp} W"
        else:
            task = asyncio.create_task(self._media(action))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            self.last_action = action.replace("_", " ")
        log.info("action: %s", self.last_action)

    def _pedaling(self) -> bool:
        readings = (
            self.trainer.value("power"),
            self.trainer.value("cadence"),
            self.power_meter.value("power"),
        )
        return any(v for v in readings)

    async def tick(self) -> Snapshot:
        now = self._clock()
        if self.started_at is None and self._pedaling():
            self.started_at = now
        elapsed = 0.0 if self.started_at is None else now - self.started_at
        pos = position(self.workout, elapsed)
        target = target_watts(pos.fraction, self.ftp)
        await self.trainer.set_target(target)

        t, pm, hr = self.trainer, self.power_meter, self.heart_rate
        if self.started_at is not None:
            self.recorder.write(
                {
                    "timestamp": self._wall(),
                    "elapsed": round(elapsed, 1),
                    "segment": pos.index,
                    "ftp": self.ftp,
                    "target_power": target,
                    "trainer_power": t.value("power"),
                    "trainer_cadence": t.value("cadence"),
                    "speed": t.value("speed"),
                    "pm_power": pm.value("power"),
                    "pm_cadence": pm.value("cadence"),
                    "pm_balance_left": pm.value("balance_left"),
                    "heart_rate": hr.value("heart_rate"),
                }
            )

        segments = self.workout.segments
        seg = segments[pos.index] if pos.index is not None else None
        nxt = segments[pos.index + 1] if pos.index is not None and pos.index + 1 < len(segments) else None
        cadence = t.value("cadence")
        return Snapshot(
            workout_name=self.workout.name,
            started=self.started_at is not None,
            finished=pos.finished,
            elapsed=elapsed,
            total=self.workout.total_duration,
            segment_index=pos.index,
            segment_count=len(segments),
            segment_kind=seg.kind if seg else "",
            segment_percent=pos.fraction,
            segment_duration=seg.duration if seg else 0,
            segment_remaining=pos.segment_remaining,
            next_segment=(nxt.duration, nxt.power_start) if nxt else None,
            target=target,
            ftp=self.ftp,
            ftp_delta=self.ftp - self.base_ftp,
            trainer_power=t.value("power"),
            pm_power=pm.value("power"),
            balance_left=pm.value("balance_left"),
            heart_rate=hr.value("heart_rate"),
            cadence=cadence if cadence is not None else pm.value("cadence"),
            speed=t.value("speed"),
            statuses={s.name: s.status for s in self.sensors},
            last_action=self.last_action,
        )


async def run_session(
    session: Session,
    stop: asyncio.Event,
    show: Callable[[Snapshot], None],
    trainer_timeout: float = 45.0,
    interval: float = 1.0,
) -> None:
    """Tick until `stop` is set. Raises TrainerMissing if the trainer never connects."""
    tasks = {s.name: asyncio.create_task(s.run()) for s in session.sensors}
    trainer_task = tasks[session.trainer.name]
    began = time.monotonic()
    trainer_seen = False
    next_tick = began
    try:
        while not stop.is_set():
            if trainer_task.done() and trainer_task.exception():
                raise trainer_task.exception()
            trainer_seen = trainer_seen or session.trainer.status == "ok"
            if not trainer_seen and time.monotonic() - began > trainer_timeout:
                raise TrainerMissing(f"{session.trainer.name} did not connect within {trainer_timeout:.0f} s")
            show(await session.tick())
            next_tick += interval
            try:
                await asyncio.wait_for(stop.wait(), max(0.0, next_tick - time.monotonic()))
            except TimeoutError:
                pass
    finally:
        for task in tasks.values():
            task.cancel()
        await asyncio.gather(*tasks.values(), return_exceptions=True)
