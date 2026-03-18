# Search & Timestamps Design Spec

**Date:** 2026-03-17
**Version target:** 0.3.0
**Approach:** A (search as a mode, timestamps as filters)

## Overview

Three additions to claude-stream:

1. **Timestamp display** — show message timestamps in rendered output
2. **Text search** — find JSONL session files by content
3. **Timestamp filtering** — filter messages by time range with `--before`/`--after`

Plus a shared date parsing utility and a rename of `resolve_watch_path` to `resolve_project_path`.

## 0. Pre-existing Bug Fix: `--compact` Override

The current `cli.py` applies `--compact` settings first, then unconditionally overwrites them with individual flag values (argparse defaults). This means `--compact` has no actual effect on `show_thinking` or `show_tool_results`:

```python
if args.compact:
    config.show_thinking = False    # set to False...
config.show_thinking = args.show_thinking  # ...immediately overwritten with default True
```

**Fix:** Only apply individual visibility flags when the user explicitly provided them. Use argparse's `default=None` + post-processing to detect explicit vs. default values. This must be fixed as part of this work, since `--compact` will also need to set `show_timestamps = False`.

## 1. Timestamp Display

### CLI Flags

- `--show-timestamps` / `--hide-timestamps` (default: **show**)
- `--timestamp-format FMT` (default: `%Y-%m-%d %H:%M:%S`)
- `--compact` additionally sets `show_timestamps = False`

### RenderConfig Fields

```python
show_timestamps: bool = True
timestamp_format: str = "%Y-%m-%d %H:%M:%S"
```

### Display Format

Timestamps appear in the message header, separated by a middle dot:

```
▸ ASSISTANT · 2026-03-17 14:23:05
◂ USER · 2026-03-17 14:23:12
▸ SYSTEM (init) · 2026-03-17 14:22:58
```

In ANSI mode, the `· timestamp` portion uses `DIM` style. In Markdown and Plain, it renders as plain text.

### Implementation

Each message class's `render_header()` (or equivalent render path) parses the ISO 8601 `timestamp` field from `BaseMessage`, formats it with the configured format string, and appends `· {formatted_time}` to the header text. Messages without a timestamp skip it.

**Affected render methods:**
- `AgentStyleMessage.render_header()` (covers `AssistantMessage`)
- `UserMessage.render_user_input()` / `render_subagent()` / `render_local_command()`
- `SystemMessage.render()`
- `FileHistorySnapshot.render()`
- `SummaryMessage.render()`
- `QueueOperationMessage.render()`
- `ResultMessage.render()`

**Not affected:** `UserMessage.render_tool_result()` — this method produces no `HeaderBlock` (it directly renders `ToolResultContent` items), so there is no header to attach a timestamp to. Tool results inherit temporal context from their parent user message.

The timestamp is rendered as part of the `HeaderBlock` text content. In ANSI mode, the formatter applies `DIM` to the timestamp portion. This can be achieved by either:
- Appending a separate `TextBlock` with `DIM` style after the header, or
- Extending `HeaderBlock` with an optional `suffix` field that gets styled independently

The suffix approach is cleaner — it keeps the timestamp logically part of the header block while allowing formatters to style it differently.

### HeaderBlock Change

```python
@dataclass
class HeaderBlock(RenderBlock):
    text: str = ""
    level: int = 1
    icon: str = ""
    prefix: str = ""
    suffix: str = ""  # NEW — styled independently (DIM in ANSI)
```

Formatter updates:
- **ANSIFormatter:** `if block.suffix: text += self._apply_styles(f" {block.suffix}", {Style.DIM})`
- **MarkdownFormatter:** `if block.suffix: text += f" {block.suffix}"`
- **PlainFormatter:** `if block.suffix: text += f" {block.suffix}"`

## 2. Date Parsing Utility

### New Module: `src/claude_stream/dateparse.py`

Adapted from the `countdown` script's `parse_timestring` function (`/home/guy/code/python/bin/countdown`).

```python
def parse_datetime(text: str) -> datetime:
    """Parse a human-friendly date/time string into a datetime object.

    Supports:
    - ISO dates: 2026-03-17, 2026-03-17T14:23:05
    - Natural language: March 17 2026, Monday at 5pm
    - Keywords: noon, midnight, today, tomorrow
    - Relative times: now -2h, +30m, 5d, now +1w
    """
```

### Supported Syntax

| Input | Meaning |
|-------|---------|
| `2026-03-17` | Specific date |
| `2026-03-17T14:23:05` | Specific datetime |
| `yesterday` | Yesterday's date (via dateutil) |
| `today` | Today's date |
| `tomorrow` | Tomorrow's date |
| `noon` | Today at 12:00 |
| `midnight` | Today at 00:00 |
| `Monday at 5pm` | Next/last Monday at 5pm (via dateutil) |
| `now -2h` | 2 hours ago |
| `+30m` | 30 minutes from now |
| `5d` | 5 days from now |

### Dependency

`python-dateutil>=2.8` added as a **required** dependency in `pyproject.toml`.

**Rationale for required (not optional):** Date features (timestamp display, `--before`/`--after`) are a primary selling point of this release, with timestamps shown by default. Making `python-dateutil` optional would create a confusing experience where the default behavior degrades without an extra install. The package is small and widely used.

## 3. Text Search (`--search`)

### CLI Flags

- `--search TEXT` — search JSONL files for matching text
- `--stream` — render matching sessions instead of listing filepaths

### Scope Resolution

