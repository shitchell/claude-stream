"""
Parse and prettify Claude Code JSONL stream output.

Architecture:
- Pydantic models parse JSON into typed message structures
- Messages produce RenderBlock lists (flexible rendering primitives)
- Formatters convert RenderBlocks to output formats (ANSI, Markdown, Plain)
"""

from __future__ import annotations

import json
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal, TextIO

from pydantic import BaseModel, Field

# Optional watchdog for --watch functionality
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False


# =============================================================================
# Constants
# =============================================================================

TOOL_RESULT_PREVIEW_LINES = 20
TOOL_INPUT_TRUNCATE_LENGTH = 200


# =============================================================================
# Render Blocks - Flexible Rendering Primitives
# =============================================================================

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
    bullet: str = "•"


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


# =============================================================================
# Formatters - Convert RenderBlocks to Output
# =============================================================================

class Formatter(ABC):
    """Base class for output formatters."""

    @abstractmethod
    def format(self, blocks: list[RenderBlock]) -> str:
        """Convert render blocks to formatted string."""
        ...

    @abstractmethod
    def format_block(self, block: RenderBlock) -> str:
        """Format a single block."""
        ...


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

    def _indent(self, text: str, level: int) -> str:
        """Add indentation to text."""
        if level <= 0:
            return text
        prefix = "  " * level
        return "\n".join(prefix + line for line in text.split("\n"))

    def format(self, blocks: list[RenderBlock]) -> str:
        """Convert render blocks to ANSI-formatted string."""
        lines: list[str] = []
        for block in blocks:
            formatted = self.format_block(block)
            if formatted:
                lines.append(formatted)
        return "\n".join(lines)

    def format_block(self, block: RenderBlock) -> str:
        """Format a single block with ANSI codes."""

        if isinstance(block, HeaderBlock):
            parts = []
            if block.icon:
                parts.append(block.icon)
            if block.prefix:
                parts.append(block.prefix)
            parts.append(block.text)
            text = " ".join(parts)
            styled = self._apply_styles(text, block.styles | {Style.BOLD})
            return styled

        elif isinstance(block, TextBlock):
            styled = self._apply_styles(block.text, block.styles)
            return self._indent(styled, block.indent)

        elif isinstance(block, CodeBlock):
            # For ANSI, just indent the code
            styled = self._apply_styles(block.content, block.styles)
            return self._indent(styled, block.indent)

        elif isinstance(block, KeyValueBlock):
            key_styled = self._apply_styles(f"{block.key}:", {Style.BOLD})
            value_styled = self._apply_styles(block.value, block.styles)
            return self._indent(f"{key_styled} {value_styled}", block.indent)

        elif isinstance(block, DividerBlock):
            line = block.char * block.width
            return self._apply_styles(line, block.styles)

        elif isinstance(block, ListBlock):
            lines = [f"{block.bullet} {item}" for item in block.items]
            text = "\n".join(lines)
            styled = self._apply_styles(text, block.styles)
            return self._indent(styled, block.indent)

        elif isinstance(block, NestedBlock):
            inner = self.format(block.children)
            return self._indent(inner, block.indent)

        elif isinstance(block, SpacerBlock):
            return "\n" * (block.lines - 1)  # -1 because join adds one

        return ""


