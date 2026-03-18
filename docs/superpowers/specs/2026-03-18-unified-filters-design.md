# Unified `--show`/`--hide` Filter System Design Spec

**Date:** 2026-03-18
**Version target:** 0.6.0 (breaking change — old visibility flags removed)
**Current baseline:** 0.5.1

## Overview

Replace the scattered visibility flags (`--show-thinking`, `--hide-tool-results`, `--show-type`, `--show-subtype`, `--show-tool`, `--show-metadata`, `--show-timestamps`, `--hide-timestamps`) with a unified `--show`/`--hide`/`--show-only` system that operates on a single namespace of named filters. Add `--list-filters` for discoverability.

## Motivation

The current system has:
- 6 toggle flag pairs (`--show-X`/`--hide-X`) for content aspects
- 3 separate whitelist flags (`--show-type`, `--show-subtype`, `--show-tool`) for message filtering
- Two different semantics: toggle (show/hide thinking) vs. whitelist (show-type assistant)
- `--hide-tool-results` does double duty: hides messages AND content blocks
- No way to discover available types/subtypes

## Design

### CLI Flags

```
--show-only NAME[,NAME...]   Show ONLY these, hide everything else (repeatable)
--show NAME[,NAME...]        Ensure these are visible (repeatable)
--hide NAME[,NAME...]        Remove these from output (repeatable)
--list-filters               Show all available filter names and exit
```

All three accept comma-separated names and are repeatable:

```bash
claugs show --hide thinking,metadata
claugs show --hide thinking --hide metadata        # same thing
claugs show --show metadata                        # override default-hidden
claugs show --show-only assistant,user             # only these, hide rest
claugs show --show-only assistant --show metadata  # only assistant, plus metadata
```

### Priority Chain

When `--show-only`, `--show`, and `--hide` are combined, they are applied in this order:

