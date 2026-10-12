"""Curses dashboard. `render` is pure (and tested); `draw` just paints its output."""

import curses
from dataclasses import dataclass

Span = tuple[str, str]  # (text, color name or "")

STATUS_COLORS = {
    "ok": "green",
    "connecting": "yellow",
    "reconnecting": "yellow",
    "missing": "red",
    "off": "red",
}
COLOR_PAIRS = {"green": 1, "yellow": 2, "red": 3}
BAR_WIDTH = 25
CELL = 22


@dataclass
class Snapshot:
    workout_name: str
    started: bool
    finished: bool
    elapsed: float
    total: int
    segment_index: int | None
    segment_count: int
    segment_kind: str
    segment_percent: float | None
    segment_duration: int
    segment_remaining: float
    next_segment: tuple[int, float | None] | None  # (duration, FTP fraction)
    target: int | None
    ftp: int
    ftp_delta: int
    trainer_power: float | None
    pm_power: float | None
    balance_left: float | None
    heart_rate: float | None
    cadence: float | None
    speed: float | None
    statuses: dict[str, str]
    last_action: str


def _hms(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _ms(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}"


def _v(value: float | None, fmt: str = ".0f") -> str:
    return "--" if value is None else format(value, fmt)


def _pct(fraction: float | None) -> str:
    return "free" if fraction is None else f"{fraction * 100:.0f}%"


def _row(*cells: str) -> list[Span]:
    return [("  " + "".join(c.ljust(CELL) for c in cells).rstrip(), "")]


def _truncate(line: list[Span], width: int) -> list[Span]:
    out, left = [], width
    for text, color in line:
        if left <= 0:
            break
        out.append((text[:left], color))
        left -= len(text)
    return out


def render(s: Snapshot, width: int) -> list[list[Span]]:
    if not s.started:
        title = f"{s.workout_name} — Waiting for you to start pedaling"
    elif s.finished:
        title = f"{s.workout_name} — Workout done — free ride, q to finish"
    else:
        title = s.workout_name
    clock = f"{_hms(s.elapsed)} / {_hms(s.total)}"
    lines: list[list[Span]] = [[(title.ljust(max(width - len(clock), len(title) + 1)) + clock, "bold")]]

    if s.segment_index is None:
        lines += [[("Free ride", "")], []]
    else:
        nxt = "Last segment"
        if s.next_segment is not None:
            nxt = f"Next: {_ms(s.next_segment[0])} @ {_pct(s.next_segment[1])}"
        current = (
            f"Segment {s.segment_index + 1}/{s.segment_count}  {s.segment_kind} {_pct(s.segment_percent)}"
        )
        lines.append([(current.ljust(40) + nxt, "")])
        done = 1 - s.segment_remaining / s.segment_duration if s.segment_duration else 1
        filled = round(done * BAR_WIDTH)
        bar = "█" * filled + "░" * (BAR_WIDTH - filled)
        lines.append([(f"Segment left  {_ms(s.segment_remaining).rjust(5, '0')}   [{bar}]", "")])
    lines.append([])

    balance = "" if s.balance_left is None else f" ({s.balance_left:.0f}/{100 - s.balance_left:.0f})"
    target = "free" if s.target is None else f"{s.target} W"
    ftp_delta = f" ({s.ftp_delta:+d})" if s.ftp_delta else ""
    lines.append(
        _row(f"TARGET   {target}", f"TRAINER  {_v(s.trainer_power)} W", f"4iiii  {_v(s.pm_power)} W{balance}")
    )
    lines.append(
        _row(
            f"HR       {_v(s.heart_rate)} bpm",
            f"CADENCE  {_v(s.cadence)} rpm",
            f"SPEED  {_v(s.speed, '.1f')} km/h",
        )
    )
    lines.append(_row(f"FTP      {s.ftp} W{ftp_delta}"))
    lines.append([])

    status: list[Span] = []
    for name, state in s.statuses.items():
        dot = "●" if state == "ok" else "○"
        status += [(f"{name} {dot} {state}", STATUS_COLORS.get(state, "")), ("   ", "")]
    lines.append(status)
    lines.append([(f"last action: {s.last_action}", "")])
    lines.append([("q / Ctrl+C: finish and save", "")])
    return [_truncate(line, width) for line in lines]


def init_screen(scr: "curses.window") -> None:
    curses.curs_set(0)
    scr.nodelay(True)
    curses.start_color()
    curses.use_default_colors()
    for name, pair in COLOR_PAIRS.items():
        curses.init_pair(pair, getattr(curses, f"COLOR_{name.upper()}"), -1)


def draw(scr: "curses.window", snap: Snapshot) -> int:
    """Paint the snapshot; returns the last key pressed (or -1)."""
    height, width = scr.getmaxyx()
    scr.erase()
    try:
        scr.box()
        for y, line in enumerate(render(snap, width - 4)[: height - 2], start=1):
            x = 2
            for text, color in line:
                attr = curses.A_BOLD if color == "bold" else curses.color_pair(COLOR_PAIRS.get(color, 0))
                scr.addstr(y, x, text, attr)
                x += len(text)
    except curses.error:  # terminal too small; draw what fits
        pass
    scr.refresh()
    key, last = scr.getch(), -1
    while key != -1:
        key, last = scr.getch(), key
    return last
