import pytest

from trainer.zwo import Segment, parse_zwo_string

ZWO = """<workout_file>
    <author>me</author>
    <name>Test Workout</name>
    <sportType>bike</sportType>
    <workout>
        <Warmup Duration="600" PowerLow="0.25" PowerHigh="0.75"/>
        <SteadyState Duration="300.0" Power="0.9">
            <textevent timeoffset="10" message="go"/>
        </SteadyState>
        <IntervalsT Repeat="2" OnDuration="30" OffDuration="60" OnPower="1.2" OffPower="0.5"/>
        <Ramp Duration="120" PowerLow="0.6" PowerHigh="0.8"/>
        <FreeRide Duration="60"/>
        <MaxEffort Duration="20"/>
        <UnknownThing Duration="99"/>
        <Cooldown Duration="300" PowerLow="0.3" PowerHigh="0.7"/>
    </workout>
</workout_file>"""


def test_name_and_segment_count() -> None:
    w = parse_zwo_string(ZWO)
    assert w.name == "Test Workout"
    assert len(w.segments) == 10


def test_warmup_ramps_as_written() -> None:
    assert parse_zwo_string(ZWO).segments[0] == Segment("Warmup", 600, 0.25, 0.75)


def test_steady_state_float_duration() -> None:
    assert parse_zwo_string(ZWO).segments[1] == Segment("SteadyState", 300, 0.9, 0.9)


def test_intervals_expanded() -> None:
    s = parse_zwo_string(ZWO).segments[2:6]
    assert s == [
        Segment("IntervalsT on", 30, 1.2, 1.2),
        Segment("IntervalsT off", 60, 0.5, 0.5),
        Segment("IntervalsT on", 30, 1.2, 1.2),
        Segment("IntervalsT off", 60, 0.5, 0.5),
    ]


def test_ramp_and_free_ride() -> None:
    s = parse_zwo_string(ZWO).segments
    assert s[6] == Segment("Ramp", 120, 0.6, 0.8)
    assert s[7] == Segment("FreeRide", 60, None, None)
    assert s[8] == Segment("MaxEffort", 20, None, None)


def test_cooldown_always_descends() -> None:
    assert parse_zwo_string(ZWO).segments[9] == Segment("Cooldown", 300, 0.7, 0.3)


def test_total_duration() -> None:
    assert parse_zwo_string(ZWO).total_duration == 600 + 300 + 180 + 120 + 60 + 20 + 300


def test_no_workout_element_raises() -> None:
    with pytest.raises(ValueError):
        parse_zwo_string("<workout_file><name>x</name></workout_file>")
