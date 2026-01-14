"""Stream processing functions for JSONL data.

This module contains the filtering logic (should_show_message) and
the main stream processing function (process_stream).
"""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from .blocks import Style, TextBlock
from .formatters import Formatter
from .models import BaseMessage, RenderConfig, parse_message


def should_show_message(msg: BaseMessage, data: dict[str, Any], config: RenderConfig) -> bool:
    """Determine if a message should be displayed based on filters."""

    # Check type filter
    if config.show_types and msg.type not in config.show_types:
        return False

    # Check subtype filter
    if config.show_subtypes:
        subtype = data.get("subtype")
        if msg.type == "assistant":
            content_types = set()
            for item in data.get("message", {}).get("content", []):
                content_types.add(item.get("type"))
            if not config.show_subtypes.intersection(content_types):
                return False
        elif subtype and subtype not in config.show_subtypes:
            return False

    # Check tool filter
    if config.show_tools:
        tools_in_msg = set()
        for item in data.get("message", {}).get("content", []):
            if item.get("type") == "tool_use":
                tools_in_msg.add(item.get("name"))
        if not tools_in_msg:
            return False
        if not config.show_tools.intersection(tools_in_msg):
            return False

    # Check grep patterns
    if config.grep_patterns:
        msg_str = json.dumps(data)
        if not any(pattern in msg_str for pattern in config.grep_patterns):
            return False

    # Check exclude patterns
    if config.exclude_patterns:
        msg_str = json.dumps(data)
        if any(pattern in msg_str for pattern in config.exclude_patterns):
            return False

    return True


def process_stream(
    input_file: TextIO,
    config: RenderConfig,
    formatter: Formatter
) -> None:
    """Process JSONL stream and output formatted messages."""

    line_num = 0

    for line in input_file:
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

        if config.show_line_numbers:
            blocks.insert(0, TextBlock(
                text=f"[{line_num}]",
                styles={Style.METADATA}
            ))

        output = formatter.format(blocks)
        print(output)