class MarkdownFormatter(Formatter):
    """Format output as Markdown."""

    def format(self, blocks: list[RenderBlock]) -> str:
        """Convert render blocks to Markdown string."""
        lines: list[str] = []
        for block in blocks:
            formatted = self.format_block(block)
            if formatted:
                lines.append(formatted)
        return "\n".join(lines)

    def _indent(self, text: str, level: int) -> str:
        """Add indentation via blockquote or spaces."""
        if level <= 0:
            return text
        # Use spaces for markdown (blockquotes would change semantics)
        prefix = "  " * level
        return "\n".join(prefix + line for line in text.split("\n"))

    def _apply_styles(self, text: str, styles: set[Style]) -> str:
        """Apply markdown formatting for styles."""
        if Style.BOLD in styles:
            text = f"**{text}**"
        if Style.ITALIC in styles or Style.THINKING in styles:
            text = f"*{text}*"
        # DIM and colors don't have direct markdown equivalents
        return text

    def format_block(self, block: RenderBlock) -> str:
        """Format a single block as Markdown."""

        if isinstance(block, HeaderBlock):
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

        elif isinstance(block, TextBlock):
            styled = self._apply_styles(block.text, block.styles)
            return self._indent(styled, block.indent)

        elif isinstance(block, CodeBlock):
            lang = block.language or ""
            content = f"```{lang}\n{block.content}\n```"
            return self._indent(content, block.indent)

        elif isinstance(block, KeyValueBlock):
            return self._indent(f"**{block.key}:** {block.value}", block.indent)

        elif isinstance(block, DividerBlock):
            return "---"

        elif isinstance(block, ListBlock):
            lines = [f"- {item}" for item in block.items]
            return self._indent("\n".join(lines), block.indent)

        elif isinstance(block, NestedBlock):
            inner = self.format(block.children)
            return self._indent(inner, block.indent)

        elif isinstance(block, SpacerBlock):
            return "\n" * (block.lines - 1)

        return ""


class PlainFormatter(Formatter):
    """Format output as plain text (no styling)."""

    def format(self, blocks: list[RenderBlock]) -> str:
        """Convert render blocks to plain text."""
        lines: list[str] = []
        for block in blocks:
            formatted = self.format_block(block)
            if formatted:
                lines.append(formatted)
        return "\n".join(lines)

    def _indent(self, text: str, level: int) -> str:
        """Add indentation."""
        if level <= 0:
            return text
        prefix = "  " * level
        return "\n".join(prefix + line for line in text.split("\n"))

    def format_block(self, block: RenderBlock) -> str:
        """Format a single block as plain text."""

        if isinstance(block, HeaderBlock):
            parts = []
            if block.prefix:
                parts.append(block.prefix)
            parts.append(block.text)
            return " ".join(parts)

        elif isinstance(block, TextBlock):
            return self._indent(block.text, block.indent)

        elif isinstance(block, CodeBlock):
            return self._indent(block.content, block.indent)

        elif isinstance(block, KeyValueBlock):
            return self._indent(f"{block.key}: {block.value}", block.indent)

        elif isinstance(block, DividerBlock):
            return block.char * block.width

        elif isinstance(block, ListBlock):
            lines = [f"{block.bullet} {item}" for item in block.items]
            return self._indent("\n".join(lines), block.indent)

        elif isinstance(block, NestedBlock):
            inner = self.format(block.children)
            return self._indent(inner, block.indent)

        elif isinstance(block, SpacerBlock):
            return "\n" * (block.lines - 1)

        return ""


# =============================================================================
# File Watcher
# =============================================================================

