"""Tests for timestamp-related CLI flags."""

import sys
from unittest.mock import patch

from claude_logs.cli import parse_args


class TestTimestampFlags:
    def test_show_timestamps_default(self):
        with patch.object(sys, "argv", ["claugs", "show", "--latest"]):
            _, args = parse_args()
        assert args.show_timestamps is None

    def test_hide_timestamps(self):
        with patch.object(
            sys, "argv", ["claugs", "show", "--hide-timestamps", "--latest"]
        ):
            _, args = parse_args()
        assert args.show_timestamps is False

    def test_show_timestamps_explicit(self):
        with patch.object(
            sys, "argv", ["claugs", "show", "--show-timestamps", "--latest"]
        ):
            _, args = parse_args()
        assert args.show_timestamps is True

    def test_timestamp_format(self):
        with patch.object(
            sys,
            "argv",
            ["claugs", "show", "--timestamp-format", "%H:%M", "--latest"],
        ):
            _, args = parse_args()
        assert args.timestamp_format == "%H:%M"

    def test_timestamp_format_default(self):
        with patch.object(sys, "argv", ["claugs", "show", "--latest"]):
            _, args = parse_args()
        assert args.timestamp_format is None

    def test_compact_hides_timestamps(self):
        with patch.object(sys, "argv", ["claugs", "show", "--compact", "--latest"]):
            _, args = parse_args()
        assert args.compact is True
        assert args.show_timestamps is None
