"""Tests for timestamp display in message rendering."""

from datetime import datetime, timezone

from claude_stream.blocks import HeaderBlock, Style
from claude_stream.models import (
    AssistantMessage,
    QueueOperationMessage,
    RenderConfig,
    ResultMessage,
    SummaryMessage,
    SystemMessage,
    UserMessage,
    parse_message,
)


def _find_header(blocks) -> HeaderBlock | None:
    """Find the first HeaderBlock in a list of render blocks."""
    for b in blocks:
        if isinstance(b, HeaderBlock):
            return b
    return None


def _expected_local(iso_utc: str, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Convert a UTC ISO timestamp to expected local-time formatted string."""
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone()
    return f"· {dt.strftime(fmt)}"


class TestTimestampInHeaders:
    def test_assistant_message_has_timestamp_suffix(self, sample_assistant_message):
        config = RenderConfig(show_timestamps=True)
        msg = parse_message(sample_assistant_message)
        blocks = msg.render(config)
        header = _find_header(blocks)
        assert header is not None
        expected = _expected_local("2026-03-17T14:23:05.000Z")
        assert expected in header.suffix

    def test_user_message_has_timestamp_suffix(self, sample_user_message):
        config = RenderConfig(show_timestamps=True)
        msg = parse_message(sample_user_message)
        blocks = msg.render(config)
        header = _find_header(blocks)
        assert header is not None
        expected = _expected_local("2026-03-17T14:23:12.000Z")
        assert expected in header.suffix

    def test_system_message_has_timestamp_suffix(self, sample_system_init_message):
        config = RenderConfig(show_timestamps=True)
        msg = parse_message(sample_system_init_message)
        blocks = msg.render(config)
        header = _find_header(blocks)
        assert header is not None
        expected = _expected_local("2026-03-17T14:22:58.000Z")
        assert expected in header.suffix

    def test_result_message_has_timestamp_suffix(self, sample_result_message):
        config = RenderConfig(show_timestamps=True)
        msg = parse_message(sample_result_message)
        blocks = msg.render(config)
        headers = [b for b in blocks if isinstance(b, HeaderBlock)]
        expected = _expected_local("2026-03-17T14:30:00.000Z")
        assert any(expected in h.suffix for h in headers)


class TestTimestampHidden:
    def test_no_suffix_when_hidden(self, sample_assistant_message):
        config = RenderConfig(show_timestamps=False)
        msg = parse_message(sample_assistant_message)
        blocks = msg.render(config)
        header = _find_header(blocks)
        assert header is not None
        assert header.suffix == ""


class TestTimestampFormat:
    def test_custom_format(self, sample_assistant_message):
        config = RenderConfig(show_timestamps=True, timestamp_format="%H:%M")
        msg = parse_message(sample_assistant_message)
        blocks = msg.render(config)
        header = _find_header(blocks)
        assert header is not None
        expected = _expected_local("2026-03-17T14:23:05.000Z", "%H:%M")
        assert expected in header.suffix


class TestTimestampMissing:
    def test_no_timestamp_no_suffix(self, sample_message_no_timestamp):
        config = RenderConfig(show_timestamps=True)
        msg = parse_message(sample_message_no_timestamp)
        blocks = msg.render(config)
        header = _find_header(blocks)
        assert header is not None
        assert header.suffix == ""


class TestToolResultNoTimestamp:
    def test_tool_result_no_header(self, sample_tool_result_message):
        config = RenderConfig(show_timestamps=True, show_tool_results=True)
        msg = parse_message(sample_tool_result_message)
        blocks = msg.render(config)
        headers = [b for b in blocks if isinstance(b, HeaderBlock)]
        for h in headers:
            assert "USER" not in h.text
