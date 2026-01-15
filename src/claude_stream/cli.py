"""Command-line interface for claude-stream."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from . import (
    ANSIFormatter,
    Formatter,
    MarkdownFormatter,
    PlainFormatter,
    RenderConfig,
    process_stream,
    watch_path,
)


def encode_path(path: str) -> str:
    """Encode a filesystem path to Claude's .claude/projects/ format.

    Algorithm:
      - [a-zA-Z0-9-] → preserved
      - All other chars → max(1, floor(utf8_bytes/2)) dashes

    This means:
      - ASCII special chars (/, ., _, space) → 1 dash each
      - BMP chars (U+0000-U+FFFF, 1-3 bytes) → 1 dash each
      - SMP chars (U+10000+, 4 bytes) → 2 dashes each
    """
    result = []
    for char in path:
        if char.isalnum() or char == "-":
            result.append(char)
        else:
            # Calculate dashes: max(1, floor(bytes/2))
            byte_len = len(char.encode("utf-8"))
            dashes = max(1, byte_len // 2)
            result.append("-" * dashes)
    return "".join(result)


def resolve_watch_path(path: Path) -> Path:
    """Resolve a path to its Claude project directory if needed.

    If the path is already under ~/.claude, returns it as-is.
    Otherwise, converts the path to Claude's project format and
    returns that if it exists.
    """
    claude_base = Path.home() / ".claude"
    resolved = path.resolve()

    # Already under ~/.claude? Use directly
    try:
        resolved.relative_to(claude_base)
        return resolved
    except ValueError:
        pass  # Not under ~/.claude

    # Convert to Claude project path format
    encoded = encode_path(str(resolved))
    claude_path = claude_base / "projects" / encoded

    if claude_path.exists():
        return claude_path

    # Fall back to original path
    return resolved


def find_session_file(session_id: str | None = None, latest: bool = False) -> Path | None:
    """Find a session file by UUID or get the latest."""

    projects_dir = Path.home() / ".claude" / "projects"

    if not projects_dir.exists():
        return None

    if latest:
        jsonl_files = list(projects_dir.rglob("*.jsonl"))
        if not jsonl_files:
            return None
        return max(jsonl_files, key=lambda p: p.stat().st_mtime)

    if session_id:
        matches = list(projects_dir.rglob(f"{session_id}.jsonl"))
        return matches[0] if matches else None

    return None


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""

    parser = argparse.ArgumentParser(
        description="Parse and prettify Claude Code JSONL stream output",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Output Formats:
    ansi        Terminal colors (default)
    markdown    Markdown formatting
    plain       Plain text, no formatting

Examples:
    %(prog)s session.jsonl                      # Parse entire file
    %(prog)s session.jsonl -n 20                # Show last 20 lines
    %(prog)s --latest -n 50                     # Last 50 lines of most recent session
    %(prog)s --latest --format markdown > out.md
    %(prog)s --watch ~/.claude/projects/        # Watch all sessions
    %(prog)s --watch .                          # Watch current dir's Claude sessions
    %(prog)s --watch ~/myproject -n 10          # Watch project with initial context
        """
    )

    # Positional file argument
    parser.add_argument("input_file", nargs="?", type=Path, help="JSONL file to read")

    # Input sources (mutually exclusive with positional)
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument("-f", "--file", type=Path, help="Read from JSONL file")
    input_group.add_argument("--session", help="Find and parse session by UUID")
    input_group.add_argument("--latest", action="store_true", help="Parse most recent session")

    # Output format
    parser.add_argument(
        "--format", "-F",
        choices=["ansi", "markdown", "plain"],
        default=None,
        help="Output format (default: ansi, or plain if piped)"
    )

    # Visibility controls
    parser.add_argument("--show-thinking", dest="show_thinking", action="store_true", default=True)
    parser.add_argument("--hide-thinking", dest="show_thinking", action="store_false")
    parser.add_argument("--show-tool-results", dest="show_tool_results", action="store_true", default=True)
    parser.add_argument("--hide-tool-results", dest="show_tool_results", action="store_false")
    parser.add_argument("--show-metadata", dest="show_metadata", action="store_true", default=False)
    parser.add_argument("--hide-metadata", dest="show_metadata", action="store_false")
    parser.add_argument("--line-numbers", action="store_true", help="Show message numbers")
    parser.add_argument("--compact", action="store_true",
                        help="Shorthand for --hide-metadata --hide-thinking --hide-tool-results")

    # Filtering
    parser.add_argument("--show-type", action="append", dest="show_types",
                        help="Show only these message types (repeatable)")
    parser.add_argument("--show-subtype", action="append", dest="show_subtypes",
                        help="Show only these subtypes (repeatable)")
    parser.add_argument("--show-tool", action="append", dest="show_tools",
                        help="Show only these tools (repeatable)")
    parser.add_argument("--grep", action="append", dest="grep_patterns",
                        help="Include only messages matching pattern (repeatable)")
    parser.add_argument("--exclude", action="append", dest="exclude_patterns",
                        help="Exclude messages matching pattern (repeatable)")

    # Watch mode
    parser.add_argument("-w", "--watch", type=Path, metavar="PATH",
                        help="Watch a file or directory for changes (like tail -f)")
    parser.add_argument("-n", "--lines", type=int, default=0, metavar="N",
                        help="Show only last N lines (works with files and --watch)")

    return parser.parse_args()


