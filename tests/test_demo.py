import random

import pytest

from trainer.click import ACTIONS
from trainer.demo import KEYS, SimClock, demo_devices
from trainer.session import Session
from trainer.zwo import Segment, Workout


async def test_trainer_follows_target_with_noise() -> None:
    trainer, pm, hr, click = demo_devices(random.Random(1))
    await trainer.set_target(200)
    assert trainer.value("power") == pytest.approx(200, abs=20)
    assert pm.value("power") == pytest.approx(0.97 * trainer.value("power"), abs=20)
    assert pm.value("balance_left") == pytest.approx(49, abs=3)
    assert trainer.value("cadence") == pytest.approx(90, abs=10)
    assert 25 < trainer.value("speed") < 40
    assert click.status == "ok"


async def test_free_ride_uses_default_power() -> None:
    trainer, *_ = demo_devices(random.Random(1))
    await trainer.set_target(None)
    assert trainer.value("power") == pytest.approx(150, abs=20)


async def test_heart_rate_drifts_towards_effort() -> None:
    trainer, _, hr, _ = demo_devices(random.Random(1))
    await trainer.set_target(100)
    easy = hr.value("heart_rate")
    for _ in range(120):
        await trainer.set_target(300)
    assert hr.value("heart_rate") > easy + 30


def test_sim_clock_runs_faster() -> None:
    real = [100.0]
    sim = SimClock(10, clock=lambda: real[0], wall=lambda: 5000.0)
    assert sim.now() == 100.0 and sim.wall() == 5000.0
    real[0] = 101.0
    assert sim.now() == 110.0 and sim.wall() == 5010.0


def test_keys_cover_every_click_action() -> None:
    assert set(KEYS.values()) == set(ACTIONS.values())


async def test_session_with_demo_devices_records_every_field() -> None:
    rows = []

    class Rec:
        def write(self, row: dict) -> None:
            rows.append(row)

    workout = Workout("w", [Segment("SteadyState", 60, 0.8, 0.8)])
    now = [0.0]
    session = Session(workout, 250, *demo_devices(random.Random(1)), Rec(), clock=lambda: now[0])
    for t in range(3):
        now[0] = float(t)
        await session.tick()
    assert len(rows) == 2  # first tick primes the trainer, pedaling starts on the second
    assert all(v is not None for v in rows[-1].values())
