"""The two things this site reader exists for: squashing and deduping."""

import json

import pytest

from processor.records import Mark, slug
from processor.sites.ieeg import (
    EXACT,
    FIRST,
    LAST,
    WIDEST,
    Row,
    convert,
    dedupe,
    read_rows,
    squash,
    to_bodies,
)

HEADER = (
    "annotation_id,layer,type,description,annotator,created_at,"
    "time_us,duration_us,channel"
)


def _row(annotation_id="1", channel="C3", **overrides):
    fields = {
        "annotation_id": annotation_id,
        "layer": "Imported Natus ENT annotations",
        "type": "Seizure",
        "description": "Seizure",
        "annotator": "Review",
        "created_at": "2022-11-09 02:12:31",
        "time_us": 1000,
        "duration_us": 0,
        "channel": channel,
    }
    fields.update(overrides)
    return Row(**fields)


def _csv(tmp_path, lines, name="export.csv"):
    path = tmp_path / name
    path.write_text("\n".join([HEADER, *lines]) + "\n")
    return path


def test_squash_turns_the_per_channel_fanout_into_one_mark():
    rows = [_row(channel=name) for name in ("RP03", "C3", "RP01")]
    marks = squash(rows)
    assert len(marks) == 1
    assert marks[0].channels == ("C3", "RP01", "RP03")


def test_squash_sorts_channels_so_copies_compare_equal():
    one = squash([_row(channel="B"), _row(channel="A")])[0]
    two = squash([_row(channel="A"), _row(channel="B")])[0]
    assert one.channels == two.channels


def test_squash_keeps_separate_annotations_separate():
    rows = [_row("1", "C3"), _row("2", "C3", time_us=2000)]
    assert len(squash(rows)) == 2


def test_an_empty_channel_means_the_whole_recording():
    """No channels at all, rather than a list with an empty string in it."""
    assert squash([_row(channel="")])[0].channels == ()


def test_description_is_dropped_when_it_only_repeats_the_type():
    """Natus imports set both; writing both puts one string in two places."""
    assert squash([_row()])[0].text is None


def test_description_is_kept_when_it_says_something_else():
    mark = squash([_row(description="Onset right temporal.")])[0]
    assert mark.text == "Onset right temporal."


def _three_imports(channel_counts=(68, 68, 60)):
    """The measured HUP247 shape: one mark, three imports, one narrower."""
    return [
        Mark(
            time_us=3590954742,
            label="RP1-3 very active",
            channels=tuple(f"CH{i:02}" for i in range(count)),
            source_id=str(source_id),
        )
        for source_id, count in zip(
            (36462407, 36463559, 36464711), channel_counts, strict=True
        )
    ]


def test_dedupe_collapses_copies_that_are_identical():
    """Three identical imports carry no information between them."""
    assert len(dedupe(_three_imports((68, 68, 68)))) == 1


def test_dedupe_keeps_copies_that_differ_rather_than_dropping_channels():
    """The default errs toward a visible duplicate over a silent loss."""
    kept = dedupe(_three_imports((68, 68, 60)))
    assert sorted(len(mark.channels) for mark in kept) == [60, 68]


def test_exact_keeps_one_copy_per_distinct_channel_set():
    kept = dedupe(_three_imports((68, 60, 60)), EXACT)
    assert sorted(len(mark.channels) for mark in kept) == [60, 68]


def test_dedupe_first_keeps_the_oldest_import():
    assert dedupe(_three_imports(), FIRST)[0].source_id == "36462407"


def test_dedupe_last_keeps_the_newest_import():
    assert dedupe(_three_imports(), LAST)[0].source_id == "36464711"


def test_dedupe_widest_keeps_the_copy_that_named_most_channels():
    """The rule changes the data, not just which row survives."""
    kept = dedupe(_three_imports(), WIDEST)[0]
    assert len(kept.channels) == 68


def test_dedupe_warns_when_the_copies_disagree(caplog):
    dedupe(_three_imports(), EXACT)
    assert "disagree on channels" in caplog.text
    assert "keeping all" in caplog.text


def test_a_picking_rule_says_it_is_discarding(caplog):
    dedupe(_three_imports(), FIRST)
    assert "discards the rest" in caplog.text


def test_dedupe_is_quiet_when_the_copies_agree(caplog):
    dedupe(_three_imports((68, 68, 68)), EXACT)
    assert "disagree" not in caplog.text


