# Annotation interchange format (NDJSON)

**Status: draft.** This is the deliverable for ClickUp
[A1 — Define the annotation JSON interchange schema](https://app.clickup.com/t/868m610gd).
Nothing is built against it yet, so it is still cheap to change.

## What this is

Every annotation source — baked into an EDF, an XML or CSV sidecar, a detector run,
a database — is normalised by its own extractor into this one format. The TS-Zarr
bundle writer takes **NWB plus these files** and turns each one into an event channel.

Annotations deliberately do *not* travel inside NWB. Annotations that come from a
database have no NWB home at all, so an NWB-only path would have needed a second
path anyway. This is that one path. It also keeps signal conversion and annotation
extraction independent — they fail for different reasons, and you want to re-run one
without the other.

This file is an **input to the writer, not part of the bundle**. The TS-Zarr spec
argues against sidecars, but that argument is about objects *inside* a bundle that a
Zarr library cannot open. No conflict.

Format spec for the bundle itself: `Pennsieve/timeseries-zarr-paper`, `bundle-format.md`.

## File and naming

```
<channel.id>.annotations.ndjson
```

One file per annotation source → one event channel in the bundle.

**The stem must equal `channel.id`, and `channel.id` must be unique across the
workflow.** This is not cosmetic. When a workflow branch merges, the orchestrator runs
`data-transfer` with `action: "merge"`, which symlinks every dependency's output into
one flat directory and **fails the whole run on any filename collision**
(`compute-node-aws-provisioner-v2/cmd/data-transfer/main.go`, `handleMerge`). Two
extractors both emitting `annotations.json` is a dead run.

The distinctive `.annotations.ndjson` suffix also keeps the writer's discovery glob
from picking up the `asset-properties.json` that already lives in that tree.

## Why NDJSON rather than JSON

NDJSON (newline-delimited JSON, also called JSON Lines) is one JSON object per line —
no enclosing array, no commas. A reader handles one line at a time and forgets it, so
memory is constant regardless of file size.

A plain JSON document must be fully parsed before any of it is usable. Five million
detector events as one document is several GB that has to be materialised at once.

There is also a symmetry worth having: the bundle's own `bodies` array **is** NDJSON —
the spec mandates newline-terminated payloads so the chunk object is directly readable.
Same convention on both sides of the writer.

Small files use NDJSON too. One format means the writer has one code path.

## Structure

Line 1 is the header. Every line after it is one annotation.

```
{"schema": …, "channel": {…}, "provenance": {…}}     <- header
{"time_us": …, …}                                     <- annotation
{"time_us": …, …}                                     <- annotation
```

The header is identified by carrying `schema`; records never do. That makes a
malformed file detectable rather than silently misread as data.

## Header fields

| Field | Required | Notes |
|---|---|---|
| `schema` | yes | e.g. `"pennsieve/annotations-1.1"`. The writer rejects versions it does not know, by name. |
| `channel.id` | yes | Opaque identifier → channel attr `id`. **Must be pseudonymous** — no patient names, no dates. Identity belongs only in the bundle's `meta/`. |
| `channel.name` | yes | Display label → channel attr `name`. What the viewer draws. |
| `channel.time_reference` | yes | `"recording_onset"` or `"unix_epoch"`. See Time. |
| `channel.body_media_type` | no | `"text/plain"` (default) or `"application/json"`. |
| `channel.unit` | no | Physical unit of `value`, e.g. `"uV"`. |
| `provenance` | no | Free-form. What produced this file: extractor, version, source file, params. |

## Record fields

| Field | Required | Type | Notes |
|---|---|---|---|
| `time_us` | yes | integer | Microseconds. **Never seconds, never a float.** |
| `duration_us` | no | integer | Microseconds. Omit or `0` means a point event. |
| `label` | no | string | Free text. The writer interns these into integers. |
| `text` | no | string | Plain-text body. Use when `body_media_type` is `text/plain`. |
| `body` | no | object | Structured body. Use when `body_media_type` is `application/json`. |
| `value` | no | number | A measurement or detector score. |
| `channels` | no | array of strings | Channel **names**. **Omit entirely to mean the whole recording.** |

## Time

```
time_us         integer microseconds, always
time_reference  "recording_onset" | "unix_epoch"
```

**The extractor declares the frame; the writer converts it.** This is forced by the
workflow shape, not a preference: the annotation extractor runs in a branch *parallel*
to the NWB conversion, so it cannot read the NWB and cannot know the onset the writer
will compute. It can only say which clock its numbers are on.

- `recording_onset` — microseconds from the start of the recording. EDF+ TAL's natural
  frame; the extractor only has to scale seconds to microseconds.
- `unix_epoch` — microseconds since 1970. For databases and absolute-timestamped
  sources. The writer subtracts the NWB's `session_start_time`, which is the same value
  it writes to the bundle's `meta/session.start_us`.

Integer microseconds throughout. EEG samples are 0.5–4 ms apart, so seconds would
collapse annotations onto the same instant, and a float-seconds round trip loses the
precision silently. **A timebase mistake produces no error — only annotations at the
wrong time, which nobody eyeballs at 2 kHz.** It is the highest-risk field in this
format.

## Examples

Clinical marks, plain text, with channel scoping:

```
{"schema":"pennsieve/annotations-1.1","channel":{"id":"clinical-marks","name":"Clinical marks","time_reference":"recording_onset","body_media_type":"text/plain"},"provenance":{"extractor":"edf-annotations-ndjson","version":"1.1.0","source_file":"sub-01_ses-01_eeg.edf","extracted_at":"2026-09-16T14:22:01Z"}}
{"time_us":100,"label":"Spike","channels":["LH3"],"text":"Interictal discharge."}
{"time_us":250,"label":"Spike","channels":["LH3","RH2"],"text":"Bilateral."}
{"time_us":400,"duration_us":60000,"label":"Note","text":"Patient off medication."}
{"time_us":600,"duration_us":90000,"label":"Seizure","channels":["LA6","RAC1","LH3","RH2","Fz"],"text":"Onset right temporal."}
{"time_us":900,"label":"Spike","channels":["LOF4"],"text":"Isolated."}
```

A detector, JSON bodies and per-event values:

```
{"schema":"pennsieve/annotations-1.1","channel":{"id":"hfo-detector-run3","name":"HFO candidates","time_reference":"recording_onset","body_media_type":"application/json","unit":"uV"},"provenance":{"extractor":"hfo-detect","version":"2.1.0","params":{"threshold":4.5,"window_ms":200}}}
{"time_us":412000,"duration_us":850,"label":"ripple","channels":["LH3"],"value":7.2,"body":{"band":"80-250","score":7.2}}
{"time_us":918300,"duration_us":1100,"label":"fast-ripple","channels":["LA6"],"value":4.9,"body":{"band":"250-500","score":4.9}}
```

Two files in one workflow produce two event channels. Different `channel.id`, so no
merge collision.

## What the writer derives — do not put these in the file

| Derived | From |
|---|---|
| Sort order | Sorts by `time_us`. `events` must be non-decreasing; extractors emit in file order. |
| `offset_us` = 0 | Times are onset-relative by then. |
| `max_duration_us` | The largest `duration_us` seen. Must be a true upper bound or the reader's stabbing query under-returns, so it is computed, never accepted. |
| `label_names` + integer `labels` | Interns the distinct `label` strings, sorted, so indices — and therefore colours — are stable across re-runs. |
| `bodies` + `body_offsets` | Packs `text`/`body`, newline-terminated, as a single uncompressed chunk. |
| `channel_refs` + `channel_ref_offsets` | Resolves `channels` names to channel folder numbers and packs them. |
| Count pyramid levels | Decided from the event count (reference threshold ~64k). |

This table is the reason extractors stay simple: none of it requires knowing anything
about Zarr. An extractor reads its source format and writes lines.

## The `channels` field and the open spec question

**TS-Zarr has no per-event channel reference today.** An event channel's members are
`events`, `durations`, `labels`, `values`, `bodies`/`body_offsets`, `waveforms`,
`templates`, `labels.<set>`. None of them says which electrodes a mark applies to.

The proposal to Rohan is two new channel-level arrays, mirroring `bodies`/`body_offsets`:

```
channel_refs/          u2, all referenced channel indices packed end to end,
                       in event order
channel_ref_offsets/   (n+1,) u8, running total. Event i's channels are
                       channel_refs[offsets[i] : offsets[i+1]].
                       An empty span means the whole recording.
```

The spec's own Compatibility section permits this: *"new level members and new
channel-level named arrays are discovered through consolidated-metadata enumeration
and ignored when unrecognized… Nothing may change the node type or shape contract of an
existing path."* This adds two paths and alters none. `labels.<set>` is the existing
precedent for adding per-event arrays alongside `events`.

One caveat worth putting in the spec if it lands: channel references are **indices into
this bundle's channel set** and are invalidated by any renumbering.

**Until then, the writer folds `channels` into a JSON body** and sets
`body_media_type: "application/json"`. Nothing is lost; it is just not queryable
without opening every body.

**The NDJSON is identical either way.** That is the whole reason to include `channels`
now — whether it lands in a column or a body is a writer decision made in one place,
while the extractors get written once and never revisited.

## Open questions

- Where does this file ultimately live? It is the contract between several extractors
  and one writer, so a shared home (its own repo, or `timeseries-zarr-py`) may beat
  sitting inside one extractor.
- A JSON Schema alongside this prose, so extractors can validate their own output.
- Volume: NDJSON streams, but the writer still sorts in memory. Fine for millions of
  int64 timestamps; worth measuring before the first large detector run.
- `provenance` has no home in the bundle's channel attribute table. Write it as an
  additive attribute and tell Rohan, or drop it for v1.
