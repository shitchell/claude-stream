"""Tests for file scouting (pass 1)."""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path

from claude_stream.grouping import FileHandle, scout_files
from claude_stream.models import RenderConfig


def _write_jsonl(path: Path, messages: list[dict]) -> Path:
    path.write_text("".join(json.dumps(m) + "\n" for m in messages))
    return path


class TestScoutFiles:
    def test_finds_files_with_no_time_filter(self, tmp_path):
        f = _write_jsonl(
            tmp_path / "session.jsonl",
            [{"type": "user", "timestamp": "2026-03-17T14:00:00Z", "message": {"content": "hi"}}],
        )
        config = RenderConfig()
        handles = scout_files([f], config)
        assert len(handles) == 1
        assert handles[0].path == f
        assert handles[0].offset == 0

    def test_skips_to_after_offset(self, tmp_path):
        msgs = [
            {"type": "user", "timestamp": "2026-03-17T10:00:00Z", "message": {"content": "old"}},
            {"type": "user", "timestamp": "2026-03-17T14:00:00Z", "message": {"content": "new"}},
        ]
        f = _write_jsonl(tmp_path / "session.jsonl", msgs)
        config = RenderConfig(after=datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc))
        handles = scout_files([f], config)
        assert len(handles) == 1
        assert handles[0].offset > 0

    def test_discards_file_with_no_matching_messages(self, tmp_path):
        f = _write_jsonl(
            tmp_path / "session.jsonl",
            [{"type": "user", "timestamp": "2026-03-17T10:00:00Z", "message": {"content": "old"}}],
        )
        config = RenderConfig(after=datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc))
        handles = scout_files([f], config)
        assert len(handles) == 0

    def test_extracts_project_name(self, tmp_path):
        project_dir = tmp_path / "-home-guy-myproject"
        project_dir.mkdir()
        f = _write_jsonl(
            project_dir / "session.jsonl",
            [{"type": "user", "timestamp": "2026-03-17T14:00:00Z", "message": {"content": "hi"}}],
        )
        config = RenderConfig()
        handles = scout_files([f], config)
        assert handles[0].project == "-home-guy-myproject"

    def test_tail_lines(self, tmp_path):
        msgs = [
            {"type": "user", "timestamp": f"2026-03-17T{h:02d}:00:00Z", "message": {"content": f"msg{h}"}}
            for h in range(10, 15)
        ]
        f = _write_jsonl(tmp_path / "session.jsonl", msgs)
        config = RenderConfig()
        handles = scout_files([f], config, tail_lines=2)
        assert len(handles) == 1
        assert handles[0].offset > 0
