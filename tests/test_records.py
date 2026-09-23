"""The interchange file itself: what a line says and what it leaves out."""

import json

from processor.records import (
    SCHEMA,
    ChannelHeader,
    Mark,
    output_path,
    write_ndjson,
)


def _lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_a_point_event_writes_no_duration():
    """Absence is the signal: a written 0 and a point event must not differ."""
    assert "duration_us" not in Mark(time_us=5).as_record()


def test_a_span_writes_its_duration():
    assert Mark(time_us=5, duration_us=90).as_record()["duration_us"] == 90


def test_a_whole_recording_mark_writes_no_channels():
    """An omitted list means the recording; an empty one would be ambiguous."""
    assert "channels" not in Mark(time_us=5).as_record()


def test_a_scoped_mark_lists_its_channels():
    record = Mark(time_us=5, channels=("LH3", "RH2")).as_record()
    assert record["channels"] == ["LH3", "RH2"]


def test_the_record_omits_every_field_the_mark_does_not_have():
    assert Mark(time_us=5).as_record() == {"time_us": 5}


def test_a_value_of_zero_is_still_written():
    """Only None means absent; a detector score of 0.0 is a real measurement."""
    assert Mark(time_us=5, value=0.0).as_record()["value"] == 0.0


def test_only_the_header_carries_the_schema(tmp_path):
    """What lets a reader spot a truncated or concatenated file."""
    path = tmp_path / "out.ndjson"
    write_ndjson(path, ChannelHeader(id="a", name="A"), [Mark(time_us=1)])
    header, record = _lines(path)
    assert header["schema"] == SCHEMA
    assert "schema" not in record


def test_marks_are_written_in_time_order(tmp_path):
    """The bundle's events array must be non-decreasing; sort once, here."""
    path = tmp_path / "out.ndjson"
    write_ndjson(
        path,
        ChannelHeader(id="a", name="A"),
        [Mark(time_us=30), Mark(time_us=10), Mark(time_us=20)],
    )
    assert [line["time_us"] for line in _lines(path)[1:]] == [10, 20, 30]


def test_write_returns_the_count(tmp_path):
    path = tmp_path / "out.ndjson"
    written = write_ndjson(
        path, ChannelHeader(id="a", name="A"), [Mark(time_us=1), Mark(time_us=2)]
    )
    assert written == 2


def test_an_empty_source_still_writes_its_header(tmp_path):
    path = tmp_path / "out.ndjson"
    assert write_ndjson(path, ChannelHeader(id="a", name="A"), []) == 0
    assert len(_lines(path)) == 1


def test_the_header_omits_optional_channel_fields():
    record = ChannelHeader(id="a", name="A").as_record()
    assert record["channel"] == {
        "id": "a",
        "name": "A",
        "time_reference": "recording_onset",
    }


def test_the_header_declares_a_unit_when_there_is_one():
    header = ChannelHeader(id="a", name="A", unit="uV")
    assert header.as_record()["channel"]["unit"] == "uV"


def test_the_filename_stem_is_the_channel_id(tmp_path):
    """The workflow merge keys on filename, so the stem has to be the id."""
    path = output_path(tmp_path, "hup247-ictal")
    assert path.name == "hup247-ictal.annotations.ndjson"


def test_bodies_survive_a_round_trip(tmp_path):
    path = tmp_path / "out.ndjson"
    write_ndjson(
        path,
        ChannelHeader(id="a", name="A", body_media_type="application/json"),
        [Mark(time_us=1, body={"band": "80-250", "score": 7.2})],
    )
    assert _lines(path)[1]["body"] == {"band": "80-250", "score": 7.2}


def test_non_ascii_text_survives(tmp_path):
    """The database is latin1 and this file is UTF-8; the boundary is here."""
    path = tmp_path / "out.ndjson"
    write_ndjson(
        path,
        ChannelHeader(id="a", name="A"),
        [Mark(time_us=1, text="30° rotation, Müller")],
    )
    assert _lines(path)[1]["text"] == "30° rotation, Müller"
