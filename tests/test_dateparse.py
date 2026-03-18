"""Tests for dateparse module."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from claude_stream.dateparse import parse_datetime


class TestParseDatetimeISO:
    """Test ISO 8601 date parsing."""

    def test_date_only(self):
        result = parse_datetime("2026-03-17")
        assert result.year == 2026
        assert result.month == 3
        assert result.day == 17
        assert result.tzinfo is not None  # always timezone-aware

    def test_datetime_with_t(self):
        result = parse_datetime("2026-03-17T14:23:05")
        assert result.hour == 14
        assert result.minute == 23
        assert result.second == 5

    def test_datetime_with_z(self):
        result = parse_datetime("2026-03-17T14:23:05Z")
        assert result.tzinfo == timezone.utc


class TestParseDatetimeKeywords:
    """Test keyword substitutions."""

    @patch("claude_stream.dateparse._now")
    def test_today(self, mock_now):
        mock_now.return_value = datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
        result = parse_datetime("today")
        assert result.date() == datetime(2026, 3, 17).date()

    @patch("claude_stream.dateparse._now")
    def test_tomorrow(self, mock_now):
        mock_now.return_value = datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
        result = parse_datetime("tomorrow")
        assert result.date() == datetime(2026, 3, 18).date()

    @patch("claude_stream.dateparse._now")
    def test_noon(self, mock_now):
        mock_now.return_value = datetime(2026, 3, 17, 9, 0, 0, tzinfo=timezone.utc)
        result = parse_datetime("noon")
        assert result.hour == 12
        assert result.minute == 0

    @patch("claude_stream.dateparse._now")
    def test_midnight(self, mock_now):
        mock_now.return_value = datetime(2026, 3, 17, 9, 0, 0, tzinfo=timezone.utc)
        result = parse_datetime("midnight")
        assert result.hour == 0
        assert result.minute == 0


class TestParseDatetimeRelative:
    """Test relative time parsing."""

    @patch("claude_stream.dateparse._now")
    def test_now_minus_2h(self, mock_now):
        base = datetime(2026, 3, 17, 14, 0, 0, tzinfo=timezone.utc)
        mock_now.return_value = base
        result = parse_datetime("now -2h")
        assert result == base - timedelta(hours=2)

    @patch("claude_stream.dateparse._now")
    def test_plus_30m(self, mock_now):
        base = datetime(2026, 3, 17, 14, 0, 0, tzinfo=timezone.utc)
        mock_now.return_value = base
        result = parse_datetime("+30m")
        assert result == base + timedelta(minutes=30)

    @patch("claude_stream.dateparse._now")
    def test_5d(self, mock_now):
        base = datetime(2026, 3, 17, 14, 0, 0, tzinfo=timezone.utc)
        mock_now.return_value = base
        result = parse_datetime("5d")
        assert result == base + timedelta(days=5)

    @patch("claude_stream.dateparse._now")
    def test_minus_1w(self, mock_now):
        base = datetime(2026, 3, 17, 14, 0, 0, tzinfo=timezone.utc)
        mock_now.return_value = base
        result = parse_datetime("now -1w")
        assert result == base - timedelta(weeks=1)


class TestParseDatetimeNaturalLanguage:
    """Test natural language via dateutil."""

    def test_month_day_year(self):
        result = parse_datetime("March 17, 2026")
        assert result.year == 2026
        assert result.month == 3
        assert result.day == 17

    def test_always_timezone_aware(self):
        """All results must be timezone-aware."""
        result = parse_datetime("2026-01-01")
        assert result.tzinfo is not None


class TestParseDatetimeInvalid:
    """Test error handling."""

    def test_empty_string(self):
        with pytest.raises(ValueError):
            parse_datetime("")

    def test_gibberish(self):
        with pytest.raises(ValueError):
            parse_datetime("qqq zzz www")
