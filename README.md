# claugs

[![PyPI version](https://badge.fury.io/py/claugs.svg)](https://pypi.org/project/claugs/)

Parse and prettify Claude Code JSONL session logs.

## Installation

```bash
pip install claugs
```

For file watching support:

```bash
pip install "claugs[watch]"
```

## Usage

claugs has two subcommands: `show` (render sessions) and `watch` (live monitoring).

### Show

Render sessions with filtering. Accepts JSONL files, directories, or `--latest`/`--session`.

```bash
# Render a session file
claugs show session.jsonl

# Last 50 lines of the most recent session
claugs show --latest -n 50

# Find and render a session by UUID
claugs show --session abc123

# Read from stdin
cat session.jsonl | claugs show

# Render sessions from a project directory
claugs show ~/myproject

# Markdown export
claugs show --latest --format markdown > export.md
```

Directories are automatically resolved to Claude's project format (e.g., `~/myproject` becomes `~/.claude/projects/-home-user-myproject`).

### Watch

Monitor session files for new messages in real-time (like `tail -f`):

```bash
# Watch all Claude sessions
claugs watch ~/.claude/projects/

# Watch from any project directory (auto-resolves)
claugs watch .
claugs watch ~/myproject

# Watch with initial context (last N lines)
claugs watch . -n 10
```

### Search

`--search` is a filter on `show` that narrows to files containing the search text:

```bash
# Find sessions containing "error" and render them
claugs show --search "error"

# Just list matching filepaths
claugs show --search "error" -l

# Combine with time filters
claugs show --search "bug" --since "yesterday" ~/myproject
```

### Time Filtering

Filter messages by timestamp using `--after`/`--since` and `--before`/`--until`:

```bash
# Today's messages
claugs show --since "today" ~/myproject

# Last 2 hours
claugs show --since "2 hours ago" .

# Specific range
claugs show --after "2026-03-17" --before "2026-03-18" .
```

Accepts ISO dates, natural language (`yesterday`, `noon`, `tomorrow`), and relative times (`now -2h`, `30 minutes ago`, `5d`).

### Grouping

When scanning multiple files, `--group-by` controls how results are organized:

```bash
# Group by project directory
claugs show --since "today" ~/.claude/projects/ --group-by project

# Interleave messages by hour across files
claugs show --since "today" . --group-by time:%Y%m%d%H

# Combine: project first, then hourly interleaving within each
claugs show --since "today" . --group-by project,time:%Y%m%d%H
```

### Visibility: `--show` / `--hide` / `--show-only`

A unified system controls what appears in the output. Use `--list-filters` to see all available filter names:

```bash
claugs show --list-filters
```

Toggle visibility:

```bash
# Hide thinking blocks and tool content
claugs show --latest --hide thinking,tools

# Show metadata (hidden by default)
claugs show --latest --show metadata

# Only show assistant messages
claugs show --latest --show-only assistant

# Compact mode (hides thinking, tools, metadata, timestamps, system messages)
claugs show --latest --compact

# Compact but keep thinking visible
claugs show --latest --compact --show thinking
```

Priority chain: `--show-only` sets the base, `--show` adds back, `--hide` removes. `--show` always wins over `--hide` for the same filter name.

#### Filter categories

**Message types:** `assistant`, `user`, `system`, `summary`, `queue-operation`, `result`, `file-history-snapshot`, `progress`

**Subtypes:** `user-input`, `tool-result`, `subagent-result`, `system-meta`, `local-command`, `init`, `compact-boundary`, `success`

**Content:** `thinking`, `tools`, `metadata`, `timestamps`, `line-numbers`

**Tool names:** Any tool name from the data (e.g., `Bash`, `Read`, `Edit`) — use `--show` or `--hide` with the tool name directly.

### Output Formats

```bash
# ANSI terminal colors (default for TTY)
claugs show session.jsonl

# Markdown
claugs show --format markdown session.jsonl > export.md

# Plain text (default when piped)
claugs show session.jsonl | less
```

### Text Filtering

```bash
# Include only messages matching a pattern
claugs show --grep "error" session.jsonl

# Exclude messages matching a pattern
claugs show --exclude "cache" session.jsonl
```

## Architecture

```
JSONL → Pydantic Models → RenderBlocks → Formatters → Output
```

- **Models** (`models.py`) — Pydantic-based message types with a discriminated union. Each message type auto-registers via class hierarchy introspection. Subtypes and content filters also self-register via class variables.
- **RenderBlocks** (`blocks.py`) — Format-agnostic rendering primitives (HeaderBlock, TextBlock, CodeBlock, etc.)
- **Formatters** (`formatters.py`) — Convert RenderBlocks to ANSI, Markdown, or plain text
- **Stream** (`stream.py`) — Message filtering (`should_show_message`) and stream processing
- **FilterConfig** (`models.py`) — Unified visibility system with `is_visible(name)` resolution
- **Grouping** (`grouping.py`) — Two-pass file cursor algorithm for `--group-by` interleaving
- **DateParse** (`dateparse.py`) — Human-friendly date/time parsing for `--after`/`--before`

### Adding new message types

1. Define a class inheriting from `BaseMessage` (or a subclass) with `type: Literal["your-type"]`
2. Add `_filter_description` and optionally `_filter_default_visible` / `_known_subtypes`
3. Add it to the `Message` discriminated union
4. It auto-registers in the filter system — `--list-filters`, `--show`/`--hide`, and `parse_message()` all pick it up

## License

[WTFPL](http://www.wtfpl.net/)
