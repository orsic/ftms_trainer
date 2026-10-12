import pytest

from trainer.workout import position, target_watts
from trainer.zwo import Segment, Workout

W = Workout(
    "w",
    [
        Segment("Warmup", 100, 0.5, 1.0),
        Segment("SteadyState", 60, 0.9, 0.9),
        Segment("FreeRide", 30, None, None),
    ],
)


def test_start_of_ramp() -> None:
    p = position(W, 0)
    assert (p.index, p.fraction, p.segment_remaining) == (0, 0.5, 100)


def test_ramp_interpolation() -> None:
    assert position(W, 50).fraction == pytest.approx(0.75)


def test_segment_boundary_belongs_to_next_segment() -> None:
    p = position(W, 100)
    assert (p.index, p.fraction, p.segment_remaining) == (1, 0.9, 60)


def test_free_ride_has_no_fraction() -> None:
    p = position(W, 170)
    assert (p.index, p.fraction) == (2, None)


def test_finished() -> None:
    p = position(W, 190)
    assert p.finished and p.index is None and p.fraction is None


def test_target_watts_follows_ftp() -> None:
    assert target_watts(0.9, 250) == 225
    assert target_watts(0.9, 255) == 230
    assert target_watts(None, 250) is None
