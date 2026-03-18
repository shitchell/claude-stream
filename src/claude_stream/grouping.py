"""Grouping logic for multi-file rendering.

This module handles --group-by parsing, file scouting (pass 1),
and interleaved rendering (pass 2).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import groupby as itertools_groupby
from pathlib import Path
from typing import TextIO

from .blocks import DividerBlock, HeaderBlock, Style
from .formatters import Formatter
from .models import GroupByConfig, RenderConfig
from .stream import process_stream, should_show_message


def parse_group_by_spec(spec: str) -> GroupByConfig:
    """Parse a --group-by spec string into GroupByConfig.

    Args:
        spec: Comma-separated grouping keys (e.g., "project,time:%Y%m%d%H")

    Returns:
        Parsed GroupByConfig.

    Raises:
        ValueError: If the spec is invalid.
    """
    config = GroupByConfig()
    seen_project = False
    seen_time = False
    project_index = -1
    time_index = -1

    keys = [k.strip() for k in spec.split(",")]

    for i, key in enumerate(keys):
        if key == "project":
            if not seen_project:
                seen_project = True
                project_index = i
            config.by_project = True

        elif key.startswith("time:"):
            if seen_time:
                raise ValueError("only one time: group-by key is allowed")
            pattern = key[5:]  # strip "time:" prefix
            if not pattern:
                raise ValueError(
                    f"invalid group-by key: {key!r}. "
                    "Expected 'project' or 'time:<strftime>'"
                )
            # Validate strftime pattern: must contain at least one
            # directive that actually formats (output != input).
            # CPython on Linux silently passes unknown directives like %Q.
            test_result = datetime.now().strftime(pattern)
            if test_result == pattern:
                raise ValueError(f"invalid strftime pattern in group-by: {pattern!r}")
            seen_time = True
            time_index = i
            config.time_format = pattern

        else:
            raise ValueError(
                f"invalid group-by key: {key!r}. "
                "Expected 'project' or 'time:<strftime>'"
            )

    # Determine ordering
    if seen_project and seen_time:
        config.project_first = project_index < time_index
        if not config.project_first:
            raise ValueError(
                "time-then-project ordering is not yet supported. "
                "Use 'project,time:<fmt>' instead."
            )

    return config


# =============================================================================
# Pass 1: File scouting
# =============================================================================


@dataclass
class FileHandle:
    """A JSONL file with a starting byte offset and project name."""

    path: Path
    offset: int = 0
    project: str = ""


def _parse_timestamp(ts_str: str) -> datetime | None:
    """Parse an ISO 8601 timestamp string to a timezone-aware datetime."""
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, OSError):
        return None


def _extract_project(path: Path) -> str:
    """Extract project name from a JSONL file path."""
    return path.parent.name


def scout_files(
    jsonl_files: list[Path],
    config: RenderConfig,
    tail_lines: int = 0,
) -> list[FileHandle]:
    """Pass 1: Scout files to find starting offsets."""
    has_time_filter = config.before is not None or config.after is not None
    handles: list[FileHandle] = []

    for path in jsonl_files:
        try:
            offset = _scout_single_file(path, config, has_time_filter, tail_lines)
            if offset is not None:
                handles.append(
                    FileHandle(path=path, offset=offset, project=_extract_project(path))
                )
        except (IOError, OSError) as e:
            print(f"warning: cannot read {path}: {e}", file=sys.stderr)

    return handles


def _scout_single_file(
    path: Path,
    config: RenderConfig,
    has_time_filter: bool,
    tail_lines: int,
) -> int | None:
    """Scout a single file, returning byte offset or None to skip."""
    time_offset: int = 0
    tail_offset: int = 0

    with open(path, "r") as f:
        if has_time_filter:
            found = False
            while True:
                line_start = f.tell()
                line = f.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    ts = _parse_timestamp(data.get("timestamp", ""))
                    if ts is None:
                        continue
                    if config.after and ts < config.after:
                        continue
                    if config.before and ts > config.before:
                        break
                    time_offset = line_start
                    found = True
                    break
                except json.JSONDecodeError:
                    continue

            if not found:
                return None

        if tail_lines > 0:
            f.seek(0)
            all_positions: list[int] = []
            while True:
                pos = f.tell()
                line = f.readline()
                if not line:
                    break
                if line.strip():
                    all_positions.append(pos)

            if not all_positions:
                return None

            start_idx = max(0, len(all_positions) - tail_lines)
            tail_offset = all_positions[start_idx]

    offset = max(time_offset, tail_offset)

    if not has_time_filter and tail_lines <= 0:
        if path.stat().st_size == 0:
            return None

    return offset


# =============================================================================
# Bucket key computation
# =============================================================================


def compute_bucket_key(dt: datetime, time_format: str) -> str:
    """Compute the bucket key for a datetime using the strftime pattern.

    Converts to local timezone before formatting.
    """
    return dt.astimezone().strftime(time_format)


# =============================================================================
# Pass 2: Grouped rendering
# =============================================================================


def render_grouped(
    handles: list[FileHandle],
    config: RenderConfig,
    group_config: GroupByConfig,
    formatter: Formatter,
) -> None:
    """Pass 2: Render files with grouping.

    Callers must pre-scout files via scout_files() which handles tail_lines
    and time-filter offsets.
    """
    if group_config.time_format is not None:
        _render_time_interleaved(handles, config, group_config, formatter)
    elif group_config.by_project:
        _render_project_grouped(handles, config, formatter)
    else:
        _render_sequential(handles, config, formatter)


def _render_sequential(
    handles: list[FileHandle],
    config: RenderConfig,
    formatter: Formatter,
) -> None:
    """Render files sequentially with file headers."""
    show_headers = len(handles) > 1

    for handle in handles:
        if show_headers:
            print(
                formatter.format(
                    [
                        DividerBlock(char="─", width=60),
                        HeaderBlock(
                            text=str(handle.path),
                            icon="📄",
                            level=2,
                            styles={Style.INFO},
                        ),
                    ]
                )
            )
        with open(handle.path, "r") as f:
            f.seek(handle.offset)
            process_stream(f, config, formatter)


def _render_project_grouped(
    handles: list[FileHandle],
    config: RenderConfig,
    formatter: Formatter,
) -> None:
    """Render files grouped by project."""
    sorted_handles = sorted(handles, key=lambda h: h.project)

    for project, group in itertools_groupby(sorted_handles, key=lambda h: h.project):
        print(
            formatter.format(
                [
                    DividerBlock(char="─", width=60),
                    HeaderBlock(
                        text=f"Project: {project}",
                        icon="──",
                        level=2,
                        styles={Style.SYSTEM},
                    ),
                ]
            )
        )

        for handle in group:
            print(
                formatter.format(
                    [
                        HeaderBlock(
                            text=str(handle.path),
                            icon="📄",
                            level=2,
                            styles={Style.INFO},
                        ),
                    ]
                )
            )
            with open(handle.path, "r") as f:
                f.seek(handle.offset)
                process_stream(f, config, formatter)


def _render_time_interleaved(
    handles: list[FileHandle],
    config: RenderConfig,
    group_config: GroupByConfig,
    formatter: Formatter,
) -> None:
    """Render files interleaved by time bucket.

    If project_first is set and by_project is True, groups by project first,
    then interleaves by time within each project group. Otherwise, interleaves
    all files together by time.
    """
    if group_config.by_project and group_config.project_first:
        sorted_handles = sorted(handles, key=lambda h: h.project)
        for project, group in itertools_groupby(
            sorted_handles, key=lambda h: h.project
        ):
            print(
                formatter.format(
                    [
                        DividerBlock(char="─", width=60),
                        HeaderBlock(
                            text=f"Project: {project}",
                            icon="──",
                            level=2,
                            styles={Style.SYSTEM},
                        ),
                    ]
                )
            )
            _interleave_by_time(
                list(group), config, group_config.time_format, formatter
            )
    else:
        _interleave_by_time(handles, config, group_config.time_format, formatter)


@dataclass
class _OpenFile:
    """An open file with a peeked line and current bucket key."""

    handle: FileHandle
    file: TextIO
    peeked_line: str | None = None
    peeked_data: dict | None = None
    peeked_timestamp: datetime | None = None
    current_bucket: str | None = None
    exhausted: bool = False


def _peek_next(
    of: _OpenFile,
    config: RenderConfig,
    time_format: str,
) -> None:
    """Read the next valid JSONL line from an open file.

    Updates of.peeked_line, peeked_data, peeked_timestamp, and current_bucket.
    If a line has no timestamp, the bucket is inherited (current_bucket unchanged).
    Marks exhausted=True when EOF is reached or --before cutoff is exceeded.
    """
    while True:
        line = of.file.readline()
        if not line:
            of.peeked_line = None
            of.peeked_data = None
            of.peeked_timestamp = None
            of.exhausted = True
            return

        line = line.strip()
        if not line:
            continue

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Check --before cutoff
        ts_str = data.get("timestamp", "")
        ts = _parse_timestamp(ts_str)

        if ts is not None and config.before and ts > config.before:
            of.peeked_line = None
            of.peeked_data = None
            of.peeked_timestamp = None
            of.exhausted = True
            return

        of.peeked_line = line
        of.peeked_data = data
        of.peeked_timestamp = ts

        # Update bucket: only change if we have a timestamp
        if ts is not None:
            of.current_bucket = compute_bucket_key(ts, time_format)

        return


def _interleave_by_time(
    handles: list[FileHandle],
    config: RenderConfig,
    time_format: str,
    formatter: Formatter,
) -> None:
    """Core time-interleaving loop.

    Algorithm:
    1. Open all files, seek to offset, peek first line to get initial bucket
    2. Find the lowest bucket key among active files
    3. Collect files in that bucket, sorted by first timestamp
    4. For each file: print header, render messages until bucket changes
    5. Close exhausted files, repeat
    """
    from .models import parse_message

    if len(handles) > 500:
        print(
            f"warning: opening {len(handles)} files simultaneously",
            file=sys.stderr,
        )

    # Open all files and peek at their first line
    active: list[_OpenFile] = []
    for handle in handles:
        try:
            f = open(handle.path, "r")
            f.seek(handle.offset)
            of = _OpenFile(handle=handle, file=f)
            _peek_next(of, config, time_format)
            if not of.exhausted:
                active.append(of)
            else:
                f.close()
        except (IOError, OSError) as e:
            print(f"warning: cannot read {handle.path}: {e}", file=sys.stderr)

    try:
        while active:
            # Find the lowest bucket key
            min_bucket = min(
                (of.current_bucket for of in active if of.current_bucket is not None),
                default=None,
            )

            # If no file has a bucket yet (all have None), just render them all
            if min_bucket is None:
                for of in active:
                    _render_of_remaining(of, config, time_format, formatter)
                break

            # Collect files that are in this bucket
            in_bucket: list[_OpenFile] = []
            not_in_bucket: list[_OpenFile] = []
            for of in active:
                if of.current_bucket == min_bucket or of.current_bucket is None:
                    in_bucket.append(of)
                else:
                    not_in_bucket.append(of)

            # Sort files in this bucket by their first peeked timestamp
            in_bucket.sort(
                key=lambda of: of.peeked_timestamp
                or datetime.max.replace(tzinfo=timezone.utc)
            )

            # Render each file's messages in this bucket
            for of in in_bucket:
                # Print file + bucket header
                print(
                    formatter.format(
                        [
                            HeaderBlock(
                                text=str(of.handle.path),
                                icon="📄",
                                level=2,
                                styles={Style.INFO},
                                suffix=f"[{min_bucket}]",
                            ),
                        ]
                    )
                )

                # Render messages until bucket changes or file exhausted
                while not of.exhausted and (
                    of.current_bucket == min_bucket or of.current_bucket is None
                ):
                    if of.peeked_data is not None:
                        msg = parse_message(of.peeked_data)
                        if should_show_message(msg, of.peeked_data, config):
                            blocks = msg.render(config)
                            output = formatter.format(blocks)
                            print(output)

                    _peek_next(of, config, time_format)

            # Remove exhausted files
            still_active: list[_OpenFile] = []
            for of in active:
                if of.exhausted:
                    of.file.close()
                else:
                    still_active.append(of)
            active = still_active

    finally:
        # Clean up any remaining open files
        for of in active:
            of.file.close()


def _render_of_remaining(
    of: _OpenFile,
    config: RenderConfig,
    time_format: str,
    formatter: Formatter,
) -> None:
    """Render all remaining messages from an open file."""
    from .models import parse_message

    while not of.exhausted:
        if of.peeked_data is not None:
            msg = parse_message(of.peeked_data)
            if should_show_message(msg, of.peeked_data, config):
                blocks = msg.render(config)
                output = formatter.format(blocks)
                print(output)
        _peek_next(of, config, time_format)
