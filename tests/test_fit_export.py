import fitdecode

from trainer.fit_export import export_fit
from trainer.recorder import Recorder

T0 = 1760000000.0


def write_csv(path) -> None:
    with Recorder(path) as rec:
        for i in range(10):
            rec.write(
                {
                    "timestamp": T0 + i,
                    "elapsed": i,
                    "segment": 0 if i < 6 else 1,
                    "ftp": 250,
                    "target_power": 200,
                    "trainer_power": 200 + i,
                    "trainer_cadence": 90,
                    "speed": 36.0,
                    "pm_power": 195 + i if i != 3 else None,
                    "pm_cadence": 91,
                    "pm_balance_left": 49.5,
                    "heart_rate": 140 if i >= 5 else None,
                }
            )


def decode(path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    with fitdecode.FitReader(str(path)) as fr:
        for m in fr:
            if isinstance(m, fitdecode.FitDataMessage):
                out.setdefault(m.name, []).append({f.name: f.value for f in m.fields})
    return out


def test_fit_contents(tmp_path) -> None:
    csv_path, fit_path = tmp_path / "r.csv", tmp_path / "r.fit"
    write_csv(csv_path)
    export_fit(csv_path, fit_path)
    msgs = decode(fit_path)

    assert msgs["file_id"][0]["type"] == "activity"
    records = msgs["record"]
    assert len(records) == 10
    assert [r["power"] for r in records] == [200 + i for i in range(10)]
    assert records[0]["pm_power"] == 195
    assert "pm_power" not in records[3]
    assert "heart_rate" not in records[0] and records[5]["heart_rate"] == 140
    assert records[0]["cadence"] == 90
    assert records[0]["target_power"] == 200
    assert records[9]["distance"] == 90.0  # 10 m/s for 9 s

    laps = msgs["lap"]
    assert len(laps) == 2
    assert laps[0]["total_timer_time"] == 6.0
    assert laps[0]["total_distance"] + laps[1]["total_distance"] == session_distance(msgs)
    session = msgs["session"][0]
    assert (session["sport"], session["sub_sport"]) == ("cycling", "indoor_cycling")
    assert session["num_laps"] == 2
    assert session["avg_power"] == round(sum(200 + i for i in range(10)) / 10)
    assert msgs["activity"][0]["num_sessions"] == 1


def test_duplicate_seconds_dropped(tmp_path) -> None:
    csv_path, fit_path = tmp_path / "r.csv", tmp_path / "r.fit"
    with Recorder(csv_path) as rec:
        for ts in (T0, T0 + 0.4, T0 + 1.0):
            rec.write({"timestamp": ts, "elapsed": ts - T0, "segment": 0, "trainer_power": 100})
    export_fit(csv_path, fit_path)
    assert len(decode(fit_path)["record"]) == 2


def session_distance(msgs: dict[str, list[dict]]) -> float:
    return msgs["session"][0]["total_distance"]
