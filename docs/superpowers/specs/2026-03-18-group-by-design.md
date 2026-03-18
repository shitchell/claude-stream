# `--group-by` Design Spec

**Date:** 2026-03-18
**Version target:** 0.4.0

## Overview

Add a `--group-by` flag that controls how multi-file results are ordered and grouped when scanning directories or search results. Supports grouping by project directory and/or time buckets at arbitrary resolution via strftime syntax.

## CLI Flag

```
--group-by SPEC
```

Where `SPEC` is a comma-separated list of grouping keys:

- `project` — group by encoded project directory (the parent dir of the JSONL file under `~/.claude/projects/`)
- `time:<strftime>` — group by time bucket at the given resolution (e.g., `time:%Y%m%d%H` for hourly)

Examples:

```bash
claude-stream --after "yesterday" ~/.claude/projects/ --group-by time:%Y%m%d%H
claude-stream --search "error" --group-by project
claude-stream --after "7 days ago" . --group-by project,time:%Y%m%d
```

## Parsing & Validation

The `SPEC` string is split on `,` to produce a list of grouping keys. Each key is validated:

- `project` — valid as-is
- `time:<pattern>` — the `<pattern>` portion must be a non-empty strftime format string. Validated by attempting `datetime.now().strftime(pattern)` — if it raises, the pattern is invalid.
- Anything else → error: `"invalid group-by key: {key}. Expected 'project' or 'time:<strftime>'"`

**Constraints:**
- At most one `time:` key is allowed. Multiple `time:` keys → error: `"only one time: group-by key is allowed"`
- Duplicate `project` keys → silently deduplicated
- Order matters: `project,time:%H` groups by project first, then interleaves by time within each project. `time:%H,project` would interleave by time first, then sub-group by project within each bucket (though this ordering is unusual).

**Parsed representation:**

```python
@dataclass
class GroupByConfig:
    """Parsed --group-by configuration."""
    by_project: bool = False
    time_format: str | None = None  # strftime pattern, or None if no time grouping
    project_first: bool = True  # True if project appears before time in SPEC
```

This is stored on `RenderConfig`:

```python
@dataclass
class RenderConfig:
    # ... existing fields ...
    group_by: GroupByConfig | None = None  # None = no grouping (default behavior)
```

## Behavior

### No `--group-by` (default)

Current behavior: files sorted by mtime (most recent first), each rendered start-to-finish.

### `--group-by project`

Files grouped by their project directory. Within each project, files rendered start-to-finish ordered by mtime. Project headers displayed between groups.

```
────────────────────────────────────────────────────────────
── Project: -home-guy-myproject ──
📄 session-003.jsonl
  ... all messages ...
📄 session-001.jsonl
  ... all messages ...

────────────────────────────────────────────────────────────
── Project: -home-guy-other ──
📄 session-002.jsonl
  ... all messages ...
```

This is a degenerate case of the general algorithm: each file is a single "bucket" rendered in full.

### `--group-by time:<strftime>`

Messages interleaved across files by time bucket. Within each bucket, files ordered by their first message timestamp in that bucket. Each file's messages within a bucket are rendered contiguously before moving to the next file in the same bucket.

Example with `--group-by time:%H` (hourly buckets):

Given:
- File A: messages at 9:01, 9:15, 9:23
- File B: messages at 9:02, 9:30, 10:02, 10:45, 11:10
- File C: messages at 9:03, 9:50, 10:01, 10:30

Output:

```
📄 File A [9:*]
  9:01 message...
  9:15 message...
  9:23 message...
📄 File B [9:*]
  9:02 message...
  9:30 message...
📄 File C [9:*]
  9:03 message...
  9:50 message...
📄 File C [10:*]
  10:01 message...
  10:30 message...
📄 File B [10:*]
  10:02 message...
  10:45 message...
📄 File B [11:*]
  11:10 message...
```

### `--group-by project,time:<strftime>`

First group by project, then interleave by time within each project. Project headers displayed between project groups. Within each project, time-bucket interleaving applies across that project's files.

### `--group-by` with a single file

When there's only one file, `project` grouping has no visible effect. However, `time:` grouping still produces bucket headers showing temporal segments within the file, which can be useful for navigating long sessions.

### Bucket Key Computation

A message's bucket key is computed by formatting its timestamp (converted to local timezone) with the strftime pattern:

```python
bucket_key = message_dt.astimezone().strftime(strftime_pattern)
```

Two messages are in the same bucket if they produce the same bucket key string. This means:

- `time:%Y%m%d%H` → hourly buckets (e.g., "2026031714")
- `time:%Y%m%d` → daily buckets (e.g., "20260317")
- `time:%Y%m` → monthly buckets
- `time:%H` → by hour-of-day (would group 9am across different days together — unusual but valid; within a bucket, files from different days still sort by their first message timestamp)

### Ordering Within and Across Buckets

- **Across buckets:** chronological (ascending bucket key)
- **Within a bucket, across files:** files ordered by their first message timestamp in that bucket
- **Within a file's bucket segment:** messages in their natural file order (which is chronological)

## Algorithm: Two-Pass with File Cursors

### Pass 1: Scout

For each JSONL file in scope:

1. Open the file
2. If `--after`/`--before` are set, scan forward line-by-line (discarding each line from memory) until finding the first message whose timestamp falls within range
3. Record the file offset at that position
4. If no matching message found, discard the file
5. Close the file
6. Result: a list of `FileHandle` objects, each with a path and a starting offset

