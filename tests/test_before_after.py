"""Tests for --before/--after CLI flags and directory scanning."""

import sys
from unittest.mock import patch

from claude_stream.cli import main
from conftest import create_session_file


class TestBeforeAfterFlags:
    def test_after_flag_parses(self, tmp_path, capsys):
        create_session_file(
            tmp_path,
            "session-001",
            [
                {
                    "type": "user",
                    "uuid": "a",
                    "timestamp": "2026-03-17T10:00:00Z",
                    "message": {"content": "morning message"},
                },
                {
                    "type": "user",
                    "uuid": "b",
                    "timestamp": "2026-03-17T20:00:00Z",
                    "message": {"content": "evening message"},
                },
            ],
        )
        with patch.object(
            sys,
            "argv",
            [
                "claude-stream",
                "--after",
                "2026-03-17T15:00:00",
                "--hide-timestamps",
                str(tmp_path / "session-001.jsonl"),
            ],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "evening message" in out
        assert "morning message" not in out


class TestDirectoryMode:
    def test_directory_with_after_scans_files(self, tmp_path, capsys):
        create_session_file(
            tmp_path,
            "session-001",
            [
                {
                    "type": "user",
                    "uuid": "a",
                    "timestamp": "2026-03-17T14:00:00Z",
                    "message": {"content": "matching message"},
                },
            ],
        )
        create_session_file(
            tmp_path,
            "session-002",
            [
                {
                    "type": "user",
                    "uuid": "b",
                    "timestamp": "2026-03-15T14:00:00Z",
                    "message": {"content": "old message"},
                },
            ],
        )
        with patch.object(
            sys,
            "argv",
            [
                "claude-stream",
                "--after",
                "2026-03-16",
                "--hide-timestamps",
                str(tmp_path),
            ],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "matching message" in out
        assert "old message" not in out


class TestSearchWithTimeFilter:
    def test_search_combined_with_after(self, tmp_path, capsys):
        create_session_file(
            tmp_path,
            "session-001",
            [
                {
                    "type": "user",
                    "uuid": "a",
                    "timestamp": "2026-03-17T14:00:00Z",
                    "message": {"content": "needle in recent session"},
                },
            ],
        )
        create_session_file(
            tmp_path,
            "session-002",
            [
                {
                    "type": "user",
                    "uuid": "b",
                    "timestamp": "2026-03-10T14:00:00Z",
                    "message": {"content": "needle in old session"},
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
                "--after",
                "2026-03-15",
                str(tmp_path),
            ],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "session-001.jsonl" in out
        assert "session-002.jsonl" not in out
