"""Command-line interface for claugs."""

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
from .grouping import parse_group_by_spec, render_grouped, scout_files
from .models import parse_message
from .stream import should_show_message


def encode_path(path: str) -> str:
    """Encode a filesystem path to Claude's .claude/projects/ format.

    Algorithm:
      - [a-zA-Z0-9-] -> preserved
      - All other chars -> max(1, floor(utf8_bytes/2)) dashes

    This means:
      - ASCII special chars (/, ., _, space) -> 1 dash each
      - BMP chars (U+0000-U+FFFF, 1-3 bytes) -> 1 dash each
      - SMP chars (U+10000+, 4 bytes) -> 2 dashes each
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

                    # Text matched -- check time filter if present
                    if not has_time_filter:
                        matching.append(jf)
                        break  # Early termination

                    # Parse timestamp from matching line
                    try:
                        data = _json.loads(line)
                        ts_str = data.get("timestamp", "")
                        if not ts_str:
                            continue  # No timestamp on this line, keep looking
                        msg_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
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


def parse_args():
    """Parse command line arguments using subcommands.

    Returns (parser, args) tuple so the parser can be reused for
    default subcommand injection.
    """

    # -- Shared parent: display/format options --
    display_parent = argparse.ArgumentParser(add_help=False)

    display_parent.add_argument(
        "--format",
        "-F",
        choices=["ansi", "markdown", "plain"],
        default=None,
        help="Output format (default: markdown if CLAUDECODE is set, ansi if TTY, plain if piped)",
    )
    display_parent.add_argument(
        "--timestamp-format",
        dest="timestamp_format",
        default=None,
        help="Timestamp format string (default: %%Y-%%m-%%d %%H:%%M:%%S)",
    )

    # -- Shared parent: filtering options --
    filter_parent = argparse.ArgumentParser(add_help=False)

    filter_parent.add_argument(
        "--show-only",
        action="append",
        dest="show_only_filters",
        metavar="NAME[,NAME]",
        help="Show ONLY these, hide everything else (repeatable, comma-separated)",
    )
    filter_parent.add_argument(
        "--show",
        action="append",
        dest="show_filters",
        metavar="NAME[,NAME]",
        help="Ensure these are visible (repeatable, comma-separated)",
    )
    filter_parent.add_argument(
        "--hide",
        action="append",
        dest="hide_filters",
        metavar="NAME[,NAME]",
        help="Remove these from output (repeatable, comma-separated)",
    )
    filter_parent.add_argument(
        "--compact",
        action="store_true",
        help="Hide non-essential content (thinking, tools, metadata, timestamps, system messages)",
    )
    filter_parent.add_argument(
        "--after",
        "--since",
        dest="after",
        metavar="DATETIME",
        help="Only show messages after this time",
    )
    filter_parent.add_argument(
        "--before",
        "--until",
        dest="before",
        metavar="DATETIME",
        help="Only show messages before this time",
    )
    filter_parent.add_argument(
        "--grep",
        action="append",
        dest="grep_patterns",
        help="Include only messages matching pattern (repeatable)",
    )
    filter_parent.add_argument(
        "--exclude",
        action="append",
        dest="exclude_patterns",
        help="Exclude messages matching pattern (repeatable)",
    )
    filter_parent.add_argument(
        "-n",
        "--lines",
        type=int,
        default=0,
        metavar="N",
        help="Show only last N lines (works with files and watch)",
    )

    # -- Main parser --
    parser = argparse.ArgumentParser(
        prog="claugs",
        description="Parse and prettify Claude Code JSONL session logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Output Formats:
    ansi        Terminal colors (default)
    markdown    Markdown formatting
    plain       Plain text, no formatting

Examples:
    %(prog)s show session.jsonl                         # Render a session
    %(prog)s show session.jsonl -n 20                   # Last 20 lines
    %(prog)s show --latest -n 50                        # Last 50 of most recent
    %(prog)s show --latest --format markdown > out.md
    %(prog)s show --hide timestamps                     # Hide timestamps
    %(prog)s show --show metadata                       # Show metadata
    %(prog)s show --show-only user,assistant             # Only user + assistant
    %(prog)s show --compact                             # Hide non-essential content
    %(prog)s show --list-filters                        # Show available filters
    %(prog)s show --find "error" -l                   # List matching filepaths
    %(prog)s show --find "bug" --since "yesterday" .  # Search recent sessions
    %(prog)s show --since "today" ~/myproject            # Today's messages
    %(prog)s show --since "2h ago" . --group-by time:%%H # Interleave by hour
    %(prog)s watch ~/.claude/projects/                  # Watch all sessions
    %(prog)s watch .                                    # Watch current project
    %(prog)s watch ~/myproject -n 10                    # Watch with context
        """,
    )

    # Version flags (on the main parser, before subcommands)
    from importlib.metadata import version as pkg_version

    from .models import LAST_VERIFIED_CLAUDE_CODE_VERSION

    try:
        claugs_version = pkg_version("claugs")
    except Exception:
        claugs_version = "unknown"

    parser.add_argument(
        "--version",
        action="version",
        version=f"claugs {claugs_version}",
    )
    parser.add_argument(
        "--version-cc",
        action="version",
        version=f"Last verified against Claude Code {LAST_VERIFIED_CLAUDE_CODE_VERSION}",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # -- show subcommand --
    show_parser = subparsers.add_parser(
        "show",
        parents=[display_parent, filter_parent],
        help="Render sessions with filtering (default)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Render sessions with filtering. This is the default subcommand.",
    )

    # Positional source argument
    show_parser.add_argument(
        "source", nargs="?", type=Path, help="JSONL filepath or directory"
    )

    # Source options (mutually exclusive)
    source_group = show_parser.add_mutually_exclusive_group()
    source_group.add_argument(
        "-f", "--file", type=Path, help="Read from JSONL filepath"
    )
    source_group.add_argument("--session", help="Find session by UUID")
    source_group.add_argument(
        "--latest", action="store_true", help="Most recent session"
    )

    # Show-specific options
    show_parser.add_argument(
        "--find",
        dest="search_text",
        metavar="TEXT",
        help="Only files containing this text",
    )
    show_parser.add_argument(
        "-l",
        "--filepaths-only",
        action="store_true",
        help="Print matching filepaths instead of rendering",
    )
    show_parser.add_argument(
        "--group-by",
        dest="group_by",
        metavar="SPEC",
        help="Group by 'project' and/or 'time:<strftime>'",
    )
    show_parser.add_argument(
        "--list-filters",
        action="store_true",
        help="Show available filter names and exit",
    )

    # -- watch subcommand --
    watch_parser = subparsers.add_parser(
        "watch",
        parents=[display_parent, filter_parent],
        help="Monitor sessions for new messages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Watch a file or directory for new JSONL messages (like tail -f).",
    )
    watch_parser.add_argument(
        "path", type=Path, help="JSONL filepath or directory to watch"
    )

    args = parser.parse_args()
    return parser, args


def _build_filters(args: argparse.Namespace) -> "FilterConfig":
    """Build a FilterConfig from parsed arguments."""
    from .models import FilterConfig

    show_only: set[str] = set()
    shown: set[str] = set()
    hidden: set[str] = set()

    if getattr(args, "show_only_filters", None):
        for spec in args.show_only_filters:
            show_only.update(name.strip() for name in spec.split(","))
    if args.compact:
        hidden.update(
            {
                "thinking",
                "tools",
                "metadata",
                "timestamps",
                "system",
                "summary",
                "queue-operation",
                "result",
            }
        )
    if getattr(args, "hide_filters", None):
        for spec in args.hide_filters:
            hidden.update(name.strip() for name in spec.split(","))
    if getattr(args, "show_filters", None):
        for spec in args.show_filters:
            shown.update(name.strip() for name in spec.split(","))

    # Warn on unknown filter names
    from .models import get_filter_registry

    known = set(get_filter_registry().keys())
    for name in show_only | shown | hidden:
        if name not in known:
            print(f"warning: unknown filter: {name}", file=sys.stderr)

    return FilterConfig(show_only=show_only, shown=shown, hidden=hidden)


def _build_config(args: argparse.Namespace) -> RenderConfig:
    """Build a RenderConfig from parsed arguments."""
    filters = _build_filters(args)
    config = RenderConfig(filters=filters)
    if args.timestamp_format is not None:
        config.timestamp_format = args.timestamp_format
    if args.before:
        config.before = parse_datetime(args.before)
    if args.after:
        config.after = parse_datetime(args.after)
    if args.grep_patterns:
        config.grep_patterns = args.grep_patterns
    if args.exclude_patterns:
        config.exclude_patterns = args.exclude_patterns
    return config


def _print_filter_list() -> None:
    """Print available filter names and exit."""
    from .models import get_filter_registry

    registry = get_filter_registry()

    print("Available filter names for --show, --hide, --show-only:\n")

    categories = {
        "type": "Message types",
        "subtype": "Subtypes",
        "content": "Content visibility",
    }
    for cat_key, cat_label in categories.items():
        items = {k: v for k, v in registry.items() if v["category"] == cat_key}
        if not items:
            continue
        print(f"{cat_label}:")
        for name, info in items.items():
            default = "hidden" if not info["default_visible"] else "shown"
            print(f"  {name:24s} {info['description']} (default: {default})")
        print()

    defaults = sorted(k for k, v in registry.items() if not v["default_visible"])
    if defaults:
        print(f"Defaults hidden: {', '.join(defaults)}")

    from .models import LAST_VERIFIED_CLAUDE_CODE_VERSION

    print(
        f"\nMessage types verified against Claude Code v{LAST_VERIFIED_CLAUDE_CODE_VERSION}"
    )


def _build_formatter(args: argparse.Namespace) -> Formatter:
    """Select the output formatter based on args and environment."""
    # Priority: explicit --format > CLAUDECODE env var > TTY detection
    output_format = args.format
    if output_format is None:
        if os.environ.get("CLAUDECODE"):
            output_format = "markdown"
        elif sys.stdout.isatty():
            output_format = "ansi"
        else:
            output_format = "plain"

    if output_format == "markdown":
        return MarkdownFormatter()
    elif output_format == "plain":
        return PlainFormatter()
    else:
        return ANSIFormatter()


def _collect_jsonl_files(directory: Path) -> list[Path]:
    """Collect JSONL files from a directory, sorted by mtime (newest first)."""
    return sorted(
        directory.rglob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _render_files(
    files: list[Path],
    config: RenderConfig,
    formatter: Formatter,
    tail_lines: int = 0,
    group_config=None,
) -> None:
    """Render multiple JSONL files, with optional grouping."""
    if group_config:
        handles = scout_files(files, config, tail_lines=tail_lines)
        render_grouped(handles, config, group_config, formatter)
    else:
        for jf in files:
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
                if len(files) > 1:
                    print(
                        formatter.format(
                            [
                                DividerBlock(char="\u2500", width=60),
                                HeaderBlock(
                                    text=str(jf),
                                    icon="\U0001f4c4",
                                    level=2,
                                    styles={Style.INFO},
                                ),
                            ]
                        )
                    )
                with open(jf) as f:
                    process_stream(f, config, formatter, tail_lines=tail_lines)


def handle_show(
    args: argparse.Namespace, config: RenderConfig, formatter: Formatter
) -> int:
    """Handle the 'show' subcommand."""

    if getattr(args, "list_filters", False):
        _print_filter_list()
        return 0

    # Parse --group-by
    group_config = None
    if args.group_by:
        try:
            group_config = parse_group_by_spec(args.group_by)
            config.group_by = group_config
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1

    # Check for source + --file conflict
    if args.source and args.file:
        print(
            "error: cannot specify both positional source and --file", file=sys.stderr
        )
        return 1

    # Resolve the source path
    file_path = args.source or args.file
    session_path: Path | None = None

    # Resolve --session or --latest to a file path
    if args.session:
        session_path = find_session_file(session_id=args.session)
        if not session_path:
            print(f"error: session not found: {args.session}", file=sys.stderr)
            return 1
    elif args.latest:
        session_path = find_session_file(latest=True)
        if not session_path:
            print("error: no sessions found", file=sys.stderr)
            return 1

    # --filepaths-only with stdin is an error
    if args.filepaths_only and not file_path and not session_path:
        if not sys.stdin.isatty():
            print("error: --filepaths-only cannot be used with stdin", file=sys.stderr)
            return 1

    # Determine what we're working with
    if session_path:
        # Working with a specific session file
        target_files = [session_path]

        # Apply --find filter if set
        if args.search_text:
            target_files = _find_matching_files(target_files, args.search_text, config)
            if not target_files:
                return 0  # No match, silent exit

        if args.filepaths_only:
            for f in target_files:
                print(f)
            return 0

        # Render the session
        with open(target_files[0]) as f:
            process_stream(f, config, formatter, tail_lines=args.lines)
        return 0

    if file_path:
        resolved_path = resolve_project_path(file_path)

        if resolved_path.is_dir():
            # Directory mode: collect all JSONL files
            jsonl_files = _collect_jsonl_files(resolved_path)

            # Apply --find filter if set
            if args.search_text:
                jsonl_files = _find_matching_files(
                    jsonl_files, args.search_text, config
                )

            if args.filepaths_only:
                for jf in jsonl_files:
                    print(jf)
                return 0

            # Render files
            _render_files(
                jsonl_files,
                config,
                formatter,
                tail_lines=args.lines,
                group_config=group_config,
            )
            return 0

        else:
            # Single file mode
            if not resolved_path.exists():
                print(f"error: file not found: {file_path}", file=sys.stderr)
                return 1

            target_files = [resolved_path]

            # Apply --find filter if set
            if args.search_text:
                target_files = _find_matching_files(
                    target_files, args.search_text, config
                )
                if not target_files:
                    return 0  # No match, silent exit

            if args.filepaths_only:
                for f in target_files:
                    print(f)
                return 0

            with open(target_files[0]) as f:
                process_stream(f, config, formatter, tail_lines=args.lines)
            return 0

    # No file_path and no session_path -- check for --find without explicit source
    if args.search_text:
        search_dir = Path.home() / ".claude" / "projects"
        if not search_dir.exists():
            print(f"error: path not found: {search_dir}", file=sys.stderr)
            return 1

        jsonl_files = _collect_jsonl_files(search_dir)
        matching_files = _find_matching_files(jsonl_files, args.search_text, config)

        if args.filepaths_only:
            for mf in matching_files:
                print(mf)
            return 0

        # Render matching files
        _render_files(
            matching_files,
            config,
            formatter,
            tail_lines=args.lines,
            group_config=group_config,
        )
        return 0

    # Try stdin
    if not sys.stdin.isatty():
        process_stream(sys.stdin, config, formatter, tail_lines=args.lines)
        return 0

    # No input source
    print("error: no input source specified", file=sys.stderr)
    return 1


def handle_watch(
    args: argparse.Namespace, config: RenderConfig, formatter: Formatter
) -> int:
    """Handle the 'watch' subcommand."""
    watch_target = resolve_project_path(args.path)

    if not watch_target.exists():
        print(f"error: path not found: {args.path}", file=sys.stderr)
        # If we tried to resolve to a Claude path, mention it
        if watch_target != args.path.resolve():
            print(f"  (looked for Claude project at: {watch_target})", file=sys.stderr)
        return 1

    # Show resolved path if different from input
    if watch_target != args.path.resolve():
        print(f"watching: {watch_target}", file=sys.stderr)

    watch_path(watch_target, config, formatter, recursive=True, tail_lines=args.lines)
    return 0


def main() -> int:
    """Main entry point."""

    parser, args = parse_args()

    # Parse --before/--after and build config
    try:
        config = _build_config(args)
    except ValueError as e:
        # parse_datetime raises ValueError for bad date strings
        print(f"error: cannot parse date: {e}", file=sys.stderr)
        return 1

    formatter = _build_formatter(args)

    # Dispatch to handler
    if args.command == "show":
        return handle_show(args, config, formatter)
    elif args.command == "watch":
        return handle_watch(args, config, formatter)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    exit_code: int = 0
    try:
        exit_code = main()
    except KeyboardInterrupt:
        print("\nexiting", file=sys.stderr)

    sys.exit(exit_code)
