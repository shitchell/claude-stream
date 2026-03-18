# Claugs Refactor Design Spec

**Date:** 2026-03-18
**Version target:** 0.5.0 (new package name: `claugs`)
**Current baseline:** 0.4.0 (published to PyPI as `claude-stream`)

## Overview

Rename the project from `claude-stream` to `claugs` and refactor the flat flag-based CLI into two subcommands: `show` (default) and `watch`. Merge the current `--search` mode into `show` as a filter. Replace `--stream` with `--filepaths-only` (inverted default). No backward compatibility with the old `claude-stream` command.

## Rename

### Package Names

| What | Old | New |
|------|-----|-----|
| PyPI package | `claude-stream` | `claugs` |
| CLI command | `claude-stream` | `claugs` |
| Python import | `claude_stream` | `claude_logs` |
| Source directory | `src/claude_stream/` | `src/claude_logs/` |
| Test imports | `from claude_stream...` | `from claude_logs...` |

### Files Changed for Rename

| File | Change |
|------|--------|
| `pyproject.toml` | name, version, description, entry point, package path, keywords |
| `src/claude_stream/` → `src/claude_logs/` | Rename directory |
| All `*.py` under `src/claude_logs/` | Update `__init__.py` docstring |
| `src/claude_logs/__main__.py` | Update import path (supports `python -m claude_logs`) |
| All `tests/*.py` | `from claude_stream` → `from claude_logs` |
| `tests/conftest.py` | Same import updates |
| `README.md` | Update all references |

Internal relative imports (`from .models import ...`) are unaffected by the rename since they use `.` notation.

### `pyproject.toml` Changes

```toml
[project]
name = "claugs"
version = "0.5.0"
description = "Parse and prettify Claude Code JSONL session logs"
keywords = ["claude", "anthropic", "jsonl", "cli", "logs"]

[project.scripts]
claugs = "claude_logs.cli:main"

[project.urls]
Homepage = "https://github.com/shitchell/claude-stream"
Repository = "https://github.com/shitchell/claude-stream"
Issues = "https://github.com/shitchell/claude-stream/issues"
```

Note: GitHub repo URL stays as `claude-stream` unless manually renamed on GitHub.

## Subcommand Architecture

### Command Structure

```
claugs <command> [options]
```

Two subcommands:
- **`show`** — render sessions with filtering (default if no subcommand given)
- **`watch`** — live monitoring of session files

### Backward Compatibility

None. The `claude-stream` entry point is removed entirely. `pip install claugs` provides only the `claugs` command. The old `claude-stream` PyPI package stays at 0.4.0 permanently.

### Removed / Renamed Flags

| Old | New | Notes |
|-----|-----|-------|
| `--stream` | (removed) | Default is now render; use `--filepaths-only` to list paths |
| `--search` (mode) | `--search` (filter on `show`) | No longer mutually exclusive with `--latest`/`--session`/source |
| `-w, --watch PATH` | `claugs watch PATH` | Becomes a subcommand |
| `input_file` (positional) | `source` (positional) | Renamed for clarity |

### Lifted Restrictions

In the current code, `--search` is mutually exclusive with `--session` and `--latest`. **These restrictions are removed.** `--search` is now composable with all source options — it simply filters which files/sessions are processed.

The old test `test_search_with_latest_is_error` should be removed and replaced with a test verifying the combination works.

## `claugs show`

The primary subcommand. Combines the current file rendering, directory scanning, and search functionality into one unified command with `git log`-style filtering.

### Usage

```
claugs show [source] [options]
claugs [source] [options]          # "show" is implied when omitted
```

### Source Argument

The positional `source` argument accepts:

- **A JSONL filepath** — render that session
- **A directory** — scan all `.jsonl` files in that directory. This can be:
  - A userland directory (e.g., `~/myproject`) — resolved to its `~/.claude/projects/` equivalent
  - A `~/.claude/projects/` subdirectory directly
  - `~/.claude/projects/` itself (all projects)
- **Omitted** — reads from stdin, or requires `--latest`/`--session`

### Source Options

```
-f, --file FILEPATH             Read from JSONL filepath
--session UUID                  Find session by UUID
--latest                        Most recent session
```

