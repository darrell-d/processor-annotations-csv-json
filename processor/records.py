"""The interchange record, and how it reaches disk.

One annotation source becomes one NDJSON file and one event channel in the
bundle. The shape is specified in ANNOTATIONS_NDJSON.md; this module is the only
place that knows how to write it, so a site reader only has to produce Marks.
"""

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = "pennsieve/annotations-1.1"

RECORDING_ONSET = "recording_onset"
UNIX_EPOCH = "unix_epoch"

TEXT_MEDIA_TYPE = "text/plain"
JSON_MEDIA_TYPE = "application/json"

FILE_SUFFIX = ".annotations.ndjson"
"""What the writer globs for. Distinctive enough not to catch asset-properties."""


@dataclass(frozen=True, slots=True)
class Mark:
    """One annotation, with every channel it applies to.

    channels is every channel the source named. Empty means the mark belongs to
    the recording rather than to particular electrodes, and the field is left
    out of the record entirely rather than written as a empty list.
    """

    time_us: int
    duration_us: int = 0
    label: str | None = None
    text: str | None = None
    body: dict[str, Any] | None = None
    value: float | None = None
    channels: tuple[str, ...] = ()
    source_id: str | None = None

    def as_record(self) -> dict[str, Any]:
        """Return the NDJSON record, omitting everything the mark does not have.

        Absence is meaningful here: no duration is a point event, and no
        channels is the whole recording. Writing zeros and empty lists instead
        would make those two cases indistinguishable from a real value.
        """
        record: dict[str, Any] = {"time_us": self.time_us}
        if self.duration_us:
            record["duration_us"] = self.duration_us
        if self.label is not None:
            record["label"] = self.label
        if self.text is not None:
            record["text"] = self.text
        if self.body is not None:
            record["body"] = self.body
        if self.value is not None:
            record["value"] = self.value
        if self.channels:
            record["channels"] = list(self.channels)
        return record


@dataclass(frozen=True, slots=True)
class ChannelHeader:
    """The first line of a file: what this annotation source is.

    id is also the filename stem, and must be unique across a workflow run. The
    orchestrator merges every branch's output into one flat directory and fails
    the run on a filename collision, so two sites both emitting
    "clinical-marks" is a dead run rather than a silent overwrite.
    """

    id: str
    name: str
    time_reference: str = RECORDING_ONSET
    body_media_type: str | None = None
    unit: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    def as_record(self) -> dict[str, Any]:
        """Return the header line.

        It is the only line carrying "schema", which is what lets a reader tell
        a truncated or concatenated file from a valid one rather than reading
        the header as data.
        """
        channel: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "time_reference": self.time_reference,
        }
        if self.body_media_type is not None:
            channel["body_media_type"] = self.body_media_type
        if self.unit is not None:
            channel["unit"] = self.unit
        header: dict[str, Any] = {"schema": SCHEMA, "channel": channel}
        if self.provenance:
            header["provenance"] = self.provenance
        return header


def slug(text: str) -> str:
    """Return a filename-safe, lower-case form of a label.

    Layer names are free text a clinician typed, so they arrive with spaces,
    colons and the occasional asterisk. This is what turns one into a channel
    id, and therefore into a filename.
    """
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.strip().lower())
    return cleaned.strip("-") or "annotations"


def utc_now() -> str:
    """Return the current time as an ISO-8601 string, for provenance."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_ndjson(
    path: Path, header: ChannelHeader, marks: Iterable[Mark]
) -> int:
    """Write one annotation source as NDJSON and return how many marks landed.

    Marks are sorted by time on the way out because the bundle's events array
    must be non-decreasing, and sorting here means the writer never has to.
    """
    ordered: Sequence[Mark] = sorted(marks, key=lambda mark: mark.time_us)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps(header.as_record()) + "\n")
        for mark in ordered:
            stream.write(json.dumps(mark.as_record()) + "\n")
    return len(ordered)


def output_path(directory: Path, channel_id: str) -> Path:
    """Return where one source's file belongs: the stem is the channel id."""
    return directory / f"{channel_id}{FILE_SUFFIX}"