def main() -> int:
    """Main entry point."""

    args = parse_args()

    # Build config
    config = RenderConfig()

    if args.compact:
        config.show_metadata = False
        config.show_thinking = False
        config.show_tool_results = False
        config.show_types = {"assistant", "user"}

    config.show_thinking = args.show_thinking
    config.show_tool_results = args.show_tool_results
    config.show_metadata = args.show_metadata
    config.show_line_numbers = args.line_numbers

    if args.show_types:
        config.show_types = set(args.show_types)
    if args.show_subtypes:
        config.show_subtypes = set(args.show_subtypes)
    if args.show_tools:
        config.show_tools = set(args.show_tools)
    if args.grep_patterns:
        config.grep_patterns = args.grep_patterns
    if args.exclude_patterns:
        config.exclude_patterns = args.exclude_patterns

    # Select formatter (default to plain if stdout is not a TTY)
    output_format = args.format
    if output_format is None:
        output_format = "ansi" if sys.stdout.isatty() else "plain"

    formatter: Formatter
    if output_format == "markdown":
        formatter = MarkdownFormatter()
    elif output_format == "plain":
        formatter = PlainFormatter()
    else:
        formatter = ANSIFormatter()

    # Handle watch mode
    if args.watch:
        watch_target = resolve_watch_path(args.watch)
        if not watch_target.exists():
            print(f"error: path not found: {args.watch}", file=sys.stderr)
            # If we tried to resolve to a Claude path, mention it
            if watch_target != args.watch.resolve():
                print(f"  (looked for Claude project at: {watch_target})", file=sys.stderr)
            return 1
        # Show resolved path if different from input
        if watch_target != args.watch.resolve():
            print(f"watching: {watch_target}", file=sys.stderr)
        watch_path(watch_target, config, formatter, recursive=True, tail_lines=args.lines)
        return 0

    # Determine input source
    input_file: TextIO

    # Positional file takes precedence over -f/--file
    file_path = args.input_file or args.file

    if file_path:
        if not file_path.exists():
            print(f"error: file not found: {file_path}", file=sys.stderr)
            return 1
        input_file = open(file_path)
    elif args.session:
        session_path = find_session_file(session_id=args.session)
        if not session_path:
            print(f"error: session not found: {args.session}", file=sys.stderr)
            return 1
        input_file = open(session_path)
    elif args.latest:
        session_path = find_session_file(latest=True)
        if not session_path:
            print("error: no sessions found", file=sys.stderr)
            return 1
        input_file = open(session_path)
    elif not sys.stdin.isatty():
        input_file = sys.stdin
    else:
        print("error: no input source specified", file=sys.stderr)
        return 1

    try:
        process_stream(input_file, config, formatter, tail_lines=args.lines)
    finally:
        if input_file is not sys.stdin:
            input_file.close()

    return 0


if __name__ == "__main__":
    exit_code: int = 0
    try:
        exit_code = main()
    except KeyboardInterrupt:
        print("\nexiting", file=sys.stderr)

    sys.exit(exit_code)
