# Test Fixtures

This directory contains versioned JSONL test fixtures for the claude-stream / claugs tool.

## What These Fixtures Are

Each `.jsonl` file is a realistic Claude Code conversation log. One JSON object per line,
representing the sequence of messages Claude Code writes to its session files
(`~/.claude/projects/**/*.jsonl`).

The fixtures cover all message types the tool handles:

| Message type | Description |
|---|---|
| `system` / `init` | Session initialization (model, version, cwd) |
| `user` / external | Human input typed by the user |
| `assistant` (thinking + text) | Response with an extended thinking block followed by text |
| `assistant` (tool_use) | Response that invokes a tool (e.g., Bash) |
| `user` (tool-result) | Tool output returned to the model |
| `assistant` (text after tool) | Response after receiving tool output |
| `result` | Session completion record with cost, token counts, and duration |

## Versioning

Fixtures are organized by the Claude Code version that would generate them:

```
v2.1.75/complete_session.jsonl   — March 15 2026 timestamps
v2.1.77/complete_session.jsonl   — March 17 2026 timestamps
```

Using different dates lets tests filter sessions by date range without having to construct
synthetic timestamps inline.

### When to Add New Fixtures

Add a new versioned directory (`vX.Y.Z/`) when a Claude Code release changes the JSONL schema
in a way that affects parsing — for example:

- New required or optional top-level fields on any message type
- Changed field names or restructured `message.content` shapes
- New `subtype` values for `system` or `result` messages

Keep the old fixtures intact so regression tests continue to verify backward compatibility.

## Multi-project Fixtures

`multi_project/` contains two short sessions under different project directories with
overlapping timestamps. This is useful for testing `--group-by project` and time-interleaving
behavior:

- `project-a/session-001.jsonl` — messages at 14:01, 14:15, 14:30
- `project-b/session-002.jsonl` — messages at 14:02, 14:20, 15:05
