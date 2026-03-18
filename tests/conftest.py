"""Shared fixtures for claude-stream tests."""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path


@pytest.fixture
def sample_assistant_message():
    """A minimal assistant message with timestamp."""
    return {
        "type": "assistant",
        "uuid": "abc-123",
        "timestamp": "2026-03-17T14:23:05.000Z",
        "sessionId": "session-001",
        "isSidechain": False,
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "Hello world"}],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        },
    }


@pytest.fixture
def sample_user_message():
    """A minimal user input message with timestamp."""
    return {
        "type": "user",
        "uuid": "def-456",
        "timestamp": "2026-03-17T14:23:12.000Z",
        "sessionId": "session-001",
        "userType": "external",
        "message": {"role": "user", "content": "What is 2+2?"},
    }


@pytest.fixture
def sample_system_init_message():
    """A system init message with timestamp."""
    return {
        "type": "system",
        "uuid": "ghi-789",
        "timestamp": "2026-03-17T14:22:58.000Z",
        "sessionId": "session-001",
        "subtype": "init",
        "model": "claude-sonnet-4-5-20250514",
        "claude_code_version": "1.0.0",
        "cwd": "/home/user/project",
    }


@pytest.fixture
def sample_tool_result_message():
    """A user message that is a tool result (no header)."""
    return {
        "type": "user",
        "uuid": "jkl-012",
        "timestamp": "2026-03-17T14:23:15.000Z",
        "sessionId": "session-001",
        "toolUseResult": {"tool_use_id": "tool-1"},
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tool-1",
                    "content": "file contents here",
                }
            ],
        },
    }


@pytest.fixture
def sample_result_message():
    """A session result message."""
    return {
        "type": "result",
        "uuid": "mno-345",
        "timestamp": "2026-03-17T14:30:00.000Z",
        "sessionId": "session-001",
        "subtype": "success",
        "total_cost_usd": 0.05,
        "duration_ms": 420000,
        "num_turns": 10,
        "usage": {"input_tokens": 5000, "output_tokens": 2000},
    }


@pytest.fixture
def sample_message_no_timestamp():
    """A message without a timestamp field."""
    return {
        "type": "assistant",
        "uuid": "pqr-678",
        "sessionId": "session-001",
        "isSidechain": False,
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "No timestamp here"}],
        },
    }


@pytest.fixture
def sample_jsonl_lines(
    sample_system_init_message,
    sample_user_message,
    sample_assistant_message,
    sample_tool_result_message,
    sample_result_message,
):
    """Multiple JSONL lines as a list of strings."""
    messages = [
        sample_system_init_message,
        sample_user_message,
        sample_assistant_message,
        sample_tool_result_message,
        sample_result_message,
    ]
    return [json.dumps(m) + "\n" for m in messages]


@pytest.fixture
def tmp_jsonl_file(tmp_path, sample_jsonl_lines):
    """A temporary JSONL file with sample messages."""
    f = tmp_path / "session.jsonl"
    f.write_text("".join(sample_jsonl_lines))
    return f


def create_session_file(directory, session_id, messages):
    """Create a JSONL file with given messages. Not a fixture — call directly in tests."""
    f = directory / f"{session_id}.jsonl"
    lines = [json.dumps(m) + "\n" for m in messages]
    f.write_text("".join(lines))
    return f


@pytest.fixture
def fixtures_dir():
    """Path to the JSONL test fixtures directory."""
    return Path(__file__).parent / "fixtures"
