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
    """Render files interleaved by time bucket."""
    raise NotImplementedError("Time interleaving not yet implemented")
