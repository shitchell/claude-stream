"""Tests for --compact flag behavior."""

import sys
from unittest.mock import patch

from claude_logs.cli import parse_args


class TestCompactFlag:
    def test_compact_hides_thinking(self):
        """--compact alone should hide thinking (currently broken)."""
        with patch.object(sys, "argv", ["claugs", "show", "--compact", "--latest"]):
            _, args = parse_args()
        assert args.compact is True
        assert args.show_thinking is None

    def test_compact_with_explicit_override(self):
        """--compact --show-thinking should show thinking (explicit wins)."""
        with patch.object(
            sys,
            "argv",
            ["claugs", "show", "--compact", "--show-thinking", "--latest"],
        ):
            _, args = parse_args()
        assert args.compact is True
        assert args.show_thinking is True

    def test_no_compact_defaults(self):
        """Without --compact, visibility flags should be None (use defaults)."""
        with patch.object(sys, "argv", ["claugs", "show", "--latest"]):
            _, args = parse_args()
        assert args.compact is False
        assert args.show_thinking is None
        assert args.show_tool_results is None
        assert args.show_metadata is None
