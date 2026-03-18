"""Tests for --search mode."""

import sys
from unittest.mock import patch

from claude_stream.cli import main
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
            ["claude-stream", "--search", "needle", str(tmp_path)],
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
            ["claude-stream", "--search", "xyznotfound", str(tmp_path)],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert out.strip() == ""


class TestSearchStreamMode:
    def test_search_stream_renders_output(self, tmp_path, capsys):
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
                "claude-stream",
                "--search",
                "needle",
                "--stream",
                "--hide-timestamps",
                str(tmp_path),
            ],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "find the needle" in out


class TestSearchMutualExclusivity:
    def test_search_with_session_is_error(self, tmp_path, capsys):
        with patch.object(
            sys,
            "argv",
            ["claude-stream", "--search", "text", "--session", "abc-123"],
        ):
            code = main()
        assert code != 0
        err = capsys.readouterr().err
        assert "cannot combine" in err.lower()

    def test_search_with_latest_is_error(self, tmp_path, capsys):
        with patch.object(
            sys,
            "argv",
            ["claude-stream", "--search", "text", "--latest"],
        ):
            code = main()
        assert code != 0
        err = capsys.readouterr().err
        assert "cannot combine" in err.lower()
