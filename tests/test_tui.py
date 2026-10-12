from trainer.tui import Snapshot, render


def snap(**overrides) -> Snapshot:
    base = dict(
        workout_name="Sweet Spot",
        started=True,
        finished=False,
        elapsed=1421.0,
        total=3600,
        segment_index=3,
        segment_count=9,
        segment_kind="SteadyState",
        segment_percent=90.0,
        segment_duration=600,
        segment_remaining=379.0,
        next_segment=(300, 0.55),
        target=248,
        ftp=275,
        ftp_delta=5,
        trainer_power=251.0,
        pm_power=244.0,
        balance_left=49.0,
        heart_rate=None,
        cadence=91.0,
        speed=34.2,
        statuses={"D100": "ok", "4iiii": "ok", "HR": "missing", "Click": "reconnecting"},
        last_action="FTP +5 → 275 W",
    )
    base.update(overrides)
    return Snapshot(**base)


def text(lines) -> str:
    return "\n".join("".join(t for t, _ in spans) for spans in lines)


def test_main_values_rendered() -> None:
    out = text(render(snap(), 80))
    assert "00:23:41 / 01:00:00" in out
    assert "Segment 4/9" in out and "Next: 5:00 @ 55%" in out
    assert "06:19" in out
    assert "248 W" in out and "251 W" in out and "244 W (49/51)" in out
    assert "275 W (+5)" in out
    assert "FTP +5 → 275 W" in out


def test_missing_values_show_dashes() -> None:
    out = text(render(snap(pm_power=None, balance_left=None, cadence=None, target=None), 80))
    assert "HR       -- bpm" in out
    assert "4iiii  -- W" in out
    assert "CADENCE  -- rpm" in out
    assert "TARGET   free" in out


def test_status_colors() -> None:
    spans = dict(s for line in render(snap(), 80) for s in line if s[1])
    assert spans["D100 ● ok"] == "green"
    assert spans["HR ○ missing"] == "red"
    assert spans["Click ○ reconnecting"] == "yellow"


def test_header_states() -> None:
    assert "Waiting for you to start pedaling" in text(render(snap(started=False), 80))
    assert "Workout done" in text(render(snap(finished=True, segment_index=None), 80))


def test_narrow_terminal_truncates() -> None:
    for line in render(snap(), 30):
        assert sum(len(t) for t, _ in line) <= 30