class FileWatcher:
    """Watch files/directories for changes and process new JSONL lines."""

    def __init__(
        self,
        config: "RenderConfig",
        formatter: Formatter,
        show_filename: bool = True
    ):
        self.config = config
        self.formatter = formatter
        self.show_filename = show_filename
        self.file_positions: dict[Path, int] = {}
        self.current_file: Path | None = None

    def _print_file_header(self, path: Path) -> None:
        """Print a header when switching to a different file."""
        if not self.show_filename:
            return
        if self.current_file == path:
            return

        self.current_file = path
        header = DividerBlock(char="─", width=60)
        file_block = HeaderBlock(
            text=str(path),
            icon="📄",
            level=2,
            styles={Style.INFO}
        )
        print(self.formatter.format([header, file_block]))

    def process_new_lines(self, path: Path) -> None:
        """Read and process any new lines from a file."""
        if not path.exists() or not path.is_file():
            return

        # Get current position (0 if new file)
        position = self.file_positions.get(path, 0)

        try:
            with open(path, "r") as f:
                f.seek(position)
                new_content = f.read()
                new_position = f.tell()

            if new_content:
                self._print_file_header(path)

                for line in new_content.strip().split("\n"):
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                        msg = parse_message(data)

                        if not should_show_message(msg, data, self.config):
                            continue

                        blocks = msg.render(self.config)
                        output = self.formatter.format(blocks)
                        print(output, flush=True)

                    except json.JSONDecodeError:
                        pass  # Skip invalid JSON

            self.file_positions[path] = new_position

        except (IOError, OSError):
            pass  # File may have been removed

    def process_tail_lines(self, path: Path, n: int) -> None:
        """Read and process the last N lines from a file."""
        if not path.exists() or not path.is_file():
            return

        try:
            with open(path, "r") as f:
                # Read all lines and take last N
                lines = f.readlines()
                tail = lines[-n:] if n < len(lines) else lines

                # Set position to end of file for future watches
                self.file_positions[path] = f.tell()

            if tail:
                self._print_file_header(path)

                for line in tail:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                        msg = parse_message(data)

                        if not should_show_message(msg, data, self.config):
                            continue

                        blocks = msg.render(self.config)
                        output = self.formatter.format(blocks)
                        print(output, flush=True)

                    except json.JSONDecodeError:
                        pass  # Skip invalid JSON

        except (IOError, OSError):
            pass  # File may have been removed

    def get_initial_files(self, path: Path, recursive: bool = True) -> list[Path]:
        """Get all .jsonl files in a path."""
        if path.is_file():
            return [path]

        if recursive:
            return list(path.rglob("*.jsonl"))
        else:
            return list(path.glob("*.jsonl"))


if WATCHDOG_AVAILABLE:
    class JSONLEventHandler(FileSystemEventHandler):
        """Watchdog event handler for JSONL files."""

        def __init__(self, watcher: FileWatcher):
            super().__init__()
            self.watcher = watcher

        def on_modified(self, event: FileModifiedEvent) -> None:
            if event.is_directory:
                return

            path = Path(event.src_path)
            if path.suffix == ".jsonl":
                self.watcher.process_new_lines(path)

        def on_created(self, event: FileCreatedEvent) -> None:
            if event.is_directory:
                return

            path = Path(event.src_path)
            if path.suffix == ".jsonl":
                # New file - start tracking from beginning
                self.watcher.file_positions[path] = 0
                self.watcher.process_new_lines(path)


def watch_path(
    path: Path,
    config: "RenderConfig",
    formatter: Formatter,
    recursive: bool = True,
    tail_lines: int = 0
) -> None:
    """Watch a file or directory for changes."""

    if not WATCHDOG_AVAILABLE:
        print("error: watchdog not installed. Run: pip install watchdog", file=sys.stderr)
        sys.exit(1)

    watcher = FileWatcher(config, formatter, show_filename=path.is_dir())

    # Get all files to watch
    initial_files = watcher.get_initial_files(path, recursive)

    if tail_lines <= 0:
        # Skip existing content - just seek to end of all files
        for file_path in initial_files:
            if file_path.exists():
                watcher.file_positions[file_path] = file_path.stat().st_size
    else:
        # Show last N lines from each file (most recent files first)
        for file_path in sorted(initial_files, key=lambda p: p.stat().st_mtime, reverse=True):
            watcher.process_tail_lines(file_path, tail_lines)

    # Set up watchdog observer
    event_handler = JSONLEventHandler(watcher)
    observer = Observer()

    watch_path_resolved = path if path.is_dir() else path.parent
    observer.schedule(event_handler, str(watch_path_resolved), recursive=recursive)

    print(f"\n{ANSIFormatter.DIM}Watching for changes... (Ctrl+C to stop){ANSIFormatter.RESET}\n",
          file=sys.stderr, flush=True)

    observer.start()
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        observer.stop()
        print("\nexiting", file=sys.stderr)

    observer.join()


# =============================================================================
# Content Block Models (nested within messages)
# =============================================================================

class ContentBlock(BaseModel):
    """Base for content blocks within messages."""

    type: str

    def render(self, config: "RenderConfig") -> list[RenderBlock]:
        """Render this content block."""
        return []


