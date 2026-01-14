"""Output formatters for converting RenderBlocks to various formats.

This module contains the Formatter base class and implementations for
ANSI terminal colors, Markdown, and plain text output.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .blocks import (
    CodeBlock,
    DividerBlock,
    HeaderBlock,
    KeyValueBlock,
    ListBlock,
    NestedBlock,
    RenderBlock,
    SpacerBlock,
    Style,
    TextBlock,
)


class Formatter(ABC):
    """Base class for output formatters."""

    def _indent(self, text: str, level: int) -> str:
        """Add indentation to text."""
        if level <= 0:
            return text
        prefix = "  " * level
        return "\n".join(prefix + line for line in text.split("\n"))

    def format(self, blocks: list[RenderBlock]) -> str:
        """Convert render blocks to formatted string."""
        lines: list[str] = []
        for block in blocks:
            formatted = self.format_block(block)
            if formatted:
                lines.append(formatted)
        return "\n".join(lines)

    def format_block(self, block: RenderBlock) -> str:
        """Format a single block using type dispatch."""
        handler = self._block_handlers.get(type(block))
        if handler:
            return handler(self, block)
        return ""

    # Subclasses populate this with {BlockType: handler_method}
    _block_handlers: dict[type, Any] = {}

    # Common handlers that can be shared
    def _format_nested(self, block: NestedBlock) -> str:
        inner = self.format(block.children)
        return self._indent(inner, block.indent)

    def _format_spacer(self, block: SpacerBlock) -> str:
        return "\n" * (block.lines - 1)  # -1 because join adds one


class ANSIFormatter(Formatter):
    """Format output with ANSI terminal colors."""

    # ANSI codes
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"

    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"

    STYLE_MAP: dict[Style, str] = {
        Style.BOLD: BOLD,
        Style.DIM: DIM,
        Style.ITALIC: ITALIC,
        Style.ERROR: RED,
        Style.SUCCESS: GREEN,
        Style.WARNING: YELLOW,
        Style.INFO: CYAN,
        Style.USER: GREEN,
        Style.ASSISTANT: "",  # Default color
        Style.SYSTEM: BLUE,
        Style.TOOL: YELLOW,
        Style.THINKING: DIM + ITALIC,
        Style.METADATA: DIM,
    }

    def _apply_styles(self, text: str, styles: set[Style]) -> str:
        """Wrap text with ANSI codes for given styles."""
        if not styles:
            return text

        codes = "".join(self.STYLE_MAP.get(s, "") for s in styles)
        if codes:
            return f"{codes}{text}{self.RESET}"
        return text

    def _format_header(self, block: HeaderBlock) -> str:
        parts = []
        if block.icon:
            parts.append(block.icon)
        if block.prefix:
            parts.append(block.prefix)
        parts.append(block.text)
        text = " ".join(parts)
        return self._apply_styles(text, block.styles | {Style.BOLD})

    def _format_text(self, block: TextBlock) -> str:
        styled = self._apply_styles(block.text, block.styles)
        return self._indent(styled, block.indent)

    def _format_code(self, block: CodeBlock) -> str:
        styled = self._apply_styles(block.content, block.styles)
        return self._indent(styled, block.indent)

    def _format_keyvalue(self, block: KeyValueBlock) -> str:
        key_styled = self._apply_styles(f"{block.key}:", {Style.BOLD})
        value_styled = self._apply_styles(block.value, block.styles)
        return self._indent(f"{key_styled} {value_styled}", block.indent)

    def _format_divider(self, block: DividerBlock) -> str:
        line = block.char * block.width
        return self._apply_styles(line, block.styles)

    def _format_list(self, block: ListBlock) -> str:
        lines = [f"{block.bullet} {item}" for item in block.items]
        text = "\n".join(lines)
        styled = self._apply_styles(text, block.styles)
        return self._indent(styled, block.indent)

    _block_handlers = {
        HeaderBlock: _format_header,
        TextBlock: _format_text,
        CodeBlock: _format_code,
        KeyValueBlock: _format_keyvalue,
        DividerBlock: _format_divider,
        ListBlock: _format_list,
        NestedBlock: Formatter._format_nested,
        SpacerBlock: Formatter._format_spacer,
    }


class MarkdownFormatter(Formatter):
    """Format output as Markdown."""

    def _apply_styles(self, text: str, styles: set[Style]) -> str:
        """Apply markdown formatting for styles."""
        if Style.BOLD in styles:
            text = f"**{text}**"
        if Style.ITALIC in styles or Style.THINKING in styles:
            text = f"*{text}*"
        # DIM and colors don't have direct markdown equivalents
        return text

    def _format_header(self, block: HeaderBlock) -> str:
        hashes = "#" * min(block.level, 6)
        # For level 1 (document title), use clean text only
        if block.level == 1:
            return f"{hashes} {block.text}"
        # For other levels, include icon and prefix
        parts = []
        if block.icon:
            parts.append(block.icon)
        if block.prefix:
            parts.append(block.prefix)
        parts.append(block.text)
        return f"{hashes} {' '.join(parts)}"

    def _format_text(self, block: TextBlock) -> str:
        styled = self._apply_styles(block.text, block.styles)
        return self._indent(styled, block.indent)

    def _format_code(self, block: CodeBlock) -> str:
        lang = block.language or ""
        content = f"```{lang}\n{block.content}\n```"
        return self._indent(content, block.indent)

    def _format_keyvalue(self, block: KeyValueBlock) -> str:
        return self._indent(f"**{block.key}:** {block.value}", block.indent)

    def _format_divider(self, block: DividerBlock) -> str:
        return "---"

    def _format_list(self, block: ListBlock) -> str:
        lines = [f"- {item}" for item in block.items]
        return self._indent("\n".join(lines), block.indent)

    _block_handlers = {
        HeaderBlock: _format_header,
        TextBlock: _format_text,
        CodeBlock: _format_code,
        KeyValueBlock: _format_keyvalue,
        DividerBlock: _format_divider,
        ListBlock: _format_list,
        NestedBlock: Formatter._format_nested,
        SpacerBlock: Formatter._format_spacer,
    }


class PlainFormatter(Formatter):
    """Format output as plain text (no styling)."""

    def _format_header(self, block: HeaderBlock) -> str:
        parts = []
        if block.prefix:
            parts.append(block.prefix)
        parts.append(block.text)
        return " ".join(parts)

    def _format_text(self, block: TextBlock) -> str:
        return self._indent(block.text, block.indent)

    def _format_code(self, block: CodeBlock) -> str:
        return self._indent(block.content, block.indent)

    def _format_keyvalue(self, block: KeyValueBlock) -> str:
        return self._indent(f"{block.key}: {block.value}", block.indent)

    def _format_divider(self, block: DividerBlock) -> str:
        return block.char * block.width

    def _format_list(self, block: ListBlock) -> str:
        lines = [f"{block.bullet} {item}" for item in block.items]
        return self._indent("\n".join(lines), block.indent)

    _block_handlers = {
        HeaderBlock: _format_header,
        TextBlock: _format_text,
        CodeBlock: _format_code,
        KeyValueBlock: _format_keyvalue,
        DividerBlock: _format_divider,
        ListBlock: _format_list,
        NestedBlock: Formatter._format_nested,
        SpacerBlock: Formatter._format_spacer,
    }
