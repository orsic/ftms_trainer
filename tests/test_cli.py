import sys

from trainer.__main__ import _slug, main, print_summary
from trainer.recorder import Recorder, read_rows


def test_slug() -> None:
    assert _slug("Sweet Spot 3x10 (hard)") == "sweet-spot-3x10-hard"


def test_export_command_and_summary(tmp_path, monkeypatch, capsys) -> None:
    csv_path = tmp_path / "r.csv"
    with Recorder(csv_path) as rec:
        for i in range(40):
            rec.write(
                {
                    "timestamp": 1760000000.0 + i,
                    "elapsed": i,
                    "segment": 0,
                    "trainer_power": 200,
                    "heart_rate": 150,
                }
            )
    monkeypatch.setattr(sys, "argv", ["trainer", "export", str(csv_path)])
    main()
    assert (tmp_path / "r.fit").stat().st_size > 0

    print_summary(read_rows(csv_path), csv_path, tmp_path / "r.fit")
    out = capsys.readouterr().out
    assert "D100           avg 200 W   NP 200 W" in out
    assert "4iiii          --" in out
    assert "avg 150 bpm" in out