**Precedence:** If both positional `source` and `-f`/`--file` are provided, emit an error: `"error: cannot specify both positional source and --file"`. `--session` and `--latest` are mutually exclusive with each other (enforced by argparse group) but composable with `--search` and other filters.

### Filtering Options

```
--after, --since DATETIME       Only messages after this time
--before, --until DATETIME      Only messages before this time
--search TEXT                   Only files containing this text (case-sensitive)
--grep PATTERN                  Only messages matching pattern (repeatable)
--exclude PATTERN               Exclude messages matching pattern (repeatable)
--show-type TYPE                Only these message types (repeatable)
--show-subtype SUBTYPE          Only these subtypes (repeatable)
--show-tool TOOL                Only these tools (repeatable)
-n, --lines N                   Last N lines per file
```

`--search` is now a filter, not a mode. When used:
- Narrows which files are processed (only files containing the text)
- Then renders matching files through the normal pipeline
- Combined with `--after`/`--before`, both filters must be satisfied on the same line for a file to match (existing behavior from `_find_matching_files`)

Future work: `--ignore-case` / `-i` for case-insensitive `--search` and `--grep`.

### Output Mode

```
--filepaths-only, -l            Print matching filepaths instead of rendering
```

Default: render sessions. With `--filepaths-only`: print one filepath per line, plain text, no formatter.

`--filepaths-only` is useful with:
- `--search TEXT` — "which sessions mention this text?"
- A directory + `--after` — "which sessions have recent activity?"
- `--latest` — "what's the filepath of the latest session?"
- Any combination of filters — "what matches these criteria?"

### Display Options

```
-F, --format {ansi,markdown,plain}   Output format
--compact                            Hide thinking, tools, metadata, timestamps; filter to assistant+user only
--show-timestamps / --hide-timestamps
--timestamp-format FMT
--show-thinking / --hide-thinking
--show-tool-results / --hide-tool-results
--show-metadata / --hide-metadata
--line-numbers
```

**`--compact` full behavior:** Sets `show_thinking=False`, `show_tool_results=False`, `show_metadata=False`, `show_timestamps=False`, and filters `show_types` to `{"assistant", "user"}` only. Individual flags override these when explicitly provided.

### Grouping Options

```
--group-by SPEC                 Group by 'project' and/or 'time:<strftime>'
```

Same behavior as v0.4.0. Only applies in multi-file mode (directory or search results). Ignored with `--filepaths-only`.

### Behavior Matrix

| Input | `--search` | `--filepaths-only` | Result |
|-------|-----------|-------------------|--------|
| JSONL file | no | no | Render the file |
| JSONL file | no | yes | Print the filepath |
| JSONL file | yes | no | Render if file contains text, else nothing |
| JSONL file | yes | yes | Print filepath if file contains text |
| Directory | no | no | Scan and render all matching files |
| Directory | no | yes | List all JSONL filepaths |
| Directory | yes | no | Scan, filter by text, render matching |
| Directory | yes | yes | List matching filepaths |
| `--latest` | no | no | Render most recent session |
| `--latest` | no | yes | Print filepath of latest session |
| `--latest` | yes | no | Render if latest contains text |
| `--latest` | yes | yes | Print filepath if latest contains text |
| `--session UUID` | no | no | Render that session |
| `--session UUID` | no | yes | Print filepath of that session |
| stdin | no | no | Render from stdin |
| stdin | no | yes | Error: no filepath to print from stdin |
| None | no | no | Error: no input source |

### Error Handling

| Condition | Error message |
|-----------|--------------|
| No input source | `error: no input source specified` |
| Non-existent file | `error: file not found: <path>` |
| Non-existent directory (after resolution) | `error: path not found: <path>` (with note about Claude project path if resolution was attempted) |
| Directory with no `.jsonl` files | No output (silent, not an error) |
| Both positional source and `--file` | `error: cannot specify both positional source and --file` |
| `--filepaths-only` with stdin | `error: --filepaths-only cannot be used with stdin` |
| Invalid `--group-by` | `error: invalid group-by key: ...` (existing) |
| Invalid `--before`/`--after` | `error: cannot parse --before date: ...` (existing) |

## `claugs watch`

Unchanged from current `--watch` behavior. Slim subcommand.