class TextContent(ContentBlock):
    """Text content block."""

    type: Literal["text"] = "text"
    text: str = ""

    def render(self, config: "RenderConfig") -> list[RenderBlock]:
        blocks: list[RenderBlock] = []
        for line in self.text.split("\n"):
            blocks.append(TextBlock(text=line, indent=1))
        return blocks


class ThinkingContent(ContentBlock):
    """Thinking/reasoning content block."""

    type: Literal["thinking"] = "thinking"
    thinking: str = ""
    signature: str = ""  # Cryptographic signature, usually not displayed

    def render(self, config: "RenderConfig") -> list[RenderBlock]:
        if not config.show_thinking:
            return []

        blocks: list[RenderBlock] = []
        blocks.append(TextBlock(
            text="💭 Thinking:",
            indent=1,
            styles={Style.THINKING}
        ))
        for line in self.thinking.split("\n"):
            blocks.append(TextBlock(
                text=line,
                indent=2,
                styles={Style.THINKING}
            ))
        return blocks


class ToolUseContent(ContentBlock):
    """Tool invocation content block."""

    type: Literal["tool_use"] = "tool_use"
    id: str = ""
    name: str = ""
    input: dict[str, Any] = Field(default_factory=dict)

    def render(self, config: "RenderConfig") -> list[RenderBlock]:
        blocks: list[RenderBlock] = []

        # Tool header
        blocks.append(HeaderBlock(
            text=f"Tool: {self.name}",
            icon="▸",
            level=3,
            styles={Style.TOOL}
        ))
        blocks.append(TextBlock(
            text=f"({self.id})",
            indent=1,
            styles={Style.METADATA}
        ))

        # Tool inputs
        if config.show_tool_results:
            for key, value in self.input.items():
                value_str = str(value)
                if len(value_str) > TOOL_INPUT_TRUNCATE_LENGTH:
                    value_str = value_str[:TOOL_INPUT_TRUNCATE_LENGTH] + "..."
                blocks.append(KeyValueBlock(
                    key=key,
                    value=value_str,
                    indent=2
                ))

        return blocks


class ToolResultContent(ContentBlock):
    """Tool result content block."""

    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str = ""
    content: str | list[dict[str, Any]] = ""
    is_error: bool = False

    def render(self, config: "RenderConfig") -> list[RenderBlock]:
        blocks: list[RenderBlock] = []

        # Result header
        if self.is_error:
            blocks.append(HeaderBlock(
                text="Error",
                icon="✗",
                level=3,
                styles={Style.ERROR}
            ))
        else:
            blocks.append(HeaderBlock(
                text="Result",
                icon="✓",
                level=3,
                styles={Style.SUCCESS}
            ))

        blocks.append(TextBlock(
            text=f"({self.tool_use_id})",
            indent=1,
            styles={Style.METADATA}
        ))

        # Result content
        if config.show_tool_results and self.content:
            content_str = str(self.content) if not isinstance(self.content, str) else self.content
            lines = content_str.split("\n")

            for line in lines[:TOOL_RESULT_PREVIEW_LINES]:
                blocks.append(TextBlock(text=line, indent=2))

            if len(lines) > TOOL_RESULT_PREVIEW_LINES:
                blocks.append(TextBlock(
                    text=f"... ({len(lines)} lines total)",
                    indent=2,
                    styles={Style.METADATA}
                ))

        return blocks


class ImageContent(ContentBlock):
    """Image content block."""

    type: Literal["image"] = "image"
    source: dict[str, Any] = Field(default_factory=dict)

    def render(self, config: "RenderConfig") -> list[RenderBlock]:
        media_type = self.source.get("media_type", "unknown")
        return [
            HeaderBlock(
                text=f"Image ({media_type})",
                icon="🖼",
                level=3,
                styles={Style.USER}
            )
        ]


# =============================================================================
# Render Configuration
# =============================================================================

