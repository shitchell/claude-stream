"""Command-line interface for claude-stream."""

from __future__ import annotations

import argparse
import json as _json
import os
import sys
from datetime import datetime, timezone
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
from .blocks import DividerBlock, HeaderBlock, Style
from .dateparse import parse_datetime
from .models import parse_message
from .stream import should_show_message


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


def resolve_project_path(path: Path) -> Path:
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


def find_session_file(
    session_id: str | None = None, latest: bool = False
) -> Path | None:
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
    %(prog)s --search "error message"              # Find sessions containing text
    %(prog)s --search "bug" --stream ~/project     # Render matching sessions
    %(prog)s --latest --after "today"              # Today's messages only
    %(prog)s --after "now -2h" --before "now" .    # Messages from last 2 hours
    %(prog)s --latest --hide-timestamps            # Hide timestamp display
        """,
    )

    # Positional file argument
    parser.add_argument("input_file", nargs="?", type=Path, help="JSONL file to read")

    # Input sources (mutually exclusive with positional)
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument("-f", "--file", type=Path, help="Read from JSONL file")
    input_group.add_argument("--session", help="Find and parse session by UUID")
    input_group.add_argument(
        "--latest", action="store_true", help="Parse most recent session"
    )

    # Output format
    parser.add_argument(
        "--format",
        "-F",
        choices=["ansi", "markdown", "plain"],
        default=None,
        help="Output format (default: markdown if CLAUDECODE is set, ansi if TTY, plain if piped)",
    )

    # Visibility controls
    parser.add_argument(
        "--show-thinking", dest="show_thinking", action="store_true", default=None
    )
    parser.add_argument("--hide-thinking", dest="show_thinking", action="store_false")
    parser.add_argument(
        "--show-tool-results",
        dest="show_tool_results",
        action="store_true",
        default=None,
    )
    parser.add_argument(
        "--hide-tool-results", dest="show_tool_results", action="store_false"
    )
    parser.add_argument(
        "--show-metadata", dest="show_metadata", action="store_true", default=None
    )
    parser.add_argument("--hide-metadata", dest="show_metadata", action="store_false")
    parser.add_argument(
        "--line-numbers", action="store_true", help="Show message numbers"
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Shorthand for --hide-metadata --hide-thinking --hide-tool-results",
    )

    # Filtering
    parser.add_argument(
        "--show-type",
        action="append",
        dest="show_types",
        help="Show only these message types (repeatable)",
    )
    parser.add_argument(
        "--show-subtype",
        action="append",
        dest="show_subtypes",
        help="Show only these subtypes (repeatable)",
    )
    parser.add_argument(
        "--show-tool",
        action="append",
        dest="show_tools",
        help="Show only these tools (repeatable)",
    )
    parser.add_argument(
        "--grep",
        action="append",
        dest="grep_patterns",
        help="Include only messages matching pattern (repeatable)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        dest="exclude_patterns",
        help="Exclude messages matching pattern (repeatable)",
    )

    # Timestamp display
    parser.add_argument(
        "--show-timestamps",
        dest="show_timestamps",
        action="store_true",
        default=None,
    )
    parser.add_argument(
        "--hide-timestamps", dest="show_timestamps", action="store_false"
    )
    parser.add_argument(
        "--timestamp-format",
        dest="timestamp_format",
        default=None,
        help="Timestamp format string (default: %%Y-%%m-%%d %%H:%%M:%%S)",
    )

    # Timestamp filtering
    parser.add_argument(
        "--before",
        dest="before",
        metavar="DATETIME",
        help="Only show messages before this time",
    )
    parser.add_argument(
        "--after",
        dest="after",
        metavar="DATETIME",
        help="Only show messages after this time",
    )

    # Search mode
    parser.add_argument(
        "--search",
        dest="search_text",
        metavar="TEXT",
        help="Search JSONL files for matching text",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="With --search: render matching sessions instead of listing filepaths",
    )

    # Watch mode
    parser.add_argument(
        "-w",
        "--watch",
        type=Path,
        metavar="PATH",
        help="Watch a file or directory for changes (like tail -f)",
    )
    parser.add_argument(
        "-n",
        "--lines",
        type=int,
        default=0,
        metavar="N",
        help="Show only last N lines (works with files and --watch)",
    )

    return parser.parse_args()


def _find_matching_files(
    jsonl_files: list[Path],
    search_text: str,
    config: RenderConfig,
) -> list[Path]:
    """Find JSONL files matching search text and optional time filters.

    Each line must satisfy BOTH the text match AND time range (if set)
    for a file to be considered matching.
    """
    has_time_filter = config.before is not None or config.after is not None
    matching: list[Path] = []

    for jf in jsonl_files:
        try:
            with open(jf) as f:
                for line in f:
                    if search_text not in line:
                        continue

                    # Text matched — check time filter if present
                    if not has_time_filter:
                        matching.append(jf)
                        break  # Early termination

                    # Parse timestamp from matching line
                    try:
                        data = _json.loads(line)
                        ts_str = data.get("timestamp", "")
                        if not ts_str:
                            continue  # No timestamp on this line, keep looking
                        msg_dt = datetime.fromisoformat(
                            ts_str.replace("Z", "+00:00")
                        )
                        if msg_dt.tzinfo is None:
                            msg_dt = msg_dt.replace(tzinfo=timezone.utc)
                        in_range = True
                        if config.after and msg_dt < config.after:
                            in_range = False
                        if config.before and msg_dt > config.before:
                            in_range = False
                        if in_range:
                            matching.append(jf)
                            break
                    except (_json.JSONDecodeError, ValueError):
                        continue
        except (IOError, OSError):
            continue

    return matching


def main() -> int:
    """Main entry point."""

    args = parse_args()

    # Build config
    config = RenderConfig()

    # Apply --compact first
    if args.compact:
        config.show_metadata = False
        config.show_thinking = False
        config.show_tool_results = False
        config.show_timestamps = False
        config.show_types = {"assistant", "user"}

    # Apply explicit visibility flags (override compact if set)
    if args.show_thinking is not None:
        config.show_thinking = args.show_thinking
    if args.show_tool_results is not None:
        config.show_tool_results = args.show_tool_results
    if args.show_metadata is not None:
        config.show_metadata = args.show_metadata
    if args.show_timestamps is not None:
        config.show_timestamps = args.show_timestamps
    if args.timestamp_format is not None:
        config.timestamp_format = args.timestamp_format

    # Note: show_line_numbers uses store_true (default=False), not the None pattern,
    # because it's opt-in only — --compact doesn't affect it.
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

    # Select formatter
    # Priority: explicit --format > CLAUDECODE env var > TTY detection
    output_format = args.format
    if output_format is None:
        if os.environ.get("CLAUDECODE"):
            output_format = "markdown"
        elif sys.stdout.isatty():
            output_format = "ansi"
        else:
            output_format = "plain"

    formatter: Formatter
    if output_format == "markdown":
        formatter = MarkdownFormatter()
    elif output_format == "plain":
        formatter = PlainFormatter()
    else:
        formatter = ANSIFormatter()

    # Parse --before/--after into datetimes
    if args.before:
        try:
            config.before = parse_datetime(args.before)
        except ValueError:
            print(
                f"error: cannot parse --before date: {args.before}", file=sys.stderr
            )
            return 1

    if args.after:
        try:
            config.after = parse_datetime(args.after)
        except ValueError:
            print(
                f"error: cannot parse --after date: {args.after}", file=sys.stderr
            )
            return 1

    # Handle watch mode
    if args.watch:
        watch_target = resolve_project_path(args.watch)
        if not watch_target.exists():
            print(f"error: path not found: {args.watch}", file=sys.stderr)
            # If we tried to resolve to a Claude path, mention it
            if watch_target != args.watch.resolve():
                print(
                    f"  (looked for Claude project at: {watch_target})", file=sys.stderr
                )
            return 1
        # Show resolved path if different from input
        if watch_target != args.watch.resolve():
            print(f"watching: {watch_target}", file=sys.stderr)
        watch_path(
            watch_target, config, formatter, recursive=True, tail_lines=args.lines
        )
        return 0

    # Handle search mode
    if args.search_text:
        # Mutual exclusivity check
        if args.watch:
            print(
                "error: cannot combine --search with --watch", file=sys.stderr
            )
            return 1
        if args.session:
            print(
                "error: cannot combine --search with --session", file=sys.stderr
            )
            return 1
        if args.latest:
            print(
                "error: cannot combine --search with --latest", file=sys.stderr
            )
            return 1

        # Determine search scope
        search_path = args.input_file or args.file
        if search_path:
            search_dir = resolve_project_path(search_path)
        else:
            search_dir = Path.home() / ".claude" / "projects"

        if not search_dir.exists():
            print(f"error: path not found: {search_dir}", file=sys.stderr)
            return 1

        # Collect matching files
        if search_dir.is_file():
            jsonl_files = [search_dir]
        else:
            jsonl_files = sorted(
                search_dir.rglob("*.jsonl"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

        matching_files = _find_matching_files(jsonl_files, args.search_text, config)

        if not args.stream:
            # Filepath-only mode
            for mf in matching_files:
                print(mf)
            return 0
        else:
            # Stream mode — render each matching file
            for mf in matching_files:
                if len(matching_files) > 1:
                    print(
                        formatter.format(
                            [
                                DividerBlock(char="─", width=60),
                                HeaderBlock(
                                    text=str(mf),
                                    icon="📄",
                                    level=2,
                                    styles={Style.INFO},
                                ),
                            ]
                        )
                    )
                with open(mf) as f:
                    process_stream(f, config, formatter, tail_lines=args.lines)
            return 0

    # Resolve file path (used by both directory mode and file mode)
    file_path = args.input_file or args.file

    # Handle directory mode (directory + filters, no --search, no --watch)
    if file_path:
        resolved_path = resolve_project_path(file_path)
        if resolved_path.is_dir():
            jsonl_files = sorted(
                resolved_path.rglob("*.jsonl"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

            for jf in jsonl_files:
                has_output = False
                with open(jf) as f:
                    for line in f:
                        line_stripped = line.strip()
                        if not line_stripped:
                            continue
                        try:
                            data = _json.loads(line_stripped)
                            msg = parse_message(data)
                            if should_show_message(msg, data, config):
                                has_output = True
                                break
                        except _json.JSONDecodeError:
                            continue

                if has_output:
                    print(
                        formatter.format(
                            [
                                DividerBlock(char="─", width=60),
                                HeaderBlock(
                                    text=str(jf),
                                    icon="📄",
                                    level=2,
                                    styles={Style.INFO},
                                ),
                            ]
                        )
                    )
                    with open(jf) as f:
                        process_stream(f, config, formatter, tail_lines=args.lines)

            return 0

    # Determine input source
    input_file: TextIO

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