### Usage

```
claugs watch PATH [options]
```

### Source Argument

`PATH` is required. Accepts:
- A JSONL filepath — watch that file
- A directory — watch for changes in all `.jsonl` files (recursive). Same resolution rules as `show`: userland dirs get resolved to `~/.claude/projects/` equivalents.

Note: there is no `--latest` for `watch`. To watch the most recent session: `claugs watch $(claugs --latest -l)`.

### Options

```
-n, --lines N                   Show last N lines of context before watching
--after, --since DATETIME       Only show messages after this time
--before, --until DATETIME      Only show messages before this time
--grep PATTERN                  Only messages matching pattern (repeatable)
--exclude PATTERN               Exclude messages matching pattern (repeatable)
--show-type TYPE                Filter by message type (repeatable)
--show-subtype SUBTYPE          Filter by subtype (repeatable)
--show-tool TOOL                Filter by tool (repeatable)
-F, --format {ansi,markdown,plain}
--compact
--show-timestamps / --hide-timestamps
--timestamp-format FMT
--show-thinking / --hide-thinking
--show-tool-results / --hide-tool-results
--show-metadata / --hide-metadata
```

No `--group-by` (incompatible with live streaming).
No `--search` (use `show --search` then `watch` the result).
No `--filepaths-only` (doesn't make sense for watching).

**Note on `-n`:** For `watch`, `-n N` means "show last N lines as initial context before starting live monitoring." For `show`, it means "last N lines per file." These are the same underlying mechanic but serve different UX purposes.

## Implementation Strategy

### argparse Structure

Use `argparse.add_subparsers` with `dest="command"`. Create a shared parent parser for common options (format, display flags, message-level filters), then extend for each subcommand.

### Default Subcommand Handling

Standard `argparse.add_subparsers` does not forward arguments to a default subparser when no subcommand keyword is given. To make `show` the default, use the re-parse approach:

```python
args = parser.parse_args()
if args.command is None:
    # No subcommand given — re-parse with "show" injected
    args = parser.parse_args(["show"] + sys.argv[1:])
```

This ensures all `show`-specific arguments (like `source`, `--search`, `--filepaths-only`, `--group-by`) are available even when the user omits the `show` keyword.

### Refactoring `main()`

The current monolithic `main()` function gets split into:

- `main()` — parse args, build config/formatter, dispatch to handler
- `handle_show(args, config, formatter)` — all show logic (file, directory, search, stdin)
- `handle_watch(args, config, formatter)` — watch logic

This is a straightforward extraction — the logic already exists in `main()`, it just needs to be pulled into separate functions.

### `--search` as a Filter

Currently `--search` is a mode with its own code path in `main()`. In the refactor:

1. `--search` becomes a flag on the `show` subcommand
2. When set, it filters which files to process (before rendering)
3. The `_find_matching_files` helper still works as-is
4. The `--stream` flag is removed
5. `--filepaths-only` replaces it (inverted default)

### Directory Handling

The current code has separate paths for "directory mode" and "search mode" that both scan directories. In the refactor, these merge:

1. Resolve the source path (userland → claude project path)
2. If it's a directory, collect all `.jsonl` files
3. If `--search` is set, filter files by text content
4. If `--filepaths-only`, print paths and exit
5. Otherwise, render (with optional `--group-by`)

## Files Changed

| File | Change |
|------|--------|
| `src/claude_stream/` → `src/claude_logs/` | **Rename directory** |
| `src/claude_logs/__init__.py` | Update docstring |
| `src/claude_logs/__main__.py` | Update import path (`from claude_logs.cli import main`) |
| `src/claude_logs/cli.py` | Refactor into subcommands, split `main()` into handlers |
| `pyproject.toml` | Rename package, update entry point/description/keywords, bump to 0.5.0 |
| `tests/*.py` | Update all imports |
| `tests/conftest.py` | Update imports |
| `README.md` | Update all references |

Modules that need NO internal changes (only the directory rename affects them):
- `models.py`, `blocks.py`, `formatters.py`, `stream.py`, `watcher.py`, `dateparse.py`, `grouping.py` — all use relative imports

## Migration

No backward compatibility. Users run:

```bash
pip uninstall claude-stream
pip install claugs
```