@dataclass
class RenderConfig:
    """Configuration for rendering messages."""

    show_thinking: bool = True
    show_tool_results: bool = True
    show_metadata: bool = False
    show_line_numbers: bool = False

    # Filtering
    show_types: set[str] = field(default_factory=lambda: {
        "system", "assistant", "user", "file-history-snapshot",
        "summary", "queue-operation", "result"
    })
    show_subtypes: set[str] = field(default_factory=set)
    show_tools: set[str] = field(default_factory=set)
    grep_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)


# =============================================================================
# Message Models - Base Classes
# =============================================================================

class BaseMessage(BaseModel):
    """Base class for all message types."""

    type: str
    uuid: str = ""
    timestamp: str = ""
    sessionId: str = Field(default="", alias="sessionId")

    model_config = {"extra": "allow", "populate_by_name": True}

    def render(self, config: RenderConfig) -> list[RenderBlock]:
        """Render this message to blocks. Override in subclasses."""
        return [TextBlock(text=f"[Unknown message type: {self.type}]")]

    def render_metadata(self, config: RenderConfig) -> list[RenderBlock]:
        """Render metadata block if enabled."""
        if not config.show_metadata:
            return []

        blocks: list[RenderBlock] = []
        blocks.append(TextBlock(text="┌─ Metadata", indent=1, styles={Style.METADATA}))

        if self.uuid:
            blocks.append(TextBlock(text=f"│ uuid: {self.uuid}", indent=1, styles={Style.METADATA}))
        if self.sessionId:
            blocks.append(TextBlock(text=f"│ session: {self.sessionId}", indent=1, styles={Style.METADATA}))
        if self.timestamp:
            blocks.append(TextBlock(text=f"│ timestamp: {self.timestamp}", indent=1, styles={Style.METADATA}))

        blocks.append(TextBlock(text="└─", indent=1, styles={Style.METADATA}))
        return blocks


