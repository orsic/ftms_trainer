"""Where in the workout we are, and what the target is."""

from dataclasses import dataclass

from trainer.zwo import Workout

FTP_STEP = 5


@dataclass(frozen=True)
class Position:
    index: int | None  # None once the workout is finished
    fraction: float | None  # target as FTP fraction; None for free ride / finished
    segment_remaining: float

    @property
    def finished(self) -> bool:
        return self.index is None


def position(workout: Workout, elapsed: float) -> Position:
    start = 0.0
    for i, seg in enumerate(workout.segments):
        if elapsed < start + seg.duration:
            into = elapsed - start
            fraction = None
            if seg.power_start is not None and seg.power_end is not None:
                fraction = seg.power_start + (seg.power_end - seg.power_start) * into / seg.duration
            return Position(i, fraction, seg.duration - into)
        start += seg.duration
    return Position(None, None, 0.0)


def target_watts(fraction: float | None, ftp: int) -> int | None:
    return None if fraction is None else round(fraction * ftp)
