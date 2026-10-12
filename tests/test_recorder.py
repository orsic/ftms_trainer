import pytest

from trainer.recorder import FIELDS, Recorder, normalized_power, read_rows, summarize


def test_write_and_read_back_with_gaps(tmp_path) -> None:
    path = tmp_path / "ride.csv"
    with Recorder(path) as rec:
        rec.write({"timestamp": 1000.0, "elapsed": 0, "trainer_power": 200, "heart_rate": None})
        rec.write({"timestamp": 1001.0, "elapsed": 1, "trainer_power": 210, "pm_power": 205})
    assert path.read_text().splitlines()[0] == ",".join(FIELDS)
    rows = read_rows(path)
    assert rows[0]["trainer_power"] == 200 and rows[0]["heart_rate"] is None
    assert rows[1]["pm_power"] == 205 and rows[0]["pm_power"] is None


def test_normalized_power_constant_equals_average() -> None:
    assert normalized_power([200.0] * 60) == pytest.approx(200.0)


def test_normalized_power_ignores_gaps_and_short_rides() -> None:
    assert normalized_power([None] * 60) is None
    assert normalized_power([100.0] * 10) is None
    assert normalized_power([200.0, None] * 40) == pytest.approx(200.0)


def test_summarize() -> None:
    rows = [
        {"elapsed": float(i), "trainer_power": 200.0, "pm_power": 190.0, "heart_rate": None}
        for i in range(60)
    ]
    s = summarize(rows)
    assert s["duration"] == 59
    assert s["trainer_power"] == (pytest.approx(200.0), pytest.approx(200.0))
    assert s["pm_power"] == (pytest.approx(190.0), pytest.approx(190.0))
    assert s["heart_rate"] is None