- No path given: searches all of `~/.claude/projects/`
- Path given (positional or `-f`): narrows to that directory/file
- Userland paths (e.g., `~/myproject`) resolved to claude project paths via `resolve_project_path` (renamed from `resolve_watch_path`)

### Behavior

1. Scan all `.jsonl` files recursively in scope
2. For each file, read lines and check if `TEXT` appears in the raw JSON string (literal, case-sensitive match — consistent with existing `--grep`)
3. Output depends on `--stream` flag:
   - **Without `--stream`:** one matching filepath per line, plain text to stdout (no formatter, `--format` has no effect)
   - **With `--stream`:** render matching sessions through the normal pipeline, with all other filters applied (`--before`/`--after`, `--grep`, `--hide-thinking`, etc.)

### Performance

- **Fast path (search only):** When `--search` is used without `--before`/`--after`, raw string scan — no JSON parsing needed.
- **Combined path (search + time filters):** Text search first to narrow candidate files, then JSON-parse + timestamp-filter only matching files.
- Early termination: in filepath-list mode (no `--stream`), stop reading a file as soon as a match is found.

### Output Ordering

Files sorted by modification time (most recent first), consistent with existing watch behavior.

### Mutual Exclusivity

`--search` is mutually exclusive with `--watch`, `--session`, and `--latest`. These are all "input modes" that determine what to process.

**Enforcement:** Manual validation in `main()`, consistent with how `--watch` is currently handled (it is not in the argparse `input_group`). Check for conflicting flags and print a clear error message.

`--search` can combine with a positional path argument to narrow scope (the path specifies *where* to search, not *what* to stream).

## 4. Timestamp Filtering (`--before`/`--after`)

### CLI Flags

- `--before DATETIME` — only show messages with timestamps before this time
- `--after DATETIME` — only show messages with timestamps after this time
- Both accept any string that `parse_datetime()` can handle

### RenderConfig Fields

```python
before: datetime | None = None
after: datetime | None = None
```

### Timezone Handling

JSONL timestamps are ISO 8601 and may include timezone info (e.g., `2026-03-17T14:23:05.123Z`). Rules:

- All timestamp comparisons are done in UTC.
- JSONL timestamps are parsed as-is; if timezone-aware, converted to UTC. If naive, assumed UTC.
- `parse_datetime()` produces timezone-aware datetimes. User input without timezone info is assumed local time and converted to UTC.
- This avoids naive-vs-aware comparison errors.

### Filter Logic

Added to `should_show_message()` in `stream.py`:

1. Parse the message's ISO 8601 `timestamp` field into a `datetime` (UTC-normalized)
2. If `config.after` is set and message timestamp < `config.after`, exclude
3. If `config.before` is set and message timestamp > `config.before`, exclude
4. Messages without timestamps pass through (not filtered out)

### Composition

`--before`/`--after` compose with all other modes and filters:

| Context | Behavior |
|---------|----------|
| Streaming a file | Only render messages in range |
| `--search` | A file only "matches" if at least one line falls in range AND contains search text |
| `--search --stream` | Render only messages in range from matching files (note: "matching files" is determined by the combined filter — text AND time range — not text alone; this prevents rendering time-filtered messages from a file where the matching text was outside the time range) |
| `--watch` | Only display new messages in range |
| `--grep`, `--show-type`, etc. | All stack as usual |

### Directory Mode

When given a directory + `--before`/`--after` (no `--search`, no `--watch`):

- Scan all `.jsonl` files recursively
- Render filepath headers + only messages whose timestamps match
- Skip files with zero matching messages
- This is the "show me what happened yesterday in this project" use case

**Entry point in `cli.py`:** The current "Determine input source" block (lines 232-258) only handles files and stdin. Directory mode adds a new branch: if the resolved path is a directory and timestamp filters are set, enter directory scanning mode. This goes between the watch-mode handler and the file-input handler in `main()`.

## 5. Rename: `resolve_watch_path` -> `resolve_project_path`

The existing `resolve_watch_path` function in `cli.py` is now used by both watch mode and search mode. Rename to `resolve_project_path` to reflect its general purpose.

## 6. Dependencies & Version

- **New dependency:** `python-dateutil>=2.8` (required)
- **Version bump:** 0.2.3 -> 0.3.0

## 7. Files Changed

| File | Changes |
|------|---------|
| `dateparse.py` | **New** — `parse_datetime()` function |
| `models.py` | `RenderConfig` gets `show_timestamps`, `timestamp_format`, `before`, `after` |
| `blocks.py` | `HeaderBlock` gets `suffix` field |
| `formatters.py` | All formatters handle `HeaderBlock.suffix` (DIM in ANSI) |
| `stream.py` | `should_show_message()` gets timestamp filtering |
| `cli.py` | New flags, `resolve_watch_path` -> `resolve_project_path`, search mode, directory scanning |
| `models.py` (messages) | All `render_header()`/`render()` methods include formatted timestamp in header suffix |
| `__init__.py` | Export `parse_datetime`, updated `resolve_project_path` name |
| `pyproject.toml` | Add `python-dateutil`, bump version to 0.3.0 |

## 8. Future Note

The growing feature set (stream, watch, search, directory scanning) is a strong signal that the next update should refactor into subcommands:

```
claude-stream show file.jsonl
claude-stream search "text" [path]
claude-stream watch path
```

Approach A is explicitly a bridge — it keeps backward compatibility now while the flag surface area is still manageable. A subcommand refactor would be the natural next step.
