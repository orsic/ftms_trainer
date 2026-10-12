import asyncio

import pytest

from trainer.devices import Devices
from trainer.session import Session, TrainerMissing, run_session
from trainer.zwo import Segment, Workout

WORKOUT = Workout("w", [Segment("SteadyState", 3, 0.8, 0.8), Segment("SteadyState", 2, 1.0, 1.0)])


class FakeSensor:
    def __init__(self, name: str, status: str = "ok", **values: float) -> None:
        self.name, self.status, self.values = name, status, values

    def value(self, key: str) -> float | None:
        return self.values.get(key)

    async def run(self) -> None:
        await asyncio.Event().wait()


class FakeTrainer(FakeSensor):
    def __init__(self, **kw) -> None:
        super().__init__("D100", **kw)
        self.targets: list[int | None] = []

    async def set_target(self, watts: int | None) -> None:
        self.targets.append(watts)


class ListRecorder:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def write(self, row: dict) -> None:
        self.rows.append(row)


class FakeStrategy:
    def __init__(self, devices: Devices) -> None:
        self.devices = devices
        self.on_action = None

    def build(self, on_action) -> Devices:
        self.on_action = on_action
        return self.devices


def make(now: list[float], **sensors) -> tuple[Session, FakeTrainer, ListRecorder, list[str]]:
    trainer = sensors.get("trainer", FakeTrainer())
    rec = ListRecorder()
    media_calls: list[str] = []

    async def media(action: str) -> None:
        media_calls.append(action)

    devices = Devices(
        trainer,
        sensors.get("pm", FakeSensor("4iiii", status="missing")),
        sensors.get("hr", FakeSensor("HR", status="off")),
        sensors.get("click", FakeSensor("Click", status="missing")),
        clock=lambda: now[0],
        wall=lambda: 1000.0 + now[0],
        tick_interval=0.01,
    )
    s = Session(WORKOUT, 250, FakeStrategy(devices), rec, media=media)
    return s, trainer, rec, media_calls


async def test_waits_for_pedaling_before_recording() -> None:
    now = [0.0]
    s, trainer, rec, _ = make(now)
    snap = await s.tick()
    assert not snap.started and rec.rows == []
    assert trainer.targets == [200]  # ERG is primed with the first target
    trainer.values = {"power": 120.0}
    now[0] = 1.0
    snap = await s.tick()
    assert snap.started and rec.rows[0]["elapsed"] == 0.0


async def test_rides_with_missing_and_dropping_sensors() -> None:
    now = [0.0]
    pm = FakeSensor("4iiii", power=195.0, balance_left=49.0, cadence=90.0)
    s, trainer, rec, _ = make(now, trainer=FakeTrainer(power=200.0, cadence=88.0, speed=30.0), pm=pm)
    for t in range(7):
        now[0] = float(t)
        if t == 2:
            pm.values = {}  # power meter drops out
        await s.tick()
    assert [r["pm_power"] for r in rec.rows] == [195.0, 195.0, None, None, None, None, None]
    assert all(r["heart_rate"] is None for r in rec.rows)
    assert [r["target_power"] for r in rec.rows] == [200, 200, 200, 250, 250, None, None]
    assert trainer.targets[-1] is None  # finished -> free ride
    assert rec.rows[-1]["segment"] is None


async def test_ftp_buttons_shift_target_and_media_dispatch() -> None:
    now = [0.0]
    s, trainer, rec, media_calls = make(now, trainer=FakeTrainer(power=200.0))
    await s.tick()
    s.on_action("ftp_up")
    s.on_action("ftp_up")
    s.on_action("ftp_down")
    s.on_action("next")
    await asyncio.sleep(0)
    snap = await s.tick()
    assert snap.ftp == 255 and snap.ftp_delta == 5
    assert trainer.targets[-1] == 204
    assert media_calls == ["next"]
    assert snap.last_action == "next"


async def test_missing_trainer_aborts() -> None:
    now = [0.0]
    s, trainer, _, _ = make(now, trainer=FakeTrainer(status="missing"))
    with pytest.raises(TrainerMissing):
        await run_session(s, asyncio.Event(), lambda snap: None, trainer_timeout=0.05)


async def test_stop_event_ends_session() -> None:
    now = [0.0]
    s, _, _, _ = make(now)
    stop = asyncio.Event()
    shown = []

    def show(snap) -> None:
        shown.append(snap)
        stop.set()

    await run_session(s, stop, show)
    assert len(shown) == 1


def test_strategy_receives_session_action_handler() -> None:
    s, *_ = make([0.0])
    assert s.strategy.on_action == s.on_action
