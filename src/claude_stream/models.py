"""Data models for Claude Code JSONL messages.

This module contains all TypedDicts, Pydantic models, RenderConfig,
and the parse_message function for parsing JSON data into message objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from .blocks import (
    DividerBlock,
    HeaderBlock,
    KeyValueBlock,
    RenderBlock,
    SpacerBlock,
    Style,
    TextBlock,
)


# =============================================================================
# Constants
# =============================================================================

TOOL_RESULT_PREVIEW_LINES = 20
TOOL_INPUT_TRUNCATE_LENGTH = 200


# =============================================================================
# TypedDicts for Known Structures
# =============================================================================

class UsageInfo(TypedDict, total=False):
    """Token usage information."""

    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int


class TextContentItem(TypedDict):
    """Text content item structure."""

    type: Literal["text"]
    text: str


class ThinkingContentItem(TypedDict, total=False):
    """Thinking content item structure."""

    type: Literal["thinking"]
    thinking: str
    signature: str


class ToolUseContentItem(TypedDict, total=False):
    """Tool use content item structure."""

    type: Literal["tool_use"]
    id: str
    name: str
    input: dict[str, Any]


class ToolResultTextItem(TypedDict):
    """Text item within tool result content."""

    type: Literal["text"]
    text: str


class ToolResultImageItem(TypedDict):
    """Image item within tool result content."""

    type: Literal["image"]
    source: dict[str, Any]


# Tool result content can be a string or a list of text/image items
ToolResultContentValue = str | list[ToolResultTextItem | ToolResultImageItem]


class ToolResultContentItem(TypedDict, total=False):
    """Tool result content item structure."""

    type: Literal["tool_result"]
    tool_use_id: str
    content: ToolResultContentValue
    is_error: bool


class ImageSourceInfo(TypedDict, total=False):
    """Image source information."""

    type: str
    media_type: str
    data: str


class ImageContentItem(TypedDict, total=False):
    """Image content item structure."""

    type: Literal["image"]
    source: ImageSourceInfo


# Union of all content item types
ContentItem = (
    TextContentItem
    | ThinkingContentItem
    | ToolUseContentItem
    | ToolResultContentItem
    | ImageContentItem
)


class CompactMetadata(TypedDict, total=False):
    """Metadata for compact_boundary system messages."""

    preTokens: int
    postTokens: int


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
# Content Block Models (nested within messages)
# =============================================================================

class ContentBlock(BaseModel):
    """Base for content blocks within messages."""

    type: str

    def render(self, config: RenderConfig) -> list[RenderBlock]:
        """Render this content block."""
        return []


class TextContent(ContentBlock):
    """Text content block."""

    type: Literal["text"] = "text"
    text: str = ""

    def render(self, config: RenderConfig) -> list[RenderBlock]:
        blocks: list[RenderBlock] = []
        for line in self.text.split("\n"):
            blocks.append(TextBlock(text=line, indent=1))
        return blocks


class ThinkingContent(ContentBlock):
    """Thinking/reasoning content block."""

    type: Literal["thinking"] = "thinking"
    thinking: str = ""
    signature: str = ""  # Cryptographic signature, usually not displayed

    def render(self, config: RenderConfig) -> list[RenderBlock]:
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

    def render(self, config: RenderConfig) -> list[RenderBlock]:
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
    content: ToolResultContentValue = ""
    is_error: bool = False

    def render(self, config: RenderConfig) -> list[RenderBlock]:
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
            content_str = self._content_to_string()
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

    def _content_to_string(self) -> str:
        """Convert content to string representation."""
        if isinstance(self.content, str):
            return self.content
        # List of text/image items
        parts: list[str] = []
        for item in self.content:
            if item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif item.get("type") == "image":
                media_type = item.get("source", {}).get("media_type", "unknown")
                parts.append(f"[Image: {media_type}]")
        return "\n".join(parts)


class ImageContent(ContentBlock):
    """Image content block."""

    type: Literal["image"] = "image"
    source: ImageSourceInfo = Field(default_factory=dict)  # type: ignore[assignment]

    def render(self, config: RenderConfig) -> list[RenderBlock]:
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
        blocks.append(TextBlock(text="-- Metadata", indent=1, styles={Style.METADATA}))

        if self.uuid:
            blocks.append(TextBlock(text=f"| uuid: {self.uuid}", indent=1, styles={Style.METADATA}))
        if self.sessionId:
            blocks.append(TextBlock(text=f"| session: {self.sessionId}", indent=1, styles={Style.METADATA}))
        if self.timestamp:
            blocks.append(TextBlock(text=f"| timestamp: {self.timestamp}", indent=1, styles={Style.METADATA}))

        blocks.append(TextBlock(text="--", indent=1, styles={Style.METADATA}))
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
        return "*"

    def get_content_items(self) -> list[ContentItem]:
        """Get the content items from the message."""
        content = self.message.get("content", [])
        return content if isinstance(content, list) else []

    def get_usage(self) -> UsageInfo:
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
        return ">"

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
                if start < end:
                    cmd_name = content[start:end]

            if "<command-args>" in content and "</command-args>" in content:
                start = content.index("<command-args>") + len("<command-args>")
                end = content.index("</command-args>")
                if start < end:
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
                    icon="◆",
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
    compactMetadata: CompactMetadata = Field(default_factory=dict)  # type: ignore[assignment]

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
    usage: UsageInfo = Field(default_factory=dict)  # type: ignore[assignment]

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
# Message Discriminated Union and Factory
# =============================================================================

# Discriminated union of all known message types
# Uses Pydantic's discriminator feature for automatic type resolution
Message = Annotated[
    Union[
        AssistantMessage,
        UserMessage,
        SystemMessage,
        FileHistorySnapshot,
        SummaryMessage,
        QueueOperationMessage,
        ResultMessage,
    ],
    Field(discriminator="type")
]


class _MessageAdapter(BaseModel):
    """Internal adapter for parsing messages via discriminated union."""

    root: Message

    model_config = {"extra": "allow"}


def parse_message(data: dict[str, Any]) -> BaseMessage:
    """Parse a JSON dict into the appropriate message type.

    Uses Pydantic's discriminated union internally for known types,
    falling back to BaseMessage for unknown types.
    """
    msg_type = data.get("type", "")

    # Known types that can be handled by the discriminated union
    known_types = {
        "assistant", "user", "system", "file-history-snapshot",
        "summary", "queue-operation", "result"
    }

    if msg_type in known_types:
        try:
            adapter = _MessageAdapter(root=data)  # type: ignore[arg-type]
            return adapter.root
        except Exception:
            # Fall back to base message if discriminated union fails
            return BaseMessage(**data)
    else:
        # Unknown type - return base message
        return BaseMessage(**data)