```python
@dataclass
class FileHandle:
    path: Path
    offset: int  # byte offset to start reading from
    project: str  # encoded project directory name
```

**Project name extraction:** `FileHandle.project` is derived from the file's parent directory name relative to `~/.claude/projects/`. If the file is directly under a project dir (e.g., `~/.claude/projects/-home-guy-myproject/session.jsonl`), the project is `-home-guy-myproject`. For files not under `~/.claude/projects/` (e.g., user passed an arbitrary directory), the project is the immediate parent directory name.

### Pass 2: Render

**When no `time:` grouping (project-only or no grouping):**

Trivial — for each file (or each project group of files), open the file, seek to the recorded offset, render start-to-finish, and close. One file at a time, sequential. This is essentially the current behavior with optional project headers.

**When `time:` grouping is present:**

1. Open a file handle for each `FileHandle` and seek to its recorded offset
2. Peek at the first message to determine its initial bucket key
3. Build a priority structure: files sorted by their current bucket key, then by first message timestamp within that bucket
4. For the current (lowest) bucket key:
   a. Collect all files that have messages in this bucket
   b. Order them by first message timestamp in this bucket
   c. For each file, read and render messages until the bucket key changes, `--before` cutoff is hit, or EOF
   d. When a file's bucket key changes, pause it (record its new position via the peeked line)
5. Move to the next bucket key
6. Repeat until all files are exhausted
7. Close all file handles

**Memory usage:** At most one line buffered per file (the "peeked" line to determine bucket key). All rendering is streamed — no bulk loading.

**File descriptor management:** During `time:` grouping, all matching files are open simultaneously. For most use cases this is fine (dozens to low hundreds of sessions). If the number of matching files exceeds a reasonable threshold (e.g., 500), emit a warning to stderr but proceed. The OS limit is typically 1024+ and can be raised with `ulimit`.

### Messages Without Timestamps

Messages without a `timestamp` field are rendered with their surrounding messages (they inherit the bucket of the preceding message in the same file). If a file has no timestamped messages at all, it falls into a special "no-timestamp" bucket rendered at the end.

## Interaction with Existing Features

| Feature | Interaction |
|---------|------------|
| `--after`/`--since` | Narrows which messages are included. Scout pass skips to first in-range message. |
| `--before`/`--until` | Narrows which messages are included. Rendering stops when a message exceeds the cutoff. |
| `--search` | Determines which files match. `--group-by` controls how matching files are rendered (only with `--stream`). |
| `--search` (no `--stream`) | `--group-by` has no effect — filepath-list mode. |
| `--watch` | `--group-by` is not applicable (live streaming). Error if combined. |
| `--grep`, `--show-type`, etc. | Applied as usual — message-level filters within each bucket. |
| `--compact`, `--hide-timestamps` | Display-level flags, unaffected. |
| `-n` (tail lines) | See below. |

### `-n` with `--group-by`

`-n` means "last N JSONL lines per file." When combined with `--group-by`:

- **No `time:` grouping:** Works as today — each file shows its last N lines.
- **With `time:` grouping:** Applied during the scout pass to set the starting offset to `max(time_filter_offset, last_N_offset)`. The last N lines of each file are then split across their respective time buckets. This is consistent: the user asks for "the last N lines" and gets them interleaved by time.

## Integration with Existing Code

The new `grouping.py` module contains the two-pass algorithm and `FileHandle`/`GroupByConfig` types. It is invoked from `cli.py` in two places:

1. **Directory mode** (currently in `main()` after the search block): When `--group-by` is set, the directory scanning logic delegates to `grouping.py` instead of the current inline loop.
2. **Search `--stream` mode**: When `--group-by` is set alongside `--search --stream`, matching files are passed to `grouping.py` instead of being rendered sequentially.

When `--group-by` is *not* set, the existing code paths are untouched — no refactoring of current behavior.

## Display

### Bucket Headers

When `time:` grouping is active, each file's bucket segment gets a header showing the file and bucket range. Uses existing `HeaderBlock` with `DividerBlock`:

```
📄 /path/to/session.jsonl [2026031709]
```

The bucket label is the raw bucket key string (the strftime output).

### Project Headers

When `project` grouping is active, project boundaries get a divider. Uses existing `DividerBlock` + `HeaderBlock`:

```
────────────────────────────────────────────────────────────
── Project: -home-guy-myproject ──
```

No new block types needed — reuse existing `HeaderBlock` and `DividerBlock`.

## Mutual Exclusivity

- `--group-by` + `--watch` → error ("cannot combine --group-by with --watch")
- `--group-by` + `--search` without `--stream` → no effect (filepath-list mode)

## Files Changed

| File | Changes |
|------|---------|
| `grouping.py` | **New** — `FileHandle`, `GroupByConfig`, bucket computation, two-pass algorithm, interleaving logic |
| `cli.py` | New `--group-by` flag, parse/validate spec, wire into directory/search-stream modes |
| `models.py` | `RenderConfig` gets `group_by: GroupByConfig | None = None` |
| `formatters.py` | No changes (uses existing block types) |
| `__init__.py` | Export `GroupByConfig` |
| `pyproject.toml` | Bump version to 0.4.0 |

## Future Note

This feature is a step toward a subcommand refactor. The `--group-by` flag adds complexity to the flag surface area that would be cleaner as `claude-stream search "text" --group-by ...` vs `claude-stream show file.jsonl`. The subcommand refactor remains the recommended next step after v0.4.0.
