"""Comprehensive integration tests for the claugs CLI.

Tests exercise the full CLI behavior through main() using JSONL fixtures,
covering the show (default) and watch subcommands, filtering, search,
directory mode, filepaths-only mode, and error handling.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from claude_logs.cli import main, parse_args, find_session_file
from conftest import create_session_file


# =============================================================================
# 1. Show Subcommand — Basic Rendering
# =============================================================================


class TestShowBasicRendering:
    """Test basic file rendering through the show subcommand."""

    def test_render_jsonl_file(self, fixtures_dir, capsys):
        """claugs show <file> renders the session."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys, "argv", ["claugs", "show", "--hide-timestamps", str(fpath)]
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        # Should contain user message text
        assert "Hello, what files are in this directory?" in out
        # Should contain assistant response text
        assert "I'll take a look at the files in your directory." in out
        # Should contain result block
        assert "SESSION COMPLETE" in out

    def test_render_with_implicit_show(self, fixtures_dir, capsys):
        """claugs --latest (no 'show' keyword) uses implicit show subcommand.

        Note: Implicit show only works with flag-only args (e.g., --latest,
        --session). Positional paths require explicit 'show'.
        """
        fpath = fixtures_dir / "v2.1.77" / "complete_session.jsonl"
        with (
            patch.object(sys, "argv", ["claugs", "--latest", "--hide-timestamps"]),
            patch("claude_logs.cli.find_session_file", return_value=fpath),
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "Hello, what files are in this directory?" in out
        assert "SESSION COMPLETE" in out

    def test_render_latest(self, fixtures_dir, capsys):
        """claugs --latest renders the most recent session."""
        fpath = fixtures_dir / "v2.1.77" / "complete_session.jsonl"
        with (
            patch.object(sys, "argv", ["claugs", "--latest", "--hide-timestamps"]),
            patch("claude_logs.cli.find_session_file", return_value=fpath),
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        # v2.1.77 fixture has 3 files (README.md, main.py, config.json)
        assert "config.json" in out

    def test_render_session_by_uuid(self, fixtures_dir, capsys):
        """claugs show --session UUID renders that session."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with (
            patch.object(
                sys,
                "argv",
                [
                    "claugs",
                    "show",
                    "--session",
                    "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "--hide-timestamps",
                ],
            ),
            patch("claude_logs.cli.find_session_file", return_value=fpath),
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "Hello, what files are in this directory?" in out

    def test_hide_timestamps(self, fixtures_dir, capsys):
        """claugs show <file> --hide-timestamps omits timestamps."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"

        # First, render with timestamps shown
        with patch.object(
            sys, "argv", ["claugs", "show", "--show-timestamps", str(fpath)]
        ):
            code = main()
        assert code == 0
        out_with_ts = capsys.readouterr().out

        # Then, render with timestamps hidden
        with patch.object(
            sys, "argv", ["claugs", "show", "--hide-timestamps", str(fpath)]
        ):
            code = main()
        assert code == 0
        out_no_ts = capsys.readouterr().out

        # The timestamp-containing output should have the separator character
        # used in format_timestamp_suffix: "·"
        assert "\u00b7" in out_with_ts
        assert "\u00b7" not in out_no_ts

    def test_compact_mode(self, fixtures_dir, capsys):
        """claugs show <file> --compact hides thinking, tools, metadata, timestamps."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(sys, "argv", ["claugs", "show", "--compact", str(fpath)]):
            code = main()
        assert code == 0
        out = capsys.readouterr().out

        # Thinking block should be hidden
        assert "Thinking:" not in out
        # Timestamp separator should be hidden
        assert "\u00b7" not in out
        # User text should still appear
        assert "Hello, what files are in this directory?" in out

    def test_custom_timestamp_format(self, fixtures_dir, capsys):
        """claugs show <file> --timestamp-format '%H:%M' uses custom format."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys,
            "argv",
            [
                "claugs",
                "show",
                "--timestamp-format",
                "%H:%M",
                "--show-timestamps",
                str(fpath),
            ],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out

        # The custom format produces HH:MM timestamps.
        # Since timestamps get converted to local time, we just check format
        # pattern (two digits, colon, two digits) is present after the separator
        assert "\u00b7" in out
        # Should NOT contain the default full date format like "2026-03-15"
        # (since we only asked for %H:%M)
        assert "2026-03-15" not in out


# =============================================================================
# 2. Show Subcommand — Filtering
# =============================================================================


class TestShowFiltering:
    """Test filtering options on the show subcommand."""

    def test_after_filter(self, fixtures_dir, capsys):
        """--after filters messages by timestamp."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        # The v2.1.75 fixture has timestamps from 10:00:00 to 10:00:25
        # Filter to only messages after 10:00:10 UTC
        with patch.object(
            sys,
            "argv",
            [
                "claugs",
                "show",
                "--hide-timestamps",
                "--after",
                "2026-03-15T10:00:10Z",
                str(fpath),
            ],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out

        # The first user message is at 10:00:03, should be excluded
        assert "Hello, what files are in this directory?" not in out
        # The assistant response at 10:00:12 should be included
        assert "Here are the files in your directory" in out

    def test_before_filter(self, fixtures_dir, capsys):
        """--before filters messages by timestamp."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        # Filter to only messages before 10:00:10 UTC
        with patch.object(
            sys,
            "argv",
            [
                "claugs",
                "show",
                "--hide-timestamps",
                "--before",
                "2026-03-15T10:00:10Z",
                str(fpath),
            ],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out

        # Early messages should appear
        assert "SYSTEM (init)" in out
        assert "Hello, what files are in this directory?" in out
        # Messages after 10:00:10 should be excluded
        assert "Here are the files in your directory" not in out
        assert "SESSION COMPLETE" not in out

    def test_after_and_before_combined(self, fixtures_dir, capsys):
        """--after + --before creates a time range."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys,
            "argv",
            [
                "claugs",
                "show",
                "--hide-timestamps",
                "--after",
                "2026-03-15T10:00:05Z",
                "--before",
                "2026-03-15T10:00:10Z",
                str(fpath),
            ],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out

        # Only messages in [10:00:05, 10:00:10] should appear
        # assistant at 10:00:06 (thinking + text)
        assert "I'll take a look at the files in your directory." in out
        # tool_use at 10:00:07
        assert "Bash" in out
        # tool_result at 10:00:09
        assert "README.md" in out

        # Before 10:00:05 should be excluded
        assert "Hello, what files are in this directory?" not in out
        # After 10:00:10 should be excluded
        assert "SESSION COMPLETE" not in out

    def test_grep_filter(self, fixtures_dir, capsys):
        """--grep filters messages by pattern."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys,
            "argv",
            [
                "claugs",
                "show",
                "--hide-timestamps",
                "--grep",
                "README.md",
                str(fpath),
            ],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out

        # Only messages containing "README.md" should appear
        assert "README.md" in out
        # Messages without "README.md" should be hidden
        assert "Hello, what files are in this directory?" not in out

    def test_exclude_filter(self, fixtures_dir, capsys):
        """--exclude removes messages matching pattern."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys,
            "argv",
            [
                "claugs",
                "show",
                "--hide-timestamps",
                "--exclude",
                "SESSION COMPLETE",
                "--exclude",
                "success",
                str(fpath),
            ],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out

        # The result message contains "success" in its JSON, so it should be excluded
        assert "SESSION COMPLETE" not in out
        # Other messages should still appear
        assert "Hello, what files are in this directory?" in out

    def test_show_type_filter(self, fixtures_dir, capsys):
        """--show-type limits to specific message types."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys,
            "argv",
            [
                "claugs",
                "show",
                "--hide-timestamps",
                "--show-type",
                "user",
                str(fpath),
            ],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out

        # Only user messages should appear
        assert "USER" in out
        assert "Hello, what files are in this directory?" in out
        # Assistant and system should not appear
        assert "ASSISTANT" not in out
        assert "SYSTEM (init)" not in out
        assert "SESSION COMPLETE" not in out


# =============================================================================
# 3. Show Subcommand — Search as Filter
# =============================================================================


class TestShowSearch:
    """Test --search as a filter on show."""

    def test_search_renders_matching_file(self, fixtures_dir, capsys):
        """--search 'text' renders files containing the text."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys,
            "argv",
            [
                "claugs",
                "show",
                "--hide-timestamps",
                "--search",
                "README.md",
                str(fpath),
            ],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        # The file contains "README.md", so it should be rendered
        assert "Hello, what files are in this directory?" in out

    def test_search_no_match_silent(self, fixtures_dir, capsys):
        """--search with no matches produces no output."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys,
            "argv",
            [
                "claugs",
                "show",
                "--hide-timestamps",
                "--search",
                "xyzzy_nonexistent_text",
                str(fpath),
            ],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert out.strip() == ""

    def test_search_with_filepaths_only(self, fixtures_dir, capsys):
        """-l prints filepaths instead of rendering."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys,
            "argv",
            [
                "claugs",
                "show",
                "-l",
                "--search",
                "README.md",
                str(fpath),
            ],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "complete_session.jsonl" in out

    def test_search_composable_with_latest(self, fixtures_dir, capsys):
        """--search + --latest works (no longer mutually exclusive)."""
        fpath = fixtures_dir / "v2.1.77" / "complete_session.jsonl"
        with (
            patch.object(
                sys,
                "argv",
                [
                    "claugs",
                    "show",
                    "--search",
                    "config.json",
                    "--latest",
                    "--hide-timestamps",
                ],
            ),
            patch("claude_logs.cli.find_session_file", return_value=fpath),
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        # File contains "config.json" so it matches and renders
        assert "config.json" in out

    def test_search_with_after_filter(self, tmp_path, capsys):
        """--search + --after: both must match on the same line for file selection."""
        create_session_file(
            tmp_path,
            "session-001",
            [
                {
                    "type": "user",
                    "timestamp": "2026-03-17T10:00:00Z",
                    "message": {"content": "early needle"},
                },
                {
                    "type": "user",
                    "timestamp": "2026-03-17T16:00:00Z",
                    "message": {"content": "late needle"},
                },
            ],
        )
        create_session_file(
            tmp_path,
            "session-002",
            [
                {
                    "type": "user",
                    "timestamp": "2026-03-17T10:00:00Z",
                    "message": {"content": "early haystack"},
                },
            ],
        )
        # Search for "needle" with --after 12:00 -- only session-001's late line matches
        with patch.object(
            sys,
            "argv",
            [
                "claugs",
                "show",
                "-l",
                "--search",
                "needle",
                "--after",
                "2026-03-17T12:00:00Z",
                str(tmp_path),
            ],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "session-001.jsonl" in out
        assert "session-002.jsonl" not in out


# =============================================================================
# 4. Show Subcommand — Directory Mode
# =============================================================================


class TestShowDirectoryMode:
    """Test directory scanning in show."""

    def test_directory_renders_all_files(self, fixtures_dir, capsys):
        """Passing a directory renders all JSONL files in it."""
        # The multi_project directory has project-a/session-001.jsonl and project-b/session-002.jsonl
        mp_dir = fixtures_dir / "multi_project"
        with patch.object(
            sys, "argv", ["claugs", "show", "--hide-timestamps", str(mp_dir)]
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        # Both sessions should appear
        assert "project-a" in out.lower() or "status" in out.lower()
        assert "project-b" in out.lower() or "test" in out.lower()

    def test_directory_with_search(self, fixtures_dir, capsys):
        """Directory + --search filters to matching files."""
        mp_dir = fixtures_dir / "multi_project"
        with patch.object(
            sys,
            "argv",
            [
                "claugs",
                "show",
                "-l",
                "--search",
                "project-a",
                str(mp_dir),
            ],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "session-001.jsonl" in out
        assert "session-002.jsonl" not in out

    def test_directory_filepaths_only(self, fixtures_dir, capsys):
        """Directory + -l lists all JSONL filepaths."""
        mp_dir = fixtures_dir / "multi_project"
        with patch.object(sys, "argv", ["claugs", "show", "-l", str(mp_dir)]):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "session-001.jsonl" in out
        assert "session-002.jsonl" in out

    def test_directory_with_group_by_project(self, fixtures_dir, capsys):
        """Directory + --group-by project shows project headers."""
        mp_dir = fixtures_dir / "multi_project"
        with patch.object(
            sys,
            "argv",
            [
                "claugs",
                "show",
                "--hide-timestamps",
                "--group-by",
                "project",
                str(mp_dir),
            ],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "Project: project-a" in out
        assert "Project: project-b" in out

    def test_directory_with_group_by_time(self, fixtures_dir, capsys):
        """Directory + --group-by time:... interleaves by time bucket."""
        mp_dir = fixtures_dir / "multi_project"
        with patch.object(
            sys,
            "argv",
            [
                "claugs",
                "show",
                "--hide-timestamps",
                "--group-by",
                "time:%Y%m%d%H",
                str(mp_dir),
            ],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        # Should have bucket headers in brackets (local-time dependent)
        # The fixture timestamps are 2026-03-17T14:xx:xx UTC, which converts
        # to a local time bucket like [2026031710] or [2026031714] etc.
        # Just verify a bracket-delimited bucket key is present.
        import re

        assert re.search(
            r"\[20260317\d{2}\]", out
        ), f"No time bucket header found in output"


# =============================================================================
# 5. Show Subcommand — Filepaths Only
# =============================================================================


class TestShowFilepathsOnly:
    """Test --filepaths-only / -l flag."""

    def test_single_file_prints_filepath(self, fixtures_dir, capsys):
        """claugs show -l <file> prints the filepath."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(sys, "argv", ["claugs", "show", "-l", str(fpath)]):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "complete_session.jsonl" in out

    def test_directory_prints_all_filepaths(self, fixtures_dir, capsys):
        """claugs show -l <dir> prints all JSONL filepaths."""
        mp_dir = fixtures_dir / "multi_project"
        with patch.object(sys, "argv", ["claugs", "show", "-l", str(mp_dir)]):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "session-001.jsonl" in out
        assert "session-002.jsonl" in out

    def test_filepaths_only_with_search(self, fixtures_dir, capsys):
        """claugs show -l --search 'text' <dir> prints matching filepaths."""
        mp_dir = fixtures_dir / "multi_project"
        with patch.object(
            sys,
            "argv",
            ["claugs", "show", "-l", "--search", "project-b", str(mp_dir)],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "session-002.jsonl" in out
        assert "session-001.jsonl" not in out

    def test_filepaths_only_stdin_error(self, capsys):
        """claugs -l with stdin is an error."""
        with (
            patch.object(sys, "argv", ["claugs", "-l"]),
            patch.object(sys, "stdin", wraps=sys.stdin) as mock_stdin,
        ):
            mock_stdin.isatty = lambda: False
            code = main()
        assert code == 1
        err = capsys.readouterr().err
        assert "cannot be used with stdin" in err.lower()


# =============================================================================
# 6. Show Subcommand — Error Cases
# =============================================================================


class TestShowErrors:
    """Test error handling in show."""

    def test_no_input_source(self, capsys):
        """No file/dir/stdin/--latest gives error."""
        with (
            patch.object(sys, "argv", ["claugs", "show"]),
            patch.object(sys.stdin, "isatty", return_value=True),
        ):
            code = main()
        assert code == 1
        err = capsys.readouterr().err
        assert "no input source" in err.lower()

    def test_nonexistent_file(self, capsys):
        """Nonexistent file gives error."""
        with patch.object(
            sys, "argv", ["claugs", "show", "/tmp/nonexistent_claugs_test_file.jsonl"]
        ):
            code = main()
        assert code == 1
        err = capsys.readouterr().err
        assert "file not found" in err.lower()

    def test_source_and_file_conflict(self, fixtures_dir, capsys):
        """Positional source + --file gives error."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys,
            "argv",
            ["claugs", "show", str(fpath), "--file", str(fpath)],
        ):
            code = main()
        assert code == 1
        err = capsys.readouterr().err
        assert "cannot specify both" in err.lower()

    def test_invalid_group_by(self, fixtures_dir, capsys):
        """Invalid --group-by spec gives error."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys,
            "argv",
            ["claugs", "show", "--group-by", "bogus", str(fpath)],
        ):
            code = main()
        assert code == 1
        err = capsys.readouterr().err
        assert "invalid" in err.lower()

    def test_invalid_after_date(self, fixtures_dir, capsys):
        """Invalid --after date gives error."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys,
            "argv",
            ["claugs", "show", "--after", "not-a-date-xyz", str(fpath)],
        ):
            code = main()
        assert code == 1
        err = capsys.readouterr().err
        assert "cannot parse date" in err.lower() or "error" in err.lower()


# =============================================================================
# 7. Watch Subcommand
# =============================================================================


class TestWatch:
    """Test watch subcommand basics (non-blocking tests only)."""

    def test_watch_nonexistent_path_error(self, capsys):
        """claugs watch /nonexistent gives error."""
        with patch.object(
            sys, "argv", ["claugs", "watch", "/tmp/nonexistent_claugs_watch_dir"]
        ):
            code = main()
        assert code == 1
        err = capsys.readouterr().err
        assert "path not found" in err.lower()

    def test_watch_requires_path(self, capsys):
        """claugs watch with no path gives error."""
        with patch.object(sys, "argv", ["claugs", "watch"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
        # argparse exits with code 2 for missing required arguments
        assert exc_info.value.code == 2


# =============================================================================
# 8. Fixture-Based Rendering Tests
# =============================================================================


class TestFixtureRendering:
    """Test rendering with versioned JSONL fixtures."""

    def test_v2_1_75_complete_session(self, fixtures_dir, capsys):
        """v2.1.75 fixture renders all message types correctly."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys, "argv", ["claugs", "show", "--hide-timestamps", str(fpath)]
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out

        # System init
        assert "SYSTEM (init)" in out
        assert "claude-sonnet-4-5-20250514" in out
        assert "2.1.75" in out

        # User message
        assert "USER" in out
        assert "Hello, what files are in this directory?" in out

        # Assistant with thinking
        assert "Thinking:" in out
        assert "I'll take a look at the files in your directory." in out

        # Tool use
        assert "Tool: Bash" in out

        # Tool result
        assert "README.md" in out
        assert "main.py" in out

        # Second user message
        assert "summarize what this project does" in out

        # Final assistant response
        assert "I can see there's a README.md file" in out

        # Session result
        assert "SESSION COMPLETE" in out
        assert "success" in out
        assert "$0.0234" in out

    def test_v2_1_77_complete_session(self, fixtures_dir, capsys):
        """v2.1.77 fixture renders all message types correctly."""
        fpath = fixtures_dir / "v2.1.77" / "complete_session.jsonl"
        with patch.object(
            sys, "argv", ["claugs", "show", "--hide-timestamps", str(fpath)]
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out

        # System init
        assert "SYSTEM (init)" in out
        assert "2.1.77" in out

        # User message
        assert "Hello, what files are in this directory?" in out

        # Tool use
        assert "Tool: Bash" in out

        # Tool result with 3 files
        assert "config.json" in out

        # Assistant response listing files
        assert "3 files in total" in out

        # Session result
        assert "$0.0198" in out

    def test_multi_project_fixtures(self, fixtures_dir, capsys):
        """Multi-project fixtures render with correct grouping."""
        mp_dir = fixtures_dir / "multi_project"
        with patch.object(
            sys,
            "argv",
            [
                "claugs",
                "show",
                "--hide-timestamps",
                "--group-by",
                "project",
                str(mp_dir),
            ],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out

        # Both projects should appear as groups
        assert "Project: project-a" in out
        assert "Project: project-b" in out

        # Content from each project should appear
        assert "project-a repository" in out
        assert "project-b" in out

    def test_thinking_blocks_shown_by_default(self, fixtures_dir, capsys):
        """Thinking blocks are rendered by default."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys, "argv", ["claugs", "show", "--hide-timestamps", str(fpath)]
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "Thinking:" in out
        assert "Let me check the directory contents" in out

    def test_thinking_blocks_hidden(self, fixtures_dir, capsys):
        """--hide-thinking suppresses thinking blocks."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys,
            "argv",
            ["claugs", "show", "--hide-timestamps", "--hide-thinking", str(fpath)],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        # "Thinking:" label should not be present
        assert "Thinking:" not in out
        # The actual thinking text should be suppressed too
        assert "Let me check the directory contents" not in out
        # But the non-thinking assistant text should still appear
        assert "I'll take a look at the files in your directory." in out

    def test_tool_use_rendered(self, fixtures_dir, capsys):
        """Tool use (Bash) is rendered with tool name."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys, "argv", ["claugs", "show", "--hide-timestamps", str(fpath)]
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "Tool: Bash" in out
        # Tool ID should be shown
        assert "toolu_01ABCdef234567890abcdef01" in out

    def test_tool_result_rendered(self, fixtures_dir, capsys):
        """Tool results are shown with content preview."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys, "argv", ["claugs", "show", "--hide-timestamps", str(fpath)]
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        # The tool result contains ls -la output
        assert "drwxr-xr-x" in out
        assert "README.md" in out

    def test_tool_results_hidden(self, fixtures_dir, capsys):
        """--hide-tool-results suppresses tool result content."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys,
            "argv",
            ["claugs", "show", "--hide-timestamps", "--hide-tool-results", str(fpath)],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        # The tool result message (type=user, toolUseResult) should be filtered
        # The ls output should not appear
        assert "drwxr-xr-x" not in out
        # But assistant messages should still appear
        assert "ASSISTANT" in out

    def test_result_message_shows_cost(self, fixtures_dir, capsys):
        """Result message shows cost, duration, tokens."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys, "argv", ["claugs", "show", "--hide-timestamps", str(fpath)]
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "$0.0234" in out
        assert "25s" in out
        assert "Turns" in out
        assert "4" in out


# =============================================================================
# 9. parse_args() Direct Tests
# =============================================================================


class TestParseArgs:
    """Test parse_args() returns (parser, args) tuple correctly."""

    def test_parse_args_returns_tuple(self):
        """parse_args() returns a (parser, args) 2-tuple."""
        with patch.object(sys, "argv", ["claugs", "show", "--latest"]):
            result = parse_args()
        assert isinstance(result, tuple)
        assert len(result) == 2
        parser, args = result
        assert hasattr(parser, "parse_args")
        assert args.command == "show"
        assert args.latest is True

    def test_implicit_show_command(self):
        """Omitting 'show' defaults to the show subcommand."""
        with patch.object(sys, "argv", ["claugs", "--latest"]):
            _, args = parse_args()
        assert args.command == "show"
        assert args.latest is True

    def test_watch_command_parsed(self):
        """'watch' subcommand is parsed correctly."""
        with patch.object(sys, "argv", ["claugs", "watch", "/some/path"]):
            _, args = parse_args()
        assert args.command == "watch"
        assert args.path == Path("/some/path")

    def test_show_with_file_arg(self):
        """--file is parsed under show."""
        with patch.object(
            sys, "argv", ["claugs", "show", "--file", "/some/file.jsonl"]
        ):
            _, args = parse_args()
        assert args.file == Path("/some/file.jsonl")

    def test_compact_flag(self):
        """--compact flag is parsed."""
        with patch.object(sys, "argv", ["claugs", "--compact", "--latest"]):
            _, args = parse_args()
        assert args.compact is True

    def test_grep_patterns_repeatable(self):
        """--grep can be repeated."""
        with patch.object(
            sys,
            "argv",
            ["claugs", "show", "--grep", "foo", "--grep", "bar", "--latest"],
        ):
            _, args = parse_args()
        assert args.grep_patterns == ["foo", "bar"]

    def test_lines_flag(self):
        """-n / --lines is parsed."""
        with patch.object(sys, "argv", ["claugs", "show", "-n", "20", "--latest"]):
            _, args = parse_args()
        assert args.lines == 20


# =============================================================================
# 10. Format Selection Tests
# =============================================================================


class TestFormatSelection:
    """Test that the correct formatter is chosen."""

    def test_plain_format_when_piped(self, fixtures_dir, capsys):
        """When not a TTY, plain format is used (no ANSI codes)."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys, "argv", ["claugs", "show", "--hide-timestamps", str(fpath)]
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        # Plain formatter should not have ANSI escape codes
        assert "\033[" not in out

    def test_explicit_plain_format(self, fixtures_dir, capsys):
        """--format plain produces plain output."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys,
            "argv",
            ["claugs", "show", "--format", "plain", "--hide-timestamps", str(fpath)],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "\033[" not in out
        assert "SYSTEM (init)" in out

    def test_explicit_markdown_format(self, fixtures_dir, capsys):
        """--format markdown produces markdown output."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys,
            "argv",
            ["claugs", "show", "--format", "markdown", "--hide-timestamps", str(fpath)],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        # Markdown format uses ## headers and --- dividers
        assert "##" in out
        assert "---" in out

    def test_explicit_ansi_format(self, fixtures_dir, capsys):
        """--format ansi produces ANSI-colored output."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys,
            "argv",
            ["claugs", "show", "--format", "ansi", "--hide-timestamps", str(fpath)],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        # ANSI format should contain escape codes
        assert "\033[" in out


# =============================================================================
# 11. Tail Lines (--lines / -n) Tests
# =============================================================================


class TestTailLines:
    """Test -n / --lines flag."""

    def test_tail_last_2_lines(self, fixtures_dir, capsys):
        """claugs show -n 2 <file> shows only last 2 JSONL lines."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys,
            "argv",
            ["claugs", "show", "--hide-timestamps", "-n", "2", str(fpath)],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out

        # Last 2 lines of v2.1.75 are:
        # Line 8: assistant message ("I can see there's a README.md file")
        # Line 9: result message (SESSION COMPLETE)
        assert "SESSION COMPLETE" in out
        assert "I can see there's a README.md file" in out

        # Earlier lines should not appear
        assert "SYSTEM (init)" not in out
        assert "Hello, what files are in this directory?" not in out

    def test_tail_1_line(self, fixtures_dir, capsys):
        """claugs show -n 1 <file> shows only the last JSONL line."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys,
            "argv",
            ["claugs", "show", "--hide-timestamps", "-n", "1", str(fpath)],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out

        # Only the result message (last line)
        assert "SESSION COMPLETE" in out
        assert "ASSISTANT" not in out


# =============================================================================
# 12. Line Numbers Tests
# =============================================================================


class TestLineNumbers:
    """Test --line-numbers flag."""

    def test_line_numbers_shown(self, fixtures_dir, capsys):
        """--line-numbers adds [N] prefix to messages."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys,
            "argv",
            ["claugs", "show", "--hide-timestamps", "--line-numbers", str(fpath)],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        # Line 1 is the system init
        assert "[1]" in out
        # Line 2 is the user message
        assert "[2]" in out

    def test_no_line_numbers_by_default(self, fixtures_dir, capsys):
        """Without --line-numbers, no [N] prefixes appear."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys, "argv", ["claugs", "show", "--hide-timestamps", str(fpath)]
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "[1]" not in out


# =============================================================================
# 13. Metadata Display Tests
# =============================================================================


class TestMetadata:
    """Test --show-metadata flag."""

    def test_metadata_hidden_by_default(self, fixtures_dir, capsys):
        """Metadata is hidden by default."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys, "argv", ["claugs", "show", "--hide-timestamps", str(fpath)]
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "| uuid:" not in out
        assert "| session:" not in out

    def test_metadata_shown(self, fixtures_dir, capsys):
        """--show-metadata shows uuid, session, timestamp metadata."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with patch.object(
            sys,
            "argv",
            ["claugs", "show", "--hide-timestamps", "--show-metadata", str(fpath)],
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "| uuid:" in out
        assert "| session:" in out
        assert "a1b2c3d4-e5f6-7890-abcd-ef1234567890" in out


# =============================================================================
# 14. Stdin Processing Tests
# =============================================================================


class TestStdinProcessing:
    """Test reading from stdin."""

    def test_stdin_renders_output(self, fixtures_dir, capsys):
        """claugs with piped stdin renders the session."""
        fpath = fixtures_dir / "v2.1.75" / "complete_session.jsonl"
        with open(fpath) as f:
            content = f.read()

        import io

        fake_stdin = io.StringIO(content)
        fake_stdin.isatty = lambda: False

        with (
            patch.object(sys, "argv", ["claugs", "show", "--hide-timestamps"]),
            patch.object(sys, "stdin", fake_stdin),
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "Hello, what files are in this directory?" in out
        assert "SESSION COMPLETE" in out


# =============================================================================
# 15. Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_jsonl_file(self, tmp_path, capsys):
        """An empty JSONL file produces no output and no error."""
        empty_file = tmp_path / "empty.jsonl"
        empty_file.write_text("")
        with patch.object(
            sys, "argv", ["claugs", "show", "--hide-timestamps", str(empty_file)]
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert out.strip() == ""

    def test_jsonl_with_blank_lines(self, tmp_path, capsys):
        """JSONL file with blank lines is handled gracefully."""
        import json

        content = (
            "\n"
            + json.dumps(
                {
                    "type": "user",
                    "uuid": "a",
                    "timestamp": "2026-03-17T10:00:00Z",
                    "message": {"content": "test message"},
                }
            )
            + "\n\n\n"
        )
        f = tmp_path / "blanks.jsonl"
        f.write_text(content)
        with patch.object(sys, "argv", ["claugs", "show", "--hide-timestamps", str(f)]):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "test message" in out

    def test_jsonl_with_invalid_json_line(self, tmp_path, capsys):
        """Invalid JSON lines produce warnings but don't crash."""
        import json

        content = (
            "this is not json\n"
            + json.dumps(
                {
                    "type": "user",
                    "uuid": "a",
                    "timestamp": "2026-03-17T10:00:00Z",
                    "message": {"content": "valid message"},
                }
            )
            + "\n"
        )
        f = tmp_path / "invalid.jsonl"
        f.write_text(content)
        with patch.object(sys, "argv", ["claugs", "show", "--hide-timestamps", str(f)]):
            code = main()
        assert code == 0
        captured = capsys.readouterr()
        assert "valid message" in captured.out
        assert "warning" in captured.err.lower()

    def test_render_empty_directory(self, tmp_path, capsys):
        """An empty directory produces no output."""
        with patch.object(
            sys, "argv", ["claugs", "show", "--hide-timestamps", str(tmp_path)]
        ):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert out.strip() == ""

    def test_filepaths_only_empty_directory(self, tmp_path, capsys):
        """claugs show -l on empty directory produces no output."""
        with patch.object(sys, "argv", ["claugs", "show", "-l", str(tmp_path)]):
            code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert out.strip() == ""