1. **`--show-only`** — sets the base: hide everything NOT in this set
2. **`--show`** — adds back: ensure these are visible (overrides show-only's hiding AND --hide)
3. **`--hide`** — removes: hide these (but cannot override an explicit --show)

Resolution rule: **`--show` always wins over `--hide`** when the same name appears in both. `--show-only` establishes the baseline, then `--show` and `--hide` adjust from there.

```python
def is_visible(self, name: str) -> bool:
    # Explicit --show always wins
    if name in self.shown:
        return True
    # Explicit --hide (or not in show-only set)
    if name in self.hidden:
        return False
    # Default: visible unless in DEFAULT_HIDDEN
    return name not in self.DEFAULT_HIDDEN
```

### Multi-Level Filter Interaction

A message must pass **all applicable filter levels** independently. The "show wins" rule applies only when the **same name** appears in both `--show` and `--hide`. Different names at different levels are AND conditions:

```bash
# --show success does NOT override --hide result
# The message must pass BOTH the type check (result: hidden) AND the subtype check
claugs show --show success --hide result  # result messages still hidden

# To show only successful results: show the type, hide the subtype you don't want
claugs show --show-only result            # only result messages
```

### Filter Namespace

A single flat namespace, resolved in priority order when names collide:

#### Synthetic Filters (Content/Display Aspects)

| Name | Default | What it controls |
|------|---------|-----------------|
| `thinking` | shown | Thinking/reasoning blocks within assistant messages |
| `tools` | shown | Tool invocations (tool_use blocks including header) AND tool result content blocks AND tool-result/subagent-result user messages |
| `metadata` | **hidden** | Message metadata blocks (uuid, session ID, timestamp details) |
| `timestamps` | shown | Timestamp suffix in message headers (`· YYYY-MM-DD HH:MM:SS`) |
| `line-numbers` | **hidden** | Line number prefixes |

These are the highest priority. `--hide tools` hides the **entire** tool block (header + inputs + results), not just the details. This is a behavior change from v0.5.x where `--hide-tool-results` kept the tool header visible.

#### Computed Subtypes (User Message Classification)

| Name | Default | What it controls |
|------|---------|-----------------|
| `user-input` | shown | Human-typed user messages |
| `tool-result` | shown | Tool output messages (also hidden by `tools` synthetic filter) |
| `subagent-result` | shown | Sub-agent output messages (also hidden by `tools` synthetic filter) |
| `system-meta` | shown | System-injected meta messages (skill loading, etc.) |
| `local-command` | shown | Local slash command messages |

Note: the computed subtype for meta messages is `system-meta` (not `meta`) to avoid collision with potential JSON `subtype` values.

#### JSON Subtypes

| Name | Default | What it controls |
|------|---------|-----------------|
| `init` | shown | System init messages (`subtype: "init"`) |
| `compact-boundary` | shown | Compaction boundary messages |
| `success` | shown | Result messages with `subtype: "success"` |

Note: `compact-boundary` uses hyphens (normalized from the JSON value `compact_boundary`) for consistency with other multi-word filter names. Both forms are accepted during parsing.

#### Message Types

| Name | Default | What it controls |
|------|---------|-----------------|
| `system` | shown | System messages (all subtypes) |
| `assistant` | shown | Claude's responses |
| `user` | shown | User messages (all subtypes) |
| `summary` | shown | Summary messages |
| `queue-operation` | shown | Queue operation messages |
| `result` | shown | Session result/completion messages |
| `file-history-snapshot` | **hidden** | File state snapshots |

Note: `file-history-snapshot` is hidden by default (matching existing behavior from v0.2.0+).

#### Tool Names (Dynamic)

| Name | Default | What it controls |
|------|---------|-----------------|
| `Bash` | shown | Messages using the Bash tool |
| `Read` | shown | Messages using the Read tool |
| `Write` | shown | Messages using the Write tool |
| `Edit` | shown | Messages using the Edit tool |
| `Grep` | shown | Messages using the Grep tool |
| ... | shown | Any other tool name found in messages |

Tool names are dynamic — they come from the JSONL data, not a fixed list. Tool name matching is **case-sensitive** (tool names in Claude Code JSONL are capitalized, e.g., `Bash` not `bash`). Tool names are checked only after all other categories (priority 5), so they cannot shadow message types or subtypes.

### Resolution Priority

When processing a name through the filter system:

1. **Synthetic filter?** → Apply content/display behavior (may also affect message filtering)
2. **Computed subtype?** → Filter user messages by subtype
3. **JSON subtype?** → Filter messages by JSON `subtype` field (normalized: `compact_boundary` → `compact-boundary`)
4. **Message type?** → Filter messages by `type` field
5. **Tool name?** → Filter messages by tool name in content
6. **Unknown?** → Warning to stderr: `"warning: unknown filter: {name}"` (non-fatal)

### `--compact` Redefined

`--compact` becomes a shorthand for:

```bash
--hide thinking,tools,metadata,timestamps,system,summary,queue-operation,result
```

Note: `file-history-snapshot` is already hidden by default so `--compact` doesn't need to include it. Individual `--show` flags can override specific items:

```bash
claugs show --compact --show thinking     # compact but keep thinking visible
```

### `--list-filters`

Prints all known filter names with descriptions and defaults, then exits. When invoked without an input source, prints static filters only. When invoked with input, also discovers and lists tool names.

```
claugs show --list-filters

Synthetic filters (content/display):
  thinking              Thinking/reasoning blocks (default: shown)
  tools                 Tool invocations and results (default: shown)
  metadata              Message metadata (default: hidden)
  timestamps            Timestamp display in headers (default: shown)
  line-numbers          Line number prefixes (default: hidden)

Subtypes:
  user-input            Human-typed messages (default: shown)
  tool-result           Tool output messages (default: shown)
  subagent-result       Sub-agent output messages (default: shown)
  system-meta           System-injected meta messages (default: shown)
  local-command         Local slash command messages (default: shown)
  init                  System initialization (default: shown)
  compact-boundary      Compaction boundary (default: shown)
  success               Result status (default: shown)

Message types:
  system                System messages (default: shown)
  assistant             Claude's responses (default: shown)
  user                  User messages (default: shown)
  summary               Summary messages (default: shown)
  queue-operation       Queue operation messages (default: shown)
  result                Session completion (default: shown)
  file-history-snapshot File state snapshots (default: hidden)

Tool names are discovered from input data. Use --show or --hide
with any tool name (e.g., Bash, Read, Edit).
```

### `--timestamp-format`

Retained as a separate flag since it's a format string, not a toggle:

```
--timestamp-format FMT    Timestamp format (default: %Y-%m-%d %H:%M:%S)
```

### `--grep` and `--exclude`

Retained as separate flags — they operate on raw message text, not the filter namespace. **Evaluated after visibility filters:** a message hidden by `--hide` will not be matched by `--grep`.

```
--grep PATTERN            Include only messages matching pattern (repeatable)
--exclude PATTERN         Exclude messages matching pattern (repeatable)
```

## Removed Flags

This is a **breaking change**. All old visibility and type-filtering flags are removed:

| Old Flag | Replacement |
|----------|------------|
| `--show-thinking` | `--show thinking` |
| `--hide-thinking` | `--hide thinking` |
| `--show-tool-results` | `--show tools` |
| `--hide-tool-results` | `--hide tools` |
| `--show-metadata` | `--show metadata` |
| `--hide-metadata` | `--hide metadata` |
| `--show-timestamps` | `--show timestamps` |
| `--hide-timestamps` | `--hide timestamps` |
| `--show-type TYPE` | `--show TYPE` or `--show-only TYPE` |
| `--show-subtype SUBTYPE` | `--show SUBTYPE` or `--show-only SUBTYPE` |
| `--show-tool TOOL` | `--show TOOL` |
| `--line-numbers` | `--show line-numbers` |

### Migration Guide

| Old usage | New usage |
|-----------|-----------|
| `--show-type assistant` (whitelist) | `--show-only assistant` |
| `--show-type assistant,user` | `--show-only assistant,user` |
| `--show-subtype user-input` | `--show-only user-input` |
| `--compact` | `--compact` (same) |
| `--compact --show-thinking` | `--compact --show thinking` |
| `--hide-tool-results` | `--hide tools` |
| `--line-numbers` | `--show line-numbers` |

## Implementation

### Visibility State

Replace the scattered booleans and sets on `RenderConfig` with a unified structure:

```python
@dataclass
class FilterConfig:
    """Unified visibility configuration."""
    show_only: set[str] = field(default_factory=set)  # whitelist base (empty = no whitelist)
    shown: set[str] = field(default_factory=set)       # explicitly shown (overrides hidden)
    hidden: set[str] = field(default_factory=set)      # explicitly hidden

    # Defaults: everything shown except these
    DEFAULT_HIDDEN: ClassVar[set[str]] = {"metadata", "line-numbers", "file-history-snapshot"}

    def is_visible(self, name: str) -> bool:
        """Check if a filter name is visible."""
        # Explicit --show always wins
        if name in self.shown:
            return True
        # Explicit --hide
        if name in self.hidden:
            return False
        # --show-only baseline: if set, only listed names are visible
        if self.show_only and name not in self.show_only:
            return False
        # Default: visible unless in DEFAULT_HIDDEN
        return name not in self.DEFAULT_HIDDEN
```

`RenderConfig` gets:
```python
@dataclass
class RenderConfig:
    filters: FilterConfig = field(default_factory=FilterConfig)
    timestamp_format: str = "%Y-%m-%d %H:%M:%S"
    # Timestamp filtering (not part of the visibility system)
    before: datetime | None = None
    after: datetime | None = None
    # Text filtering
    grep_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    # Grouping
    group_by: GroupByConfig | None = None
```

### Filter Resolution in `should_show_message()`

```python
def should_show_message(msg, data, config):
    filters = config.filters

    # 1. Check message type visibility
    if not filters.is_visible(msg.type):
        return False

    # 2. Check subtype visibility (computed or JSON)
    if isinstance(msg, UserMessage):
        subtype = msg.get_subtype()
        if not filters.is_visible(subtype):
            return False
        # Also check synthetic "tools" filter for tool-result/subagent-result
        if subtype in ("tool-result", "subagent-result") and not filters.is_visible("tools"):
            return False
    elif hasattr(msg, 'subtype') and msg.subtype:
        # Normalize JSON subtype (compact_boundary → compact-boundary)
        normalized = msg.subtype.replace("_", "-")
        if not filters.is_visible(normalized):
            return False

    # 3. Check tool name visibility (for assistant messages with tool_use)
    # Extract tool names from content, check filters.is_visible(tool_name)
    # Only filter if at least one tool name is explicitly hidden

    # 4. Timestamp filtering (separate system, not part of visibility)
    # ... existing before/after logic

    # 5. Grep/exclude (separate system, evaluated after visibility)
    # ... existing logic
```

### Render-Level Visibility

Content blocks check `filters.is_visible()` instead of individual booleans:

```python
class ThinkingContent:
    def render(self, config):
        if not config.filters.is_visible("thinking"):
            return []
        # ... existing render logic

class ToolUseContent:
    def render(self, config):
        if not config.filters.is_visible("tools"):
            return []  # Hides entire block including header
        # ... existing render logic

class ToolResultContent:
    def render(self, config):
        if not config.filters.is_visible("tools"):
            return []
        # ... existing render logic
```

For timestamps:
```python
def format_timestamp_suffix(self, config):
    if not config.filters.is_visible("timestamps") or not self.timestamp:
        return ""
    # ... existing logic
```

For metadata:
```python
def render_metadata(self, config):
    if not config.filters.is_visible("metadata"):
        return []
    # ... existing logic
```

For line numbers:
```python
# In process_stream:
if config.filters.is_visible("line-numbers"):
    blocks.insert(0, TextBlock(...))
```

### UserMessage.get_subtype() Update

Rename the "meta" computed subtype to "system-meta":

```python
def get_subtype(self) -> str:
    if self.is_subagent_result():
        return "subagent-result"
    elif self.is_tool_result():
        return "tool-result"
    elif self.is_meta():
        return "system-meta"  # was "meta"
    elif self.is_local_command():
        return "local-command"
    else:
        return "user-input"
```

### CLI Parsing

```python
# On both show and watch subparsers (via shared parent):
filter_parent.add_argument(
    "--show-only", action="append", dest="show_only_filters", metavar="NAME[,NAME]",
    help="Show ONLY these, hide everything else (repeatable, comma-separated)",
)
filter_parent.add_argument(
    "--show", action="append", dest="show_filters", metavar="NAME[,NAME]",
    help="Ensure these are visible (repeatable, comma-separated)",
)
filter_parent.add_argument(
    "--hide", action="append", dest="hide_filters", metavar="NAME[,NAME]",
    help="Remove these from output (repeatable, comma-separated)",
)

# On show subparser only:
show_parser.add_argument(
    "--list-filters", action="store_true",
    help="Show available filter names and exit",
)
```

### Config Building

```python
def _build_filters(args) -> FilterConfig:
    show_only = set()
    shown = set()
    hidden = set()

    # 1. Apply --show-only (base whitelist)
    if args.show_only_filters:
        for spec in args.show_only_filters:
            show_only.update(name.strip() for name in spec.split(","))

    # Apply --compact (adds to hidden set)
    if args.compact:
        hidden.update({
            "thinking", "tools", "metadata", "timestamps",
            "system", "summary", "queue-operation", "result",
        })

    # 2. Apply --hide (expand comma-separated)
    if args.hide_filters:
        for spec in args.hide_filters:
            hidden.update(name.strip() for name in spec.split(","))

    # 3. Apply --show (expand comma-separated, overrides hide)
    if args.show_filters:
        for spec in args.show_filters:
            shown.update(name.strip() for name in spec.split(","))

    return FilterConfig(show_only=show_only, shown=shown, hidden=hidden)
```

## Files Changed

| File | Changes |
|------|---------|
| `models.py` | Add `FilterConfig`. Replace visibility booleans on `RenderConfig` with `filters: FilterConfig`. Rename `meta` → `system-meta` in `get_subtype()`. Update all render methods to use `filters.is_visible()`. |
| `stream.py` | Rewrite `should_show_message()` to use `FilterConfig.is_visible()`. Normalize JSON subtypes. |
| `cli.py` | Replace old flags with `--show-only`/`--show`/`--hide`/`--list-filters`/`--compact`. Update `_build_config()`. Add `--list-filters` handler. |
| `grouping.py` | Update any references to old RenderConfig fields |
| `__init__.py` | Export `FilterConfig` |
| `tests/*` | Update all tests for new flag syntax |
| `pyproject.toml` | Bump version to 0.6.0 |

## Watch Subcommand

The `watch` subcommand gets `--show-only`/`--show`/`--hide`/`--compact` with the same semantics (via the shared filter parent parser). `--list-filters` is only on `show`.

## `success` / `result` Interaction Note

The `success` JSON subtype only applies to `result`-type messages. `--hide result` hides all result messages regardless of subtype. `--show success --hide result` still hides them — the type-level check (hidden) and subtype-level check (shown) are AND conditions, not overrides. To see only successful results: `--show-only result`.
