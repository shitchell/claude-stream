"""Stream processing functions for JSONL data.

This module contains the filtering logic (should_show_message) and
the main stream processing function (process_stream).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any, TextIO

from .blocks import Style, TextBlock
from .formatters import Formatter
from .models import (
    BaseMessage,
    UserMessage,
    RenderConfig,
    get_filter_registry,
    parse_message,
)


_subtype_names_cache: set[str] | None = None


def _get_subtype_names() -> set[str]:
    """Get the set of known subtype names from the registry."""
    global _subtype_names_cache
    if _subtype_names_cache is None:
        _subtype_names_cache = {
            name
            for name, info in get_filter_registry().items()
            if info["category"] == "subtype"
        }
    return _subtype_names_cache


def should_show_message(
    msg: BaseMessage, data: dict[str, Any], config: RenderConfig
) -> bool:
    """Determine if a message should be displayed based on filters."""
    filters = config.filters

    # Check message type visibility
    if not filters.is_visible(msg.type):
        return False

    # Check subtype visibility — subtypes only block a message when
    # they are explicitly hidden or when show_only explicitly names subtypes.
    # If show_only only contains type-level names (e.g. "user"), subtypes
    # (e.g. "user-input") pass through.
    _SUBTYPE_NAMES = _get_subtype_names()
    _show_only_has_subtypes = bool(filters.show_only & _SUBTYPE_NAMES)

    if isinstance(msg, UserMessage):
        subtype = msg.get_subtype()
        # Explicit hide (unless also explicitly shown)
        if subtype in filters.hidden and subtype not in filters.shown:
            return False
        # If show_only explicitly names subtypes, enforce the whitelist
        if _show_only_has_subtypes and subtype not in filters.show_only:
            if subtype not in filters.shown:
                return False
        # Tool-result / subagent-result also require "tools" visibility
        if subtype in ("tool-result", "subagent-result") and not filters.is_visible(
            "tools"
        ):
            return False
    else:
        raw_subtype = getattr(msg, "subtype", "")
        if raw_subtype:
            normalized = raw_subtype.replace("_", "-")
            if normalized in filters.hidden and normalized not in filters.shown:
                return False
            if _show_only_has_subtypes and normalized not in filters.show_only:
                if normalized not in filters.shown:
                    return False

    # Check tool name visibility — only blocked if explicitly hidden
    content = data.get("message", {}).get("content", [])
    if isinstance(content, list):
        tool_names = {
            item.get("name")
            for item in content
            if isinstance(item, dict) and item.get("type") == "tool_use"
        }
        if tool_names:
            for tool_name in tool_names:
                if tool_name in filters.hidden and tool_name not in filters.shown:
                    return False

    # Timestamp filtering
    if config.before or config.after:
        ts_str = data.get("timestamp", "")
        if ts_str:
            try:
                msg_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if msg_dt.tzinfo is None:
                    msg_dt = msg_dt.replace(tzinfo=timezone.utc)
                if config.after and msg_dt < config.after:
                    return False
                if config.before and msg_dt > config.before:
                    return False
            except (ValueError, OSError):
                pass

    # Grep/exclude
    if config.grep_patterns:
        msg_str = json.dumps(data)
        if not any(pattern in msg_str for pattern in config.grep_patterns):
            return False
    if config.exclude_patterns:
        msg_str = json.dumps(data)
        if any(pattern in msg_str for pattern in config.exclude_patterns):
            return False

    return True


def process_stream(
    input_file: TextIO, config: RenderConfig, formatter: Formatter, tail_lines: int = 0
) -> None:
    """Process JSONL stream and output formatted messages.

    Args:
        input_file: File-like object to read JSONL from
        config: Rendering configuration
        formatter: Output formatter
        tail_lines: If > 0, only process the last N lines
    """
    # If tail_lines specified, read all and take last N
    if tail_lines > 0:
        all_lines = input_file.readlines()
        lines_to_process = all_lines[-tail_lines:]
        start_line_num = max(0, len(all_lines) - tail_lines)
    else:
        lines_to_process = input_file
        start_line_num = 0

    line_num = start_line_num

    for line in lines_to_process:
        line_num += 1
        line = line.strip()

        if not line:
            continue

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            print(f"warning: invalid JSON on line {line_num}", file=sys.stderr)
            continue

        msg = parse_message(data)

        if not should_show_message(msg, data, config):
            continue

        # Add line number prefix if enabled
        blocks = msg.render(config)

        if config.filters.is_visible("line-numbers"):
            blocks.insert(0, TextBlock(text=f"[{line_num}]", styles={Style.METADATA}))

        output = formatter.format(blocks)
        print(output)
