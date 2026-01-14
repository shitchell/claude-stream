"""Render block types for flexible output rendering.

This module defines the Style enum and all RenderBlock dataclasses used
as rendering primitives throughout the library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Style(Enum):
    """Style hints for rendering."""

    # Text styles
    BOLD = "bold"
    DIM = "dim"
    ITALIC = "italic"

    # Semantic styles
    ERROR = "error"
    SUCCESS = "success"
    WARNING = "warning"
    INFO = "info"

    # Role styles
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"
    THINKING = "thinking"
    METADATA = "metadata"


@dataclass
class RenderBlock:
    """Base class for rendering primitives."""

    styles: set[Style] = field(default_factory=set)


@dataclass
class HeaderBlock(RenderBlock):
    """A header/title block."""

    text: str = ""
    level: int = 1  # 1 = top level, 2 = subheader, etc.
    icon: str = ""  # Optional prefix icon
    prefix: str = ""  # Optional prefix text (e.g., "Summary:", "Tool:")


@dataclass
class TextBlock(RenderBlock):
    """Plain text content."""

    text: str = ""
    indent: int = 0  # Indentation level


@dataclass
class CodeBlock(RenderBlock):
    """Code or preformatted content."""

    content: str = ""
    language: str = ""
    indent: int = 0


@dataclass
class KeyValueBlock(RenderBlock):
    """Key-value pair."""

    key: str = ""
    value: str = ""
    indent: int = 0


@dataclass
class DividerBlock(RenderBlock):
    """Visual separator."""

    char: str = "─"
    width: int = 40


@dataclass
class ListBlock(RenderBlock):
    """A list of items."""

    items: list[str] = field(default_factory=list)
    indent: int = 0
    bullet: str = "*"


@dataclass
class NestedBlock(RenderBlock):
    """Container for nested blocks."""

    children: list[RenderBlock] = field(default_factory=list)
    indent: int = 0


@dataclass
class SpacerBlock(RenderBlock):
    """Vertical space."""

    lines: int = 1


# Type alias for any render block
AnyBlock = (
    HeaderBlock | TextBlock | CodeBlock | KeyValueBlock |
    DividerBlock | ListBlock | NestedBlock | SpacerBlock
)
