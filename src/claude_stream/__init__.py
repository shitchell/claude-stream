"""
Parse and prettify Claude Code JSONL stream output.

Architecture:
- Pydantic models parse JSON into typed message structures
- Messages produce RenderBlock lists (flexible rendering primitives)
- Formatters convert RenderBlocks to output formats (ANSI, Markdown, Plain)
"""

from __future__ import annotations

# Block types and Style enum
from .blocks import (
    AnyBlock,
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

# Formatters
from .formatters import (
    ANSIFormatter,
    Formatter,
    MarkdownFormatter,
    PlainFormatter,
)

# Models, TypedDicts, and parse_message
from .models import (
    # TypedDicts
    CompactMetadata,
    ContentItem,
    ImageContentItem,
    ImageSourceInfo,
    TextContentItem,
    ThinkingContentItem,
    ToolResultContentItem,
    ToolResultContentValue,
    ToolResultImageItem,
    ToolResultTextItem,
    ToolUseContentItem,
    UsageInfo,
    # Content block models
    ContentBlock,
    ImageContent,
    TextContent,
    ThinkingContent,
    ToolResultContent,
    ToolUseContent,
    # Message models
    AgentStyleMessage,
    AssistantMessage,
    BaseMessage,
    FileHistorySnapshot,
    QueueOperationMessage,
    ResultMessage,
    SummaryMessage,
    SystemMessage,
    SystemStyleMessage,
    UserMessage,
    # Discriminated union and parser
    Message,
    parse_message,
    # Config
    RenderConfig,
    # Constants
    TOOL_INPUT_TRUNCATE_LENGTH,
    TOOL_RESULT_PREVIEW_LINES,
)

# Stream processing
from .stream import (
    process_stream,
    should_show_message,
)

# File watching
from .watcher import (
    FileWatcher,
    WATCHDOG_AVAILABLE,
    watch_path,
)

# Conditionally export JSONLEventHandler if watchdog is available
if WATCHDOG_AVAILABLE:
    from .watcher import JSONLEventHandler

__all__ = [
    # Blocks
    "AnyBlock",
    "CodeBlock",
    "DividerBlock",
    "HeaderBlock",
    "KeyValueBlock",
    "ListBlock",
    "NestedBlock",
    "RenderBlock",
    "SpacerBlock",
    "Style",
    "TextBlock",
    # Formatters
    "ANSIFormatter",
    "Formatter",
    "MarkdownFormatter",
    "PlainFormatter",
    # TypedDicts
    "CompactMetadata",
    "ContentItem",
    "ImageContentItem",
    "ImageSourceInfo",
    "TextContentItem",
    "ThinkingContentItem",
    "ToolResultContentItem",
    "ToolResultContentValue",
    "ToolResultImageItem",
    "ToolResultTextItem",
    "ToolUseContentItem",
    "UsageInfo",
    # Content blocks
    "ContentBlock",
    "ImageContent",
    "TextContent",
    "ThinkingContent",
    "ToolResultContent",
    "ToolUseContent",
    # Messages
    "AgentStyleMessage",
    "AssistantMessage",
    "BaseMessage",
    "FileHistorySnapshot",
    "Message",
    "QueueOperationMessage",
    "ResultMessage",
    "SummaryMessage",
    "SystemMessage",
    "SystemStyleMessage",
    "UserMessage",
    # Config and parsing
    "RenderConfig",
    "parse_message",
    # Constants
    "TOOL_INPUT_TRUNCATE_LENGTH",
    "TOOL_RESULT_PREVIEW_LINES",
    # Stream processing
    "process_stream",
    "should_show_message",
    # Watcher
    "FileWatcher",
    "WATCHDOG_AVAILABLE",
    "watch_path",
]
