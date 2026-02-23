# User Message Subtypes

## Problem

Claude Code's JSONL format stores three distinct categories of content as `type: "user"` messages:

1. **Real user input** - what the human typed
2. **Tool results** - responses from tool calls (Bash, Read, etc.)
3. **System-injected meta content** - skill loading, system reminders (`isMeta: true`)

This means `--show-type user` shows all three, `--hide-tool-results` only suppresses rendered content (not the messages themselves), and system-injected content renders with a `USER` header indistinguishable from real input.

## Design

### Subtype classification

Each `type: "user"` message gets a subtype based on JSONL fields:

| Subtype | Detection |
|---------|-----------|
| `user-input` | No `toolUseResult`, no `isMeta`, content is string |
| `tool-result` | Has `toolUseResult` (not subagent) |
| `subagent-result` | `toolUseResult` with `agentId` |
| `meta` | `isMeta: true` |
| `local-command` | Content starts with `<command-name>` or `<local-command-stdout>` |

### Filtering

`--show-subtype` applies to user messages via their computed subtype. Without `--show-subtype`, all subtypes display (backward compatible).

Example: `--show-type user --show-subtype user-input` shows only real human input.

### `--hide-tool-results` fix

When `show_tool_results=False`, tool-result and subagent-result user messages are fully filtered out in `should_show_message()`, not just content-suppressed.

### Meta rendering

Messages with `isMeta: true` render as `USER [meta]` instead of plain `USER`.

## Changes

1. **`models.py`**: Add `isMeta` field, `get_subtype()` method, `[meta]` tag in `render_user_input()`
2. **`stream.py`**: Subtype filtering for user messages, `--hide-tool-results` suppression
3. **`cli.py`**: No changes needed (existing flags sufficient)
