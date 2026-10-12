"""Parse Zwift .zwo workout files into a flat list of segments."""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Segment:
    kind: str
    duration: int  # seconds
    power_start: float | None  # FTP fraction at segment start; None = free ride
    power_end: float | None  # FTP fraction at segment end


@dataclass(frozen=True)
class Workout:
    name: str
    segments: list[Segment]

    @property
    def total_duration(self) -> int:
        return sum(s.duration for s in self.segments)


def _num(el: ET.Element, *names: str) -> float:
    for name in names:
        if name in el.attrib:
            return float(el.attrib[name])
    raise ValueError(f"<{el.tag}> is missing {names[0]}")


def _segments(el: ET.Element) -> list[Segment]:
    tag = el.tag
    if tag in ("Warmup", "Ramp"):
        lo, hi = _num(el, "PowerLow"), _num(el, "PowerHigh")
        return [Segment(tag, int(_num(el, "Duration")), lo, hi)]
    if tag == "Cooldown":
        lo, hi = _num(el, "PowerLow"), _num(el, "PowerHigh")
        return [Segment(tag, int(_num(el, "Duration")), max(lo, hi), min(lo, hi))]
    if tag == "SteadyState":
        p = _num(el, "Power", "PowerLow")
        return [Segment(tag, int(_num(el, "Duration")), p, p)]
    if tag == "IntervalsT":
        on, off = _num(el, "OnPower", "PowerOnHigh"), _num(el, "OffPower", "PowerOffHigh")
        on_d, off_d = int(_num(el, "OnDuration")), int(_num(el, "OffDuration"))
        pair = [Segment("IntervalsT on", on_d, on, on), Segment("IntervalsT off", off_d, off, off)]
        return pair * int(_num(el, "Repeat"))
    if tag in ("FreeRide", "MaxEffort"):
        return [Segment(tag, int(_num(el, "Duration")), None, None)]
    return []


def parse_zwo_string(text: str) -> Workout:
    root = ET.fromstring(text)
    workout = root.find("workout")
    if workout is None:
        raise ValueError("No <workout> element in ZWO file")
    name = (root.findtext("name") or "Workout").strip()
    return Workout(name, [s for el in workout for s in _segments(el)])


def parse_zwo(path: str | Path) -> Workout:
    return parse_zwo_string(Path(path).read_text())
