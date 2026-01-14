# claude-stream

Parse and prettify Claude Code JSONL stream output.

## Installation

```bash
pip install claude-stream
```

For file watching support:

```bash
pip install "claude-stream[watch]"
```

## Usage

```bash
# Read from a file
claude-stream session.jsonl

# Read from stdin
cat session.jsonl | claude-stream

# Parse the most recent session
claude-stream --latest

# Find and parse a session by UUID
claude-stream --session abc123

# Watch for new messages (like tail -f)
claude-stream --watch ~/.claude/projects/

# Watch with initial context (last N lines)
claude-stream --watch session.jsonl -n 10
```

### Output Formats

```bash
# ANSI terminal colors (default)
claude-stream --format ansi session.jsonl

# Markdown
claude-stream --format markdown session.jsonl > export.md

# Plain text
claude-stream --format plain session.jsonl
```

### Filtering

```bash
# Show only specific message types
claude-stream --show-type assistant --show-type user session.jsonl

# Show only messages with specific tools
claude-stream --show-tool Bash --show-tool Read session.jsonl

# Grep for patterns
claude-stream --grep "error" session.jsonl

# Exclude patterns
claude-stream --exclude "thinking" session.jsonl
```

### Display Options

```bash
# Hide thinking blocks
claude-stream --hide-thinking session.jsonl

# Hide tool results
claude-stream --hide-tool-results session.jsonl

# Show metadata (UUIDs, timestamps)
claude-stream --show-metadata session.jsonl

# Compact mode (hide thinking, tool results, metadata)
claude-stream --compact session.jsonl

# Show line numbers
claude-stream --line-numbers session.jsonl
```

## Architecture

- **Pydantic models** parse JSON into typed message structures
- **Messages** produce `RenderBlock` lists (flexible rendering primitives)
- **Formatters** convert `RenderBlocks` to output formats (ANSI, Markdown, Plain)

## License

MIT
