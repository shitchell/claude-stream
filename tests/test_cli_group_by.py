"""Tests for --group-by CLI flag and integration."""

import sys
from unittest.mock import patch

from claude_logs.cli import main, parse_args
from conftest import create_session_file


class TestGroupByFlagParsing:
    def test_group_by_default_is_none(self):
        with patch.object(sys, "argv", ["claugs", "show", "--latest"]):
            _, args = parse_args()
        assert args.group_by is None

    def test_group_by_project(self):
        with patch.object(
            sys, "argv", ["claugs", "show", "--latest", "--group-by", "project"]
        ):
            _, args = parse_args()
        assert args.group_by == "project"

    def test_group_by_time(self):
        with patch.object(
            sys,
            "argv",
            ["claugs", "show", "--latest", "--group-by", "time:%Y%m%d%H"],
        ):
            _, args = parse_args()
        assert args.group_by == "time:%Y%m%d%H"


class TestGroupByWithWatch:
    def test_group_by_not_on_watch(self):
        """watch subcommand does not have --group-by."""
        with patch.object(
            sys,
            "argv",
            ["claugs", "watch", "/tmp", "--group-by", "project"],
        ):
            # watch parser should reject --group-by
            import pytest

            with pytest.raises(SystemExit):
                parse_args()


class TestGroupByDirectoryMode:
    def test_project_grouping_shows_headers(self, tmp_path, capsys):
        proj_a = tmp_path / "proj-a"
        proj_b = tmp_path / "proj-b"
        proj_a.mkdir()
        proj_b.mkdir()

        create_session_file(
            proj_a,
            "s1",
            [
                {
                    "type": "user",
                    "uuid": "1",
                    "timestamp": "2026-03-17T14:00:00Z",
                    "message": {"content": "from A"},
                },
            ],
        )
        create_session_file(
            proj_b,
            "s2",
            [
                {
                    "type": "user",
                    "uuid": "2",
                    "timestamp": "2026-03-17T15:00:00Z",
                    "message": {"content": "from B"},
                },
            ],
        )

        with patch.object(
            sys,
            "argv",
            [
                "claugs",
                "show",
                "--group-by",
                "project",
                "--hide-timestamps",
                str(tmp_path),
            ],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "proj-a" in out
        assert "proj-b" in out
        assert "from A" in out
        assert "from B" in out

    def test_time_grouping_interleaves(self, tmp_path, capsys):
        create_session_file(
            tmp_path,
            "s1",
            [
                {
                    "type": "user",
                    "uuid": "a1",
                    "timestamp": "2026-03-17T14:01:00Z",
                    "message": {"content": "s1 hour14"},
                },
            ],
        )
        create_session_file(
            tmp_path,
            "s2",
            [
                {
                    "type": "user",
                    "uuid": "b1",
                    "timestamp": "2026-03-17T14:02:00Z",
                    "message": {"content": "s2 hour14"},
                },
                {
                    "type": "user",
                    "uuid": "b2",
                    "timestamp": "2026-03-17T15:05:00Z",
                    "message": {"content": "s2 hour15"},
                },
            ],
        )

        with patch.object(
            sys,
            "argv",
            [
                "claugs",
                "show",
                "--group-by",
                "time:%Y%m%d%H",
                "--hide-timestamps",
                str(tmp_path),
            ],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "s1 hour14" in out
        assert "s2 hour14" in out
        assert "s2 hour15" in out