def test_dedupe_keeps_marks_that_differ_in_time():
    marks = [
        Mark(time_us=1, label="a", source_id="1"),
        Mark(time_us=2, label="a", source_id="2"),
    ]
    assert len(dedupe(marks)) == 2


def test_dedupe_keeps_marks_that_differ_in_text():
    marks = [
        Mark(time_us=1, label="a", text="one", source_id="1"),
        Mark(time_us=1, label="a", text="two", source_id="2"),
    ]
    assert len(dedupe(marks)) == 2


def test_dedupe_rejects_an_unknown_rule():
    with pytest.raises(ValueError, match="unknown duplicate rule"):
        dedupe([], "newest")


def test_read_rows_rejects_a_file_that_is_not_this_export(tmp_path):
    path = tmp_path / "wrong.csv"
    path.write_text("a,b,c\n1,2,3\n")
    with pytest.raises(ValueError, match="missing columns"):
        list(read_rows(path))


def test_read_rows_treats_a_blank_duration_as_a_point(tmp_path):
    path = _csv(tmp_path, ["1,L,T,,Review,2022-11-09 02:12:31,500,,C3"])
    assert list(read_rows(path))[0].duration_us == 0


def test_convert_splits_layers_into_separate_sources(tmp_path):
    path = _csv(
        tmp_path,
        [
            "1,Ictal,Seizure,,Review,2022-11-09 02:12:31,500,90,C3",
            "2,stability,Bookmark,,Review,2022-11-09 02:12:31,900,0,C3",
        ],
    )
    sources = convert(path)
    assert [header.id for header, _ in sources] == ["ictal", "stability"]


def test_convert_carries_the_duration_through(tmp_path):
    path = _csv(
        tmp_path, ["1,Ictal,Seizure,,Review,2022-11-09 02:12:31,500,90000,C3"]
    )
    (_, marks), = convert(path)
    assert marks[0].duration_us == 90000


def test_convert_prefixes_channel_ids_for_workflow_uniqueness(tmp_path):
    """Two sites with a layer called Ictal would otherwise fail the merge."""
    path = _csv(
        tmp_path, ["1,Ictal,Seizure,,Review,2022-11-09 02:12:31,500,0,C3"]
    )
    (header, _), = convert(path, source_prefix="hup247-")
    assert header.id == "hup247-ictal"


def test_the_default_rule_is_exact(tmp_path):
    path = _csv(
        tmp_path, ["1,Ictal,Seizure,,Review,2022-11-09 02:12:31,500,0,C3"]
    )
    (header, _), = convert(path)
    assert header.provenance["duplicate_rule"] == EXACT


def test_convert_records_the_rule_it_used(tmp_path):
    path = _csv(
        tmp_path, ["1,Ictal,Seizure,,Review,2022-11-09 02:12:31,500,0,C3"]
    )
    (header, _), = convert(path, duplicate_rule=WIDEST)
    assert header.provenance["duplicate_rule"] == WIDEST


def test_json_bodies_carry_the_source_id_for_an_audit_trail():
    """A migration wants to trace a bundle mark back to its ts_annotation row."""
    marks = to_bodies([Mark(time_us=1, label="Seizure", source_id="36462407")])
    assert marks[0].body == {
        "description": "Seizure",
        "ts_annotation_id": "36462407",
    }
    assert marks[0].text is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Imported Natus ENT annotations", "imported-natus-ent-annotations"),
        ("*Tech notation: Video/EEG", "tech-notation-video-eeg"),
        ("  stability  ", "stability"),
        ("***", "annotations"),
    ],
)
def test_slug(text, expected):
    assert slug(text) == expected


def test_end_to_end_on_the_measured_natus_shape(tmp_path):
    """400 rows, six annotation rows, two real marks."""
    lines = []
    for source_id, created in (
        ("36462406", "2022-11-09 02:12:31"),
        ("36463558", "2022-11-09 02:12:57"),
        ("36464710", "2022-11-09 03:56:18"),
    ):
        for index in range(68):
            lines.append(
                f"{source_id},Imported Natus ENT annotations,"
                f"*Tech notation,*Tech notation,Acquisition,{created},"
                f"3080610992,0,CH{index:02}"
            )
    path = _csv(tmp_path, lines)
    (header, marks), = convert(path)
    assert len(marks) == 1
    assert len(marks[0].channels) == 68
    assert json.loads(json.dumps(header.as_record()))["schema"].startswith(
        "pennsieve/annotations-"
    )
