"""Tests for --search mode."""

import sys
from unittest.mock import patch

from claude_logs.cli import main
from conftest import create_session_file


class TestSearchFilepathMode:
    def test_search_finds_matching_file(self, tmp_path, capsys):
        create_session_file(
            tmp_path,
            "session-001",
            [
                {
                    "type": "user",
                    "timestamp": "2026-03-17T14:00:00Z",
                    "message": {"content": "find the needle in the haystack"},
                },
            ],
        )
        create_session_file(
            tmp_path,
            "session-002",
            [
                {
                    "type": "user",
                    "timestamp": "2026-03-17T15:00:00Z",
                    "message": {"content": "nothing here"},
                },
            ],
        )
        with patch.object(
            sys,
            "argv",
            ["claugs", "show", "--search", "needle", "-l", str(tmp_path)],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "session-001.jsonl" in out
        assert "session-002.jsonl" not in out

    def test_search_no_matches_exits_cleanly(self, tmp_path, capsys):
        create_session_file(
            tmp_path,
            "session-001",
            [
                {
                    "type": "user",
                    "timestamp": "2026-03-17T14:00:00Z",
                    "message": {"content": "nothing relevant"},
                },
            ],
        )
        with patch.object(
            sys,
            "argv",
            ["claugs", "show", "--search", "xyznotfound", "-l", str(tmp_path)],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert out.strip() == ""


class TestSearchRenderMode:
    def test_search_renders_output_by_default(self, tmp_path, capsys):
        """Default behavior with --search is to render (no -l flag)."""
        create_session_file(
            tmp_path,
            "session-001",
            [
                {
                    "type": "user",
                    "uuid": "a",
                    "timestamp": "2026-03-17T14:00:00Z",
                    "message": {"content": "find the needle"},
                },
            ],
        )
        with patch.object(
            sys,
            "argv",
            [
                "claugs",
                "show",
                "--search",
                "needle",
                "--hide-timestamps",
                str(tmp_path),
            ],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "find the needle" in out


class TestSearchComposability:
    def test_search_with_session_is_composable(self, tmp_path, capsys):
        """--search + --session should work (no longer an error)."""
        # This combination filters the session file by search text.
        # Since we can't easily create a session in ~/.claude/projects,
        # we test that it doesn't error with "cannot combine".
        # A missing session is expected.
        with patch.object(
            sys,
            "argv",
            ["claugs", "show", "--search", "text", "--session", "nonexistent-uuid"],
        ):
            code = main()
        assert code != 0
        err = capsys.readouterr().err
        # Should fail with "session not found", not "cannot combine"
        assert "session not found" in err.lower()
        assert "cannot combine" not in err.lower()