class AgentStyleMessage(BaseMessage):
    """Base for agent-style messages (assistant, sub-agents)."""

    message: dict[str, Any] = Field(default_factory=dict)
    isSidechain: bool = False

    def get_agent_label(self) -> str:
        """Get the label for this agent. Override in subclasses."""
        return "AGENT"

    def get_agent_icon(self) -> str:
        """Get the icon for this agent."""
        return "◆"

    def get_content_items(self) -> list[dict[str, Any]]:
        """Get the content items from the message."""
        content = self.message.get("content", [])
        return content if isinstance(content, list) else []

    def get_usage(self) -> dict[str, int]:
        """Get token usage from message."""
        return self.message.get("usage", {})

    def render_header(self, config: RenderConfig) -> list[RenderBlock]:
        """Render the agent header."""
        return [HeaderBlock(
            text=self.get_agent_label(),
            icon=self.get_agent_icon(),
            level=2,
            styles={Style.ASSISTANT, Style.BOLD}
        )]

    def render_content(self, config: RenderConfig) -> list[RenderBlock]:
        """Render the message content."""
        blocks: list[RenderBlock] = []

        for item in self.get_content_items():
            content_type = item.get("type", "")

            if content_type == "text":
                content = TextContent(**item)
                blocks.extend(content.render(config))

            elif content_type == "thinking":
                content = ThinkingContent(**item)
                blocks.extend(content.render(config))

            elif content_type == "tool_use":
                content = ToolUseContent(**item)
                blocks.extend(content.render(config))

            elif content_type == "tool_result":
                content = ToolResultContent(**item)
                blocks.extend(content.render(config))

            elif content_type == "image":
                content = ImageContent(**item)
                blocks.extend(content.render(config))

        return blocks

    def render_usage(self, config: RenderConfig) -> list[RenderBlock]:
        """Render token usage."""
        usage = self.get_usage()
        in_tokens = usage.get("input_tokens", 0)
        out_tokens = usage.get("output_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)

        if in_tokens > 0 or out_tokens > 0:
            return [TextBlock(
                text=f"Tokens: in={in_tokens} out={out_tokens} cache={cache_read}",
                indent=1,
                styles={Style.METADATA}
            )]
        return []

    def render(self, config: RenderConfig) -> list[RenderBlock]:
        blocks: list[RenderBlock] = []
        blocks.extend(self.render_header(config))
        blocks.extend(self.render_content(config))
        blocks.extend(self.render_usage(config))
        blocks.extend(self.render_metadata(config))
        blocks.append(SpacerBlock())
        return blocks


class SystemStyleMessage(BaseMessage):
    """Base for system-style messages."""

    def get_system_label(self) -> str:
        """Get label for this system message."""
        return "SYSTEM"

    def get_system_icon(self) -> str:
        """Get icon for this system message."""
        return "▸"

    def render_header(self, config: RenderConfig) -> list[RenderBlock]:
        """Render system header."""
        return [HeaderBlock(
            text=self.get_system_label(),
            icon=self.get_system_icon(),
            level=2,
            styles={Style.SYSTEM}
        )]


# =============================================================================
# Message Models - Concrete Types
# =============================================================================

class AssistantMessage(AgentStyleMessage):
    """Assistant response message."""

    type: Literal["assistant"] = "assistant"

    def get_agent_label(self) -> str:
        if self.isSidechain:
            return "ASSISTANT (Task Agent)"
        return "ASSISTANT"


class UserMessage(BaseMessage):
    """User input message."""

    type: Literal["user"] = "user"
    message: dict[str, Any] = Field(default_factory=dict)
    userType: str = ""
    toolUseResult: dict[str, Any] | str | None = None

    def is_subagent_result(self) -> bool:
        """Check if this is a sub-agent result."""
        return (
            isinstance(self.toolUseResult, dict) and
            self.toolUseResult.get("agentId") is not None
        )

    def is_tool_result(self) -> bool:
        """Check if this is a tool result (not sub-agent)."""
        return self.toolUseResult is not None and not self.is_subagent_result()

    def is_local_command(self) -> bool:
        """Check if this is a local slash command."""
        content = self.message.get("content", "")
        return isinstance(content, str) and (
            content.startswith("<command-name>") or
            content.startswith("<local-command-stdout>")
        )

    def render(self, config: RenderConfig) -> list[RenderBlock]:
        if self.is_subagent_result():
            return self.render_subagent(config)
        elif self.is_tool_result():
            return self.render_tool_result(config)
        elif self.is_local_command():
            return self.render_local_command(config)
        else:
            return self.render_user_input(config)

    def render_user_input(self, config: RenderConfig) -> list[RenderBlock]:
        """Render as regular user input."""
        blocks: list[RenderBlock] = []

        blocks.append(HeaderBlock(
            text="USER",
            icon="◂",
            level=2,
            styles={Style.USER}
        ))

        content = self.message.get("content")
        if isinstance(content, str) and content:
            for line in content.split("\n"):
                blocks.append(TextBlock(text=line, indent=1))
        elif isinstance(content, list):
            for item in content:
                item_type = item.get("type", "")
                if item_type == "text":
                    text = item.get("text", "")
                    for line in text.split("\n"):
                        blocks.append(TextBlock(text=line, indent=1))
                elif item_type == "tool_result":
                    result = ToolResultContent(**item)
                    blocks.extend(result.render(config))
                elif item_type == "image":
                    img = ImageContent(**item)
                    blocks.extend(img.render(config))

        blocks.extend(self.render_metadata(config))
        blocks.append(SpacerBlock())
        return blocks

    def render_tool_result(self, config: RenderConfig) -> list[RenderBlock]:
        """Render as tool result (no USER header)."""
        blocks: list[RenderBlock] = []

        content = self.message.get("content", [])
        if isinstance(content, list):
            for item in content:
                if item.get("type") == "tool_result":
                    result = ToolResultContent(**item)
                    blocks.extend(result.render(config))

        blocks.extend(self.render_metadata(config))
        blocks.append(SpacerBlock())
        return blocks

    def render_subagent(self, config: RenderConfig) -> list[RenderBlock]:
        """Render as sub-agent result."""
        blocks: list[RenderBlock] = []

        agent_id = self.toolUseResult.get("agentId", "unknown")

        blocks.append(HeaderBlock(
            text=f"SUB-AGENT ({agent_id})",
            icon="◆",
            level=2,
            styles={Style.ASSISTANT, Style.BOLD}
        ))

        # Render sub-agent content
        content_items = self.toolUseResult.get("content", [])
        for item in content_items:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                for line in text.split("\n"):
                    blocks.append(TextBlock(text=line, indent=1))

        # Token usage
        total_tokens = self.toolUseResult.get("totalTokens", 0)
        if total_tokens > 0:
            blocks.append(TextBlock(
                text=f"Total tokens: {total_tokens}",
                indent=1,
                styles={Style.METADATA}
            ))

        blocks.extend(self.render_metadata(config))
        blocks.append(SpacerBlock())
        return blocks

    def render_local_command(self, config: RenderConfig) -> list[RenderBlock]:
        """Render as local slash command."""
        blocks: list[RenderBlock] = []

        content = self.message.get("content", "")

        if content.startswith("<command-name>"):
            # Parse command
            cmd_name = ""
            cmd_args = ""

            if "<command-name>" in content and "</command-name>" in content:
                start = content.index("<command-name>") + len("<command-name>")
                end = content.index("</command-name>")
                cmd_name = content[start:end]

            if "<command-args>" in content and "</command-args>" in content:
                start = content.index("<command-args>") + len("<command-args>")
                end = content.index("</command-args>")
                cmd_args = content[start:end]

            blocks.append(HeaderBlock(
                text=f"Command: {cmd_name}",
                icon="▸",
                level=3,
                styles={Style.USER}
            ))

            if cmd_args:
                blocks.append(KeyValueBlock(key="args", value=cmd_args, indent=1))

        elif content.startswith("<local-command-stdout>"):
            if config.show_tool_results:
                stdout = content.replace("<local-command-stdout>", "").replace("</local-command-stdout>", "")

                blocks.append(HeaderBlock(
                    text="Output",
                    icon="✓",
                    level=3,
                    styles={Style.USER}
                ))

                lines = stdout.split("\n")
                for line in lines[:TOOL_RESULT_PREVIEW_LINES]:
                    blocks.append(TextBlock(text=line, indent=2))

                if len(lines) > TOOL_RESULT_PREVIEW_LINES:
                    blocks.append(TextBlock(
                        text=f"... ({len(lines)} lines total)",
                        indent=2,
                        styles={Style.METADATA}
                    ))

        blocks.extend(self.render_metadata(config))
        blocks.append(SpacerBlock())
        return blocks


class SystemMessage(SystemStyleMessage):
    """System message (init, compact_boundary, etc.)."""

    type: Literal["system"] = "system"
    subtype: str = ""
    content: str = ""
    model: str = ""
    claude_code_version: str = ""
    cwd: str = ""
    compactMetadata: dict[str, Any] = Field(default_factory=dict)

    def render(self, config: RenderConfig) -> list[RenderBlock]:
        blocks: list[RenderBlock] = []

        blocks.append(HeaderBlock(
            text=f"SYSTEM ({self.subtype})",
            icon="▸",
            level=2,
            styles={Style.SYSTEM}
        ))

        if self.subtype == "init":
            blocks.append(KeyValueBlock(key="Model", value=self.model, indent=1))
            blocks.append(KeyValueBlock(key="Version", value=self.claude_code_version, indent=1))
            blocks.append(KeyValueBlock(key="Directory", value=self.cwd, indent=1))
        elif self.subtype == "compact_boundary":
            pre_tokens = self.compactMetadata.get("preTokens", 0)
            blocks.append(TextBlock(
                text=f"{self.content} ({pre_tokens} tokens before compaction)",
                indent=1
            ))
        elif self.content:
            blocks.append(TextBlock(text=self.content, indent=1))

        blocks.extend(self.render_metadata(config))
        blocks.append(SpacerBlock())
        return blocks


class FileHistorySnapshot(SystemStyleMessage):
    """File history snapshot message."""

    type: Literal["file-history-snapshot"] = "file-history-snapshot"
    snapshot: dict[str, Any] = Field(default_factory=dict)

    def render(self, config: RenderConfig) -> list[RenderBlock]:
        timestamp = self.snapshot.get("timestamp", "unknown")
        return [
            HeaderBlock(
                text=f"File History Snapshot ({timestamp})",
                icon="📸",
                level=2,
                styles={Style.SYSTEM}
            ),
            SpacerBlock()
        ]


class SummaryMessage(BaseMessage):
    """Summary message."""

    type: Literal["summary"] = "summary"
    summary: str = ""

    def render(self, config: RenderConfig) -> list[RenderBlock]:
        return [
            HeaderBlock(
                text=self.summary,
                icon="📋",
                prefix="Summary:",
                level=1,
                styles={Style.INFO}
            ),
            SpacerBlock()
        ]


class QueueOperationMessage(SystemStyleMessage):
    """Queue operation message."""

    type: Literal["queue-operation"] = "queue-operation"
    operation: str = ""
    content: str = ""

    def render(self, config: RenderConfig) -> list[RenderBlock]:
        blocks: list[RenderBlock] = []

        blocks.append(HeaderBlock(
            text=f"Queue: {self.operation}",
            icon="⚙",
            level=2,
            styles={Style.SYSTEM}
        ))

        if self.content:
            for line in self.content.split("\n"):
                blocks.append(TextBlock(text=line, indent=1))

        blocks.extend(self.render_metadata(config))
        blocks.append(SpacerBlock())
        return blocks


class ResultMessage(BaseMessage):
    """Session result message."""

    type: Literal["result"] = "result"
    subtype: str = ""
    total_cost_usd: float = 0.0
    duration_ms: int = 0
    num_turns: int = 0
    usage: dict[str, int] = Field(default_factory=dict)

    def render(self, config: RenderConfig) -> list[RenderBlock]:
        blocks: list[RenderBlock] = []

        blocks.append(DividerBlock(char="═", width=30))
        blocks.append(HeaderBlock(
            text="SESSION COMPLETE",
            level=1,
            styles={Style.BOLD, Style.INFO}
        ))
        blocks.append(DividerBlock(char="═", width=30))

        blocks.append(KeyValueBlock(key="Status", value=self.subtype, indent=1))
        blocks.append(KeyValueBlock(key="Turns", value=str(self.num_turns), indent=1))
        blocks.append(KeyValueBlock(
            key="Duration",
            value=f"{(self.duration_ms + 500) // 1000}s",
            indent=1
        ))
        blocks.append(KeyValueBlock(
            key="Cost",
            value=f"${self.total_cost_usd:.4f}",
            indent=1
        ))

        in_tokens = self.usage.get("input_tokens", 0)
        out_tokens = self.usage.get("output_tokens", 0)
        cache_read = self.usage.get("cache_read_input_tokens", 0)
        blocks.append(KeyValueBlock(
            key="Tokens",
            value=f"in={in_tokens} out={out_tokens} cache={cache_read}",
            indent=1
        ))

        blocks.extend(self.render_metadata(config))
        blocks.append(SpacerBlock())
        return blocks


# =============================================================================
# Message Factory
# =============================================================================

def parse_message(data: dict[str, Any]) -> BaseMessage:
    """Parse a JSON dict into the appropriate message type."""

    msg_type = data.get("type", "")

    if msg_type == "assistant":
        return AssistantMessage(**data)
    elif msg_type == "user":
        return UserMessage(**data)
    elif msg_type == "system":
        return SystemMessage(**data)
    elif msg_type == "file-history-snapshot":
        return FileHistorySnapshot(**data)
    elif msg_type == "summary":
        return SummaryMessage(**data)
    elif msg_type == "queue-operation":
        return QueueOperationMessage(**data)
    elif msg_type == "result":
        return ResultMessage(**data)
    else:
        # Return base message for unknown types
        return BaseMessage(**data)


# =============================================================================
# Filtering
# =============================================================================

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


# =============================================================================
# Stream Processing
# =============================================================================

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
