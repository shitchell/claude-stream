"""Tests for grouped rendering (pass 2)."""

import json
from pathlib import Path

from claude_stream.grouping import FileHandle, render_grouped
from claude_stream.formatters import PlainFormatter
from claude_stream.models import GroupByConfig, RenderConfig


def _write_jsonl(path: Path, messages: list[dict]) -> Path:
    path.write_text("".join(json.dumps(m) + "\n" for m in messages))
    return path


class TestRenderGroupedProjectOnly:
    def test_groups_files_by_project(self, tmp_path, capsys):
        proj_a = tmp_path / "proj-a"
        proj_b = tmp_path / "proj-b"
        proj_a.mkdir()
        proj_b.mkdir()

        _write_jsonl(proj_a / "s1.jsonl", [
            {"type": "user", "uuid": "1", "timestamp": "2026-03-17T14:00:00Z", "message": {"content": "proj-a msg"}},
        ])
        _write_jsonl(proj_b / "s2.jsonl", [
            {"type": "user", "uuid": "2", "timestamp": "2026-03-17T15:00:00Z", "message": {"content": "proj-b msg"}},
        ])

        handles = [
            FileHandle(path=proj_a / "s1.jsonl", offset=0, project="proj-a"),
            FileHandle(path=proj_b / "s2.jsonl", offset=0, project="proj-b"),
        ]
        config = RenderConfig(show_timestamps=False)
        group_config = GroupByConfig(by_project=True)
        formatter = PlainFormatter()

        render_grouped(handles, config, group_config, formatter)

        out = capsys.readouterr().out
        assert "proj-a" in out
        assert "proj-b" in out
        assert "proj-a msg" in out
        assert "proj-b msg" in out
        assert out.index("proj-a") < out.index("proj-b")


class TestRenderGroupedNoGrouping:
    def test_renders_files_sequentially(self, tmp_path, capsys):
        _write_jsonl(tmp_path / "s1.jsonl", [
            {"type": "user", "uuid": "1", "timestamp": "2026-03-17T14:00:00Z", "message": {"content": "file1 msg"}},
        ])
        _write_jsonl(tmp_path / "s2.jsonl", [
            {"type": "user", "uuid": "2", "timestamp": "2026-03-17T15:00:00Z", "message": {"content": "file2 msg"}},
        ])

        handles = [
            FileHandle(path=tmp_path / "s1.jsonl", offset=0, project="proj"),
            FileHandle(path=tmp_path / "s2.jsonl", offset=0, project="proj"),
        ]
        config = RenderConfig(show_timestamps=False)
        group_config = GroupByConfig()
        formatter = PlainFormatter()

        render_grouped(handles, config, group_config, formatter)

        out = capsys.readouterr().out
        assert "file1 msg" in out
        assert "file2 msg" in out
