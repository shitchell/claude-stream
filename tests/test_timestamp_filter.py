"""Tests for --before/--after timestamp filtering."""

from datetime import datetime, timezone

from claude_stream.models import RenderConfig, parse_message
from claude_stream.stream import should_show_message


class TestTimestampFilterAfter:
    def test_message_after_cutoff_shown(self, sample_assistant_message):
        config = RenderConfig(after=datetime(2026, 3, 17, 14, 0, 0, tzinfo=timezone.utc))
        msg = parse_message(sample_assistant_message)
        assert should_show_message(msg, sample_assistant_message, config) is True

    def test_message_before_cutoff_hidden(self, sample_assistant_message):
        config = RenderConfig(after=datetime(2026, 3, 17, 15, 0, 0, tzinfo=timezone.utc))
        msg = parse_message(sample_assistant_message)
        assert should_show_message(msg, sample_assistant_message, config) is False


class TestTimestampFilterBefore:
    def test_message_before_cutoff_shown(self, sample_assistant_message):
        config = RenderConfig(before=datetime(2026, 3, 17, 15, 0, 0, tzinfo=timezone.utc))
        msg = parse_message(sample_assistant_message)
        assert should_show_message(msg, sample_assistant_message, config) is True

    def test_message_after_cutoff_hidden(self, sample_assistant_message):
        config = RenderConfig(before=datetime(2026, 3, 17, 14, 0, 0, tzinfo=timezone.utc))
        msg = parse_message(sample_assistant_message)
        assert should_show_message(msg, sample_assistant_message, config) is False


class TestTimestampFilterRange:
    def test_message_in_range_shown(self, sample_assistant_message):
        config = RenderConfig(
            after=datetime(2026, 3, 17, 14, 0, 0, tzinfo=timezone.utc),
            before=datetime(2026, 3, 17, 15, 0, 0, tzinfo=timezone.utc),
        )
        msg = parse_message(sample_assistant_message)
        assert should_show_message(msg, sample_assistant_message, config) is True

    def test_message_outside_range_hidden(self, sample_assistant_message):
        config = RenderConfig(
            after=datetime(2026, 3, 17, 15, 0, 0, tzinfo=timezone.utc),
            before=datetime(2026, 3, 17, 16, 0, 0, tzinfo=timezone.utc),
        )
        msg = parse_message(sample_assistant_message)
        assert should_show_message(msg, sample_assistant_message, config) is False


class TestTimestampFilterNoTimestamp:
    def test_message_without_timestamp_passes(self, sample_message_no_timestamp):
        config = RenderConfig(after=datetime(2026, 3, 17, 15, 0, 0, tzinfo=timezone.utc))
        msg = parse_message(sample_message_no_timestamp)
        assert should_show_message(msg, sample_message_no_timestamp, config) is True
