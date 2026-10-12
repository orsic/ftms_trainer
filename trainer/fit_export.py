"""Convert a ride CSV into a FIT activity for Strava / Garmin Connect."""

from itertools import groupby
from pathlib import Path

from fit_tool.base_type import BaseType
from fit_tool.developer_field import DeveloperField
from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.activity_message import ActivityMessage
from fit_tool.profile.messages.developer_data_id_message import DeveloperDataIdMessage
from fit_tool.profile.messages.event_message import EventMessage
from fit_tool.profile.messages.field_description_message import FieldDescriptionMessage
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.lap_message import LapMessage
from fit_tool.profile.messages.record_message import RecordMessage
from fit_tool.profile.messages.session_message import SessionMessage
from fit_tool.profile.profile_type import Event, EventType, FileType, Manufacturer, Sport, SubSport

from trainer.recorder import Row, read_rows

# (csv column, FIT developer field name, base type, byte size, units)
DEV_FIELDS = [
    ("pm_power", "pm_power", BaseType.UINT16, 2, "W"),
    ("pm_cadence", "pm_cadence", BaseType.UINT8, 1, "rpm"),
    ("pm_balance_left", "pm_balance_left", BaseType.UINT8, 1, "%"),
    ("target_power", "target_power", BaseType.UINT16, 2, "W"),
]


def _ms(seconds: float) -> int:
    return round(seconds) * 1000


def _stats(rows: list[Row], key: str) -> tuple[int | None, int | None]:
    values = [r[key] for r in rows if r.get(key) is not None]
    if not values:
        return None, None
    return round(sum(values) / len(values)), round(max(values))


def _fill_totals(
    msg: LapMessage | SessionMessage, rows: list[Row], start: float, end: float, distance: float
) -> None:
    msg.start_time = _ms(start)
    msg.timestamp = _ms(end)
    msg.total_elapsed_time = end - start
    msg.total_timer_time = end - start
    msg.total_distance = distance
    msg.avg_power, msg.max_power = _stats(rows, "trainer_power")
    msg.avg_heart_rate, msg.max_heart_rate = _stats(rows, "heart_rate")
    msg.avg_cadence, msg.max_cadence = _stats(rows, "cadence")


def _dedupe_seconds(rows: list[Row]) -> list[Row]:
    out, last = [], None
    for r in rows:
        second = round(r["timestamp"])
        if second != last:
            out.append(r)
            last = second
    return out


def export_fit(csv_path: str | Path, fit_path: str | Path) -> None:
    rows = _dedupe_seconds(read_rows(csv_path))
    if not rows:
        raise ValueError(f"{csv_path} has no samples")
    start, end = rows[0]["timestamp"], rows[-1]["timestamp"] + 1

    b = FitFileBuilder(auto_define=True, min_string_size=50)
    file_id = FileIdMessage()
    file_id.type = FileType.ACTIVITY
    file_id.manufacturer = Manufacturer.DEVELOPMENT.value
    file_id.product = 0
    file_id.serial_number = 1
    file_id.time_created = _ms(start)
    b.add(file_id)

    dev_id = DeveloperDataIdMessage()
    dev_id.developer_data_index = 0
    dev_id.application_id = bytes(16)
    b.add(dev_id)
    for num, (_, name, base_type, _, units) in enumerate(DEV_FIELDS):
        desc = FieldDescriptionMessage()
        desc.developer_data_index = 0
        desc.field_definition_number = num
        desc.fit_base_type_id = base_type.value
        desc.field_name = name
        desc.units = units
        b.add(desc)

    event = EventMessage()
    event.event = Event.TIMER
    event.event_type = EventType.START
    event.timestamp = _ms(start)
    b.add(event)

    distance, prev_ts = 0.0, start
    for r in rows:
        if r.get("speed") is not None:
            distance += r["speed"] / 3.6 * (r["timestamp"] - prev_ts)
        prev_ts = r["timestamp"]
        r["distance"] = distance
        r["cadence"] = (
            r.get("trainer_cadence") if r.get("trainer_cadence") is not None else r.get("pm_cadence")
        )

        rec = RecordMessage()
        rec.timestamp = _ms(r["timestamp"])
        rec.distance = distance
        if r.get("trainer_power") is not None:
            rec.power = round(r["trainer_power"])
        if r.get("heart_rate") is not None:
            rec.heart_rate = round(r["heart_rate"])
        if r["cadence"] is not None:
            rec.cadence = round(r["cadence"])
        if r.get("speed") is not None:
            rec.speed = r["speed"] / 3.6
        dev = []
        for num, (column, name, base_type, size, units) in enumerate(DEV_FIELDS):
            if r.get(column) is not None:
                field = DeveloperField(
                    field_id=num,
                    name=name,
                    base_type=base_type,
                    size=size,
                    units=units,
                    developer_data_index=0,
                )
                field.set_value(0, round(r[column]))
                dev.append(field)
        rec.developer_fields = dev
        b.add(rec)

    event = EventMessage()
    event.event = Event.TIMER
    event.event_type = EventType.STOP_ALL
    event.timestamp = _ms(end)
    b.add(event)

    laps = [list(g) for _, g in groupby(rows, key=lambda r: r.get("segment"))]
    for i, lap_rows in enumerate(laps):
        lap = LapMessage()
        lap.message_index = i
        lap.event = Event.LAP
        lap.event_type = EventType.STOP
        lap_end = laps[i + 1][0]["timestamp"] if i + 1 < len(laps) else end
        lap_start_distance = laps[i - 1][-1]["distance"] if i else 0.0
        _fill_totals(
            lap, lap_rows, lap_rows[0]["timestamp"], lap_end, lap_rows[-1]["distance"] - lap_start_distance
        )
        lap.sport = Sport.CYCLING
        lap.sub_sport = SubSport.INDOOR_CYCLING
        b.add(lap)

    session = SessionMessage()
    session.message_index = 0
    session.event = Event.SESSION
    session.event_type = EventType.STOP
    _fill_totals(session, rows, start, end, distance)
    session.sport = Sport.CYCLING
    session.sub_sport = SubSport.INDOOR_CYCLING
    session.first_lap_index = 0
    session.num_laps = len(laps)
    if rows[-1].get("ftp") is not None:
        session.threshold_power = round(rows[-1]["ftp"])
    b.add(session)

    activity = ActivityMessage()
    activity.timestamp = _ms(end)
    activity.total_timer_time = end - start
    activity.num_sessions = 1
    activity.event = Event.ACTIVITY
    activity.event_type = EventType.STOP
    b.add(activity)

    b.build().to_file(str(fit_path))
