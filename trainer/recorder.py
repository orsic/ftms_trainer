"""Crash-safe 1 Hz CSV log of every sample, plus ride summary statistics."""

import csv
from pathlib import Path
from typing import Self

FIELDS = [
    "timestamp",
    "elapsed",
    "segment",
    "ftp",
    "target_power",
    "trainer_power",
    "trainer_cadence",
    "speed",
    "pm_power",
    "pm_cadence",
    "pm_balance_left",
    "heart_rate",
]

Row = dict[str, float | None]


class Recorder:
    def __init__(self, path: str | Path) -> None:
        self._file = open(path, "w", newline="")
        self._writer = csv.DictWriter(self._file, FIELDS)
        self._writer.writeheader()
        self._file.flush()

    def write(self, row: Row) -> None:
        self._writer.writerow({k: "" if row.get(k) is None else row[k] for k in FIELDS})
        self._file.flush()

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def read_rows(path: str | Path) -> list[Row]:
    with open(path, newline="") as f:
        return [{k: float(v) if v else None for k, v in row.items()} for row in csv.DictReader(f)]


def normalized_power(values: list[float | None]) -> float | None:
    """30 s rolling average, 4th power mean, 4th root. Gaps are skipped."""
    present = [v for v in values if v is not None]
    if len(present) < 30:
        return None
    rolling = [sum(present[i - 30 : i]) / 30 for i in range(30, len(present) + 1)]
    return (sum(r**4 for r in rolling) / len(rolling)) ** 0.25


def _avg(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if present else None


def summarize(rows: list[Row]) -> dict:
    summary: dict = {"duration": int(rows[-1]["elapsed"] or 0) if rows else 0}
    for key in ("trainer_power", "pm_power"):
        values = [r.get(key) for r in rows]
        avg = _avg(values)
        summary[key] = None if avg is None else (avg, normalized_power(values))
    summary["heart_rate"] = _avg([r.get("heart_rate") for r in rows])
    return summary
