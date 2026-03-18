# Search & Timestamps Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add timestamp display, text search across session files, and `--before`/`--after` timestamp filtering to claude-stream.

**Architecture:** Three features layered bottom-up: date parsing utility, then rendering changes (HeaderBlock suffix + timestamp display), then filtering (timestamp filter in should_show_message), then CLI integration (flags, search mode, directory scanning). A pre-existing `--compact` bug is fixed first since it affects how visibility flags work.

**Tech Stack:** Python 3.10+, Pydantic 2.0+, python-dateutil, pytest

**Spec:** `docs/superpowers/specs/2026-03-17-search-timestamps-design.md`

---

### Task 1: Project Setup

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/conftest.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Add python-dateutil dependency and test deps to pyproject.toml**

Add `python-dateutil>=2.8` to `dependencies` and a `[project.optional-dependencies] dev` section with `pytest`:

```toml
dependencies = [
    "pydantic>=2.0",
    "typing_extensions>=4.0",
    "python-dateutil>=2.8",
]

[project.optional-dependencies]
watch = [
    "watchdog>=3.0",
]
dev = [
    "pytest>=7.0",
]
```

- [ ] **Step 2: Create test directory with conftest and sample JSONL fixtures**

Create `tests/__init__.py` (empty) and `tests/conftest.py` with reusable fixtures:

```python
"""Shared fixtures for claude-stream tests."""

import json
import pytest
from datetime import datetime, timezone


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
```

- [ ] **Step 3: Verify pytest runs with no tests**

Run: `cd /home/guy/git/github.com/shitchell/claude-stream && pip install -e ".[dev]" && pytest tests/ -v`
Expected: "no tests ran" (exit 5), no import errors.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml tests/
git commit -m "chore: add test infrastructure and python-dateutil dependency"
```

---

### Task 2: Date Parsing Utility (`dateparse.py`)

**Files:**
- Create: `src/claude_stream/dateparse.py`
- Create: `tests/test_dateparse.py`

- [ ] **Step 1: Write failing tests for parse_datetime**

```python
"""Tests for dateparse module."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from claude_stream.dateparse import parse_datetime


class TestParseDatetimeISO:
    """Test ISO 8601 date parsing."""

    def test_date_only(self):
        result = parse_datetime("2026-03-17")
        assert result.year == 2026
        assert result.month == 3
        assert result.day == 17
        assert result.tzinfo is not None  # always timezone-aware

    def test_datetime_with_t(self):
        result = parse_datetime("2026-03-17T14:23:05")
        assert result.hour == 14
        assert result.minute == 23
        assert result.second == 5

    def test_datetime_with_z(self):
        result = parse_datetime("2026-03-17T14:23:05Z")
        assert result.tzinfo == timezone.utc


class TestParseDatetimeKeywords:
    """Test keyword substitutions."""

    @patch("claude_stream.dateparse._now")
    def test_today(self, mock_now):
        mock_now.return_value = datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
        result = parse_datetime("today")
        assert result.date() == datetime(2026, 3, 17).date()

    @patch("claude_stream.dateparse._now")
    def test_tomorrow(self, mock_now):
        mock_now.return_value = datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
        result = parse_datetime("tomorrow")
        assert result.date() == datetime(2026, 3, 18).date()

    @patch("claude_stream.dateparse._now")
    def test_noon(self, mock_now):
        mock_now.return_value = datetime(2026, 3, 17, 9, 0, 0, tzinfo=timezone.utc)
        result = parse_datetime("noon")
        assert result.hour == 12
        assert result.minute == 0

    @patch("claude_stream.dateparse._now")
    def test_midnight(self, mock_now):
        mock_now.return_value = datetime(2026, 3, 17, 9, 0, 0, tzinfo=timezone.utc)
        result = parse_datetime("midnight")
        assert result.hour == 0
        assert result.minute == 0


class TestParseDatetimeRelative:
    """Test relative time parsing."""

    @patch("claude_stream.dateparse._now")
    def test_now_minus_2h(self, mock_now):
        base = datetime(2026, 3, 17, 14, 0, 0, tzinfo=timezone.utc)
        mock_now.return_value = base
        result = parse_datetime("now -2h")
        assert result == base - timedelta(hours=2)

    @patch("claude_stream.dateparse._now")
    def test_plus_30m(self, mock_now):
        base = datetime(2026, 3, 17, 14, 0, 0, tzinfo=timezone.utc)
        mock_now.return_value = base
        result = parse_datetime("+30m")
        assert result == base + timedelta(minutes=30)

    @patch("claude_stream.dateparse._now")
    def test_5d(self, mock_now):
        base = datetime(2026, 3, 17, 14, 0, 0, tzinfo=timezone.utc)
        mock_now.return_value = base
        result = parse_datetime("5d")
        assert result == base + timedelta(days=5)

    @patch("claude_stream.dateparse._now")
    def test_minus_1w(self, mock_now):
        base = datetime(2026, 3, 17, 14, 0, 0, tzinfo=timezone.utc)
        mock_now.return_value = base
        result = parse_datetime("now -1w")
        assert result == base - timedelta(weeks=1)


class TestParseDatetimeNaturalLanguage:
    """Test natural language via dateutil."""

    def test_month_day_year(self):
        result = parse_datetime("March 17, 2026")
        assert result.year == 2026
        assert result.month == 3
        assert result.day == 17

    def test_always_timezone_aware(self):
        """All results must be timezone-aware."""
        result = parse_datetime("2026-01-01")
        assert result.tzinfo is not None


class TestParseDatetimeInvalid:
    """Test error handling."""

    def test_empty_string(self):
        with pytest.raises(ValueError):
            parse_datetime("")

    def test_gibberish(self):
        with pytest.raises(ValueError):
            parse_datetime("qqq zzz www")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/guy/git/github.com/shitchell/claude-stream && pytest tests/test_dateparse.py -v`
Expected: ImportError — `claude_stream.dateparse` does not exist yet.

- [ ] **Step 3: Write the dateparse module**

Create `src/claude_stream/dateparse.py`:

```python
"""Date/time parsing utility for human-friendly date strings.

Adapted from the countdown script's parse_timestring function.
Supports ISO dates, natural language, keywords, and relative times.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from dateutil.parser import parse as dateutil_parse


def _now() -> datetime:
    """Get current time (UTC). Separated for testability."""
    return datetime.now(timezone.utc)


# Keyword substitutions applied before dateutil parsing
def _get_substitutions() -> list[tuple[str, str]]:
    """Get keyword substitutions using local time (not UTC).

    Uses _now() as base so mocking works consistently in tests.
    """
    now = _now().astimezone()  # Convert UTC to local for "today"/"tomorrow"
    return [
        (r"\bnoon\b", "12:00"),
        (r"\bmidnight\b", "00:00"),
        (r"\btoday\b", now.strftime("%B %d, %Y")),
        (r"\btomorrow\b", (now + timedelta(days=1)).strftime("%B %d, %Y")),
    ]


# Regex for relative time: "now +/-N unit" or just "+/-N unit" or "N unit"
_RELATIVE_RE = re.compile(
    r"^(?:now\s+)?([+-])?\s*(\d+)\s*"
    r"(s|seconds?|m|minutes?|h|hrs?|hours?|d|days?|w|wks?|weeks?"
    r"|M|months?|y|yrs?|years?)$",
    # Note: NO re.IGNORECASE — "m" (minutes) vs "M" (months) is intentional
)

# Map unit strings to seconds
_UNIT_SECONDS: dict[str, int] = {}
for _names, _secs in [
    (("s", "second", "seconds"), 1),
    (("m", "minute", "minutes"), 60),
    (("h", "hr", "hrs", "hour", "hours"), 3600),
    (("d", "day", "days"), 86400),
    (("w", "wk", "wks", "week", "weeks"), 604800),
    (("M", "month", "months"), 2629743),
    (("y", "yr", "yrs", "year", "years"), 31556926),
]:
    for _name in _names:
        _UNIT_SECONDS[_name] = _secs


def _ensure_aware(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware (assume local time if naive)."""
    if dt.tzinfo is None:
        # Assume local time, convert to UTC
        local_dt = dt.astimezone()  # adds local tz
        return local_dt.astimezone(timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_datetime(text: str) -> datetime:
    """Parse a human-friendly date/time string into a timezone-aware datetime.

    Supports:
    - ISO dates: 2026-03-17, 2026-03-17T14:23:05, 2026-03-17T14:23:05Z
    - Natural language: March 17 2026, Monday at 5pm (via dateutil)
    - Keywords: noon, midnight, today, tomorrow
    - Relative times: now -2h, +30m, 5d, now +1w

    Returns:
        A timezone-aware datetime in UTC.

    Raises:
        ValueError: If the string cannot be parsed.
    """
    text = text.strip()
    if not text:
        raise ValueError("Empty date string")

    # Check for relative time pattern
    match = _RELATIVE_RE.match(text)
    if match:
        sign_str, num_str, unit = match.groups()
        sign = -1 if sign_str == "-" else 1
        seconds = int(num_str) * _UNIT_SECONDS.get(unit, 1)
        return _now() + timedelta(seconds=sign * seconds)

    # Apply keyword substitutions
    processed = text.lower()
    for keyword, substitution in _get_substitutions():
        processed = re.sub(keyword, substitution, processed, flags=re.IGNORECASE)

    # Parse with dateutil
    try:
        result = dateutil_parse(processed)
    except (ValueError, OverflowError) as e:
        raise ValueError(f"Cannot parse date: {text!r}") from e

    return _ensure_aware(result)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/guy/git/github.com/shitchell/claude-stream && pytest tests/test_dateparse.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/claude_stream/dateparse.py tests/test_dateparse.py
git commit -m "feat: add dateparse module with parse_datetime utility"
```

---

### Task 3: Fix `--compact` Override Bug

**Files:**
- Modify: `src/claude_stream/cli.py:136-142,174-195`
- Create: `tests/test_compact_bug.py`

- [ ] **Step 1: Write failing test that demonstrates the bug**

```python
"""Tests for --compact flag behavior."""

import sys
from unittest.mock import patch

from claude_stream.cli import parse_args


class TestCompactFlag:
    """Verify --compact sets visibility flags correctly."""

    def test_compact_hides_thinking(self):
        """--compact alone should hide thinking (currently broken)."""
        with patch.object(sys, "argv", ["claude-stream", "--compact", "--latest"]):
            args = parse_args()
        # After the fix, compact should yield these effective values
        assert args.compact is True
        # The individual flags should be None (not explicitly set)
        assert args.show_thinking is None

    def test_compact_with_explicit_override(self):
        """--compact --show-thinking should show thinking (explicit wins)."""
        with patch.object(
            sys, "argv", ["claude-stream", "--compact", "--show-thinking", "--latest"]
        ):
            args = parse_args()
        assert args.compact is True
        assert args.show_thinking is True

    def test_no_compact_defaults(self):
        """Without --compact, visibility flags should be None (use defaults)."""
        with patch.object(sys, "argv", ["claude-stream", "--latest"]):
            args = parse_args()
        assert args.compact is False
        assert args.show_thinking is None
        assert args.show_tool_results is None
        assert args.show_metadata is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/guy/git/github.com/shitchell/claude-stream && pytest tests/test_compact_bug.py -v`
Expected: FAIL — `args.show_thinking` is `True` (argparse default), not `None`.

- [ ] **Step 3: Fix the argparse defaults and config application in cli.py**

In `parse_args()`, change the visibility flag defaults from `True`/`False` to `None`:

```python
# Visibility controls — default=None so we can detect explicit vs. implicit
parser.add_argument("--show-thinking", dest="show_thinking", action="store_true", default=None)
parser.add_argument("--hide-thinking", dest="show_thinking", action="store_false")
parser.add_argument("--show-tool-results", dest="show_tool_results", action="store_true", default=None)
parser.add_argument("--hide-tool-results", dest="show_tool_results", action="store_false")
parser.add_argument("--show-metadata", dest="show_metadata", action="store_true", default=None)
parser.add_argument("--hide-metadata", dest="show_metadata", action="store_false")
```

In `main()`, replace the config application block with logic that respects `None` = "use default or compact":

```python
# Build config
config = RenderConfig()

# Apply --compact first (sets defaults that can be overridden)
if args.compact:
    config.show_metadata = False
    config.show_thinking = False
    config.show_tool_results = False
    config.show_types = {"assistant", "user"}

# Apply explicit visibility flags (override compact if set)
if args.show_thinking is not None:
    config.show_thinking = args.show_thinking
if args.show_tool_results is not None:
    config.show_tool_results = args.show_tool_results
if args.show_metadata is not None:
    config.show_metadata = args.show_metadata

# Note: show_line_numbers uses store_true (default=False), not the None pattern,
# because it's opt-in only — --compact doesn't affect it.
config.show_line_numbers = args.line_numbers
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/guy/git/github.com/shitchell/claude-stream && pytest tests/test_compact_bug.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/claude_stream/cli.py tests/test_compact_bug.py
git commit -m "fix: --compact flag no longer silently overridden by argparse defaults"
```

---

### Task 4: HeaderBlock Suffix + Formatter Updates

**Files:**
- Modify: `src/claude_stream/blocks.py:44-50`
- Modify: `src/claude_stream/formatters.py` (all three formatters' `_format_header`)
- Create: `tests/test_header_suffix.py`

- [ ] **Step 1: Write failing tests for HeaderBlock suffix rendering**

```python
"""Tests for HeaderBlock suffix rendering in all formatters."""

from claude_stream.blocks import HeaderBlock, Style
from claude_stream.formatters import ANSIFormatter, MarkdownFormatter, PlainFormatter


class TestHeaderSuffixANSI:
    def test_no_suffix(self):
        block = HeaderBlock(text="ASSISTANT", icon="▸", level=2)
        result = ANSIFormatter().format_block(block)
        assert "ASSISTANT" in result
        assert "·" not in result

    def test_with_suffix(self):
        block = HeaderBlock(
            text="ASSISTANT", icon="▸", level=2, suffix="· 2026-03-17 14:23:05"
        )
        result = ANSIFormatter().format_block(block)
        assert "ASSISTANT" in result
        assert "· 2026-03-17 14:23:05" in result
        # Suffix should have DIM styling (ANSI code \033[2m)
        assert "\033[2m" in result

    def test_suffix_is_dim_not_bold(self):
        block = HeaderBlock(
            text="ASSISTANT",
            icon="▸",
            level=2,
            suffix="· 2026-03-17 14:23:05",
            styles={Style.BOLD},
        )
        result = ANSIFormatter().format_block(block)
        # The suffix portion should use DIM, not inherit BOLD
        # Find the suffix in output — it should be wrapped in DIM
        suffix_start = result.index("·")
        before_suffix = result[:suffix_start]
        # The main text should have BOLD
        assert "\033[1m" in before_suffix


class TestHeaderSuffixMarkdown:
    def test_no_suffix(self):
        block = HeaderBlock(text="ASSISTANT", icon="▸", level=2)
        result = MarkdownFormatter().format_block(block)
        assert "ASSISTANT" in result
        assert "·" not in result

    def test_with_suffix(self):
        block = HeaderBlock(
            text="ASSISTANT", icon="▸", level=2, suffix="· 2026-03-17 14:23:05"
        )
        result = MarkdownFormatter().format_block(block)
        assert "· 2026-03-17 14:23:05" in result


class TestHeaderSuffixPlain:
    def test_no_suffix(self):
        block = HeaderBlock(text="ASSISTANT", level=2)
        result = PlainFormatter().format_block(block)
        assert "ASSISTANT" in result
        assert "·" not in result

    def test_with_suffix(self):
        block = HeaderBlock(
            text="ASSISTANT", level=2, suffix="· 2026-03-17 14:23:05"
        )
        result = PlainFormatter().format_block(block)
        assert "ASSISTANT" in result
        assert "· 2026-03-17 14:23:05" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/guy/git/github.com/shitchell/claude-stream && pytest tests/test_header_suffix.py -v`
Expected: FAIL — `HeaderBlock` has no `suffix` field yet.

- [ ] **Step 3: Add suffix field to HeaderBlock**

In `src/claude_stream/blocks.py`, add `suffix` to `HeaderBlock`:

```python
@dataclass
class HeaderBlock(RenderBlock):
    """A header/title block."""

    text: str = ""
    level: int = 1  # 1 = top level, 2 = subheader, etc.
    icon: str = ""  # Optional prefix icon
    prefix: str = ""  # Optional prefix text (e.g., "Summary:", "Tool:")
    suffix: str = ""  # Optional suffix text, styled independently (e.g., timestamp)
```

- [ ] **Step 4: Update ANSIFormatter._format_header to render suffix with DIM**

In `src/claude_stream/formatters.py`, update `ANSIFormatter._format_header`:

```python
def _format_header(self, block: HeaderBlock) -> str:
    parts = []
    if block.icon:
        parts.append(block.icon)
    if block.prefix:
        parts.append(block.prefix)
    parts.append(block.text)
    text = " ".join(parts)
    text = self._apply_styles(text, block.styles | {Style.BOLD})
    if block.suffix:
        text += self._apply_styles(f" {block.suffix}", {Style.DIM})
    return text
```

- [ ] **Step 5: Update MarkdownFormatter._format_header to render suffix**

```python
def _format_header(self, block: HeaderBlock) -> str:
    hashes = "#" * min(block.level, 6)
    # For level 1 (document title), use clean text only
    if block.level == 1:
        text = f"{hashes} {block.text}"
    else:
        # For other levels, include icon and prefix
        parts = []
        if block.icon:
            parts.append(block.icon)
        if block.prefix:
            parts.append(block.prefix)
        parts.append(block.text)
        text = f"{hashes} {' '.join(parts)}"
    if block.suffix:
        text += f" {block.suffix}"
    return text
```

- [ ] **Step 6: Update PlainFormatter._format_header to render suffix**

```python
def _format_header(self, block: HeaderBlock) -> str:
    parts = []
    if block.prefix:
        parts.append(block.prefix)
    parts.append(block.text)
    text = " ".join(parts)
    if block.suffix:
        text += f" {block.suffix}"
    return text
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /home/guy/git/github.com/shitchell/claude-stream && pytest tests/test_header_suffix.py -v`
Expected: All tests PASS.

- [ ] **Step 8: Commit**

```bash
git add src/claude_stream/blocks.py src/claude_stream/formatters.py tests/test_header_suffix.py
git commit -m "feat: add suffix field to HeaderBlock with DIM styling in ANSI"
```

---

### Task 5: Timestamp Display in Message Rendering

**Files:**
- Modify: `src/claude_stream/models.py:144-167` (RenderConfig) and render methods throughout
- Create: `tests/test_timestamp_display.py`

- [ ] **Step 1: Write failing tests for timestamp display**

```python
"""Tests for timestamp display in message rendering."""

from claude_stream.blocks import HeaderBlock, Style
from claude_stream.models import (
    AssistantMessage,
    QueueOperationMessage,
    RenderConfig,
    ResultMessage,
    SummaryMessage,
    SystemMessage,
    UserMessage,
    parse_message,
)


def _find_header(blocks) -> HeaderBlock | None:
    """Find the first HeaderBlock in a list of render blocks."""
    for b in blocks:
        if isinstance(b, HeaderBlock):
            return b
    return None


class TestTimestampInHeaders:
    """Timestamps appear as suffix on header blocks."""

    def test_assistant_message_has_timestamp_suffix(self, sample_assistant_message):
        config = RenderConfig(show_timestamps=True)
        msg = parse_message(sample_assistant_message)
        blocks = msg.render(config)
        header = _find_header(blocks)
        assert header is not None
        assert "· 2026-03-17 14:23:05" in header.suffix

    def test_user_message_has_timestamp_suffix(self, sample_user_message):
        config = RenderConfig(show_timestamps=True)
        msg = parse_message(sample_user_message)
        blocks = msg.render(config)
        header = _find_header(blocks)
        assert header is not None
        assert "· 2026-03-17 14:23:12" in header.suffix

    def test_system_message_has_timestamp_suffix(self, sample_system_init_message):
        config = RenderConfig(show_timestamps=True)
        msg = parse_message(sample_system_init_message)
        blocks = msg.render(config)
        header = _find_header(blocks)
        assert header is not None
        assert "· 2026-03-17 14:22:58" in header.suffix

    def test_result_message_has_timestamp_suffix(self, sample_result_message):
        config = RenderConfig(show_timestamps=True)
        msg = parse_message(sample_result_message)
        blocks = msg.render(config)
        # ResultMessage has a DividerBlock first, then a HeaderBlock
        headers = [b for b in blocks if isinstance(b, HeaderBlock)]
        assert any("· 2026-03-17 14:30:00" in h.suffix for h in headers)


class TestTimestampHidden:
    """When show_timestamps=False, no suffix."""

    def test_no_suffix_when_hidden(self, sample_assistant_message):
        config = RenderConfig(show_timestamps=False)
        msg = parse_message(sample_assistant_message)
        blocks = msg.render(config)
        header = _find_header(blocks)
        assert header is not None
        assert header.suffix == ""


class TestTimestampFormat:
    """Custom timestamp format string."""

    def test_custom_format(self, sample_assistant_message):
        config = RenderConfig(
            show_timestamps=True, timestamp_format="%H:%M"
        )
        msg = parse_message(sample_assistant_message)
        blocks = msg.render(config)
        header = _find_header(blocks)
        assert header is not None
        assert "· 14:23" in header.suffix


class TestTimestampMissing:
    """Messages without timestamps get no suffix."""

    def test_no_timestamp_no_suffix(self, sample_message_no_timestamp):
        config = RenderConfig(show_timestamps=True)
        msg = parse_message(sample_message_no_timestamp)
        blocks = msg.render(config)
        header = _find_header(blocks)
        assert header is not None
        assert header.suffix == ""


class TestToolResultNoTimestamp:
    """Tool result messages have no header, so no timestamp."""

    def test_tool_result_no_header(self, sample_tool_result_message):
        config = RenderConfig(show_timestamps=True, show_tool_results=True)
        msg = parse_message(sample_tool_result_message)
        blocks = msg.render(config)
        # Tool results produce Result/Error headers, not USER headers
        # The first HeaderBlock should be a Result header, not a timestamp-bearing one
        headers = [b for b in blocks if isinstance(b, HeaderBlock)]
        for h in headers:
            # These headers are for "Result"/"Error", not for the user message itself
            assert "USER" not in h.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/guy/git/github.com/shitchell/claude-stream && pytest tests/test_timestamp_display.py -v`
Expected: FAIL — `RenderConfig` has no `show_timestamps` field yet.

- [ ] **Step 3: Add show_timestamps and timestamp_format to RenderConfig**

In `src/claude_stream/models.py`, update `RenderConfig`:

```python
@dataclass
class RenderConfig:
    """Configuration for rendering messages."""

    show_thinking: bool = True
    show_tool_results: bool = True
    show_metadata: bool = False
    show_line_numbers: bool = False
    show_timestamps: bool = True
    timestamp_format: str = "%Y-%m-%d %H:%M:%S"

    # Filtering
    show_types: set[str] = field(
        default_factory=lambda: {
            "system",
            "assistant",
            "user",
            "summary",
            "queue-operation",
            "result",
        }
    )
    show_subtypes: set[str] = field(default_factory=set)
    show_tools: set[str] = field(default_factory=set)
    grep_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
```

- [ ] **Step 4: Add a timestamp suffix helper to BaseMessage**

In `src/claude_stream/models.py`, add `from datetime import datetime as _datetime` at the module-level imports (near the top, alongside the existing imports). Then add a helper method to `BaseMessage`:

```python
def format_timestamp_suffix(self, config: RenderConfig) -> str:
    """Format the timestamp as a header suffix string."""
    if not config.show_timestamps or not self.timestamp:
        return ""
    try:
        dt = _datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
        formatted = dt.strftime(config.timestamp_format)
        return f"· {formatted}"
    except (ValueError, OSError):
        return ""
```

- [ ] **Step 5: Update AgentStyleMessage.render_header() to include timestamp suffix**

In `src/claude_stream/models.py`, update `AgentStyleMessage.render_header()`:

```python
def render_header(self, config: RenderConfig) -> list[RenderBlock]:
    """Render the agent header."""
    return [
        HeaderBlock(
            text=self.get_agent_label(),
            icon=self.get_agent_icon(),
            level=2,
            styles={Style.ASSISTANT, Style.BOLD},
            suffix=self.format_timestamp_suffix(config),
        )
    ]
```

- [ ] **Step 6: Update UserMessage render methods to include timestamp suffix**

Update `render_user_input()` — change the HeaderBlock:

```python
label = "USER [meta]" if meta else "USER"
blocks.append(
    HeaderBlock(
        text=label,
        icon="◂",
        level=2,
        styles={Style.USER},
        suffix=self.format_timestamp_suffix(config),
    )
)
```

Update `render_subagent()` — change the HeaderBlock:

```python
blocks.append(
    HeaderBlock(
        text=f"SUB-AGENT ({agent_id})",
        icon="◆",
        level=2,
        styles={Style.ASSISTANT, Style.BOLD},
        suffix=self.format_timestamp_suffix(config),
    )
)
```

Update `render_local_command()` — change the `<command-name>` HeaderBlock:

```python
blocks.append(
    HeaderBlock(
        text=f"Command: {cmd_name}",
        icon="▸",
        level=3,
        styles={Style.USER},
        suffix=self.format_timestamp_suffix(config),
    )
)
```

- [ ] **Step 7: Update SystemMessage.render() to include timestamp suffix**

Change the HeaderBlock in `SystemMessage.render()`:

```python
blocks.append(
    HeaderBlock(
        text=f"SYSTEM ({self.subtype})",
        icon="▸",
        level=2,
        styles={Style.SYSTEM},
        suffix=self.format_timestamp_suffix(config),
    )
)
```

- [ ] **Step 8: Update remaining message types (FileHistorySnapshot, SummaryMessage, QueueOperationMessage, ResultMessage)**

`FileHistorySnapshot.render()`:
```python
def render(self, config: RenderConfig) -> list[RenderBlock]:
    timestamp = self.snapshot.get("timestamp", "unknown")
    return [
        HeaderBlock(
            text=f"File History Snapshot ({timestamp})",
            icon="📸",
            level=2,
            styles={Style.SYSTEM},
            suffix=self.format_timestamp_suffix(config),
        ),
        SpacerBlock(),
    ]
```

`SummaryMessage.render()`:
```python
def render(self, config: RenderConfig) -> list[RenderBlock]:
    return [
        HeaderBlock(
            text=self.summary,
            icon="📋",
            prefix="Summary:",
            level=1,
            styles={Style.INFO},
            suffix=self.format_timestamp_suffix(config),
        ),
        SpacerBlock(),
    ]
```

`QueueOperationMessage.render()` — change the HeaderBlock:
```python
blocks.append(
    HeaderBlock(
        text=f"Queue: {self.operation}",
        icon="⚙",
        level=2,
        styles={Style.SYSTEM},
        suffix=self.format_timestamp_suffix(config),
    )
)
```

`ResultMessage.render()` — change the "SESSION COMPLETE" HeaderBlock:
```python
blocks.append(
    HeaderBlock(
        text="SESSION COMPLETE",
        level=1,
        styles={Style.BOLD, Style.INFO},
        suffix=self.format_timestamp_suffix(config),
    )
)
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd /home/guy/git/github.com/shitchell/claude-stream && pytest tests/test_timestamp_display.py -v`
Expected: All tests PASS.

- [ ] **Step 10: Commit**

```bash
git add src/claude_stream/models.py tests/test_timestamp_display.py
git commit -m "feat: display timestamps in message headers via suffix"
```

---

### Task 6: Timestamp Filtering in `should_show_message()`

**Files:**
- Modify: `src/claude_stream/models.py:144-167` (RenderConfig — add before/after)
- Modify: `src/claude_stream/stream.py:18-79` (should_show_message)
- Create: `tests/test_timestamp_filter.py`

- [ ] **Step 1: Write failing tests for timestamp filtering**

```python
"""Tests for --before/--after timestamp filtering."""

from datetime import datetime, timezone

from claude_stream.models import RenderConfig, parse_message
from claude_stream.stream import should_show_message


class TestTimestampFilterAfter:
    def test_message_after_cutoff_shown(self, sample_assistant_message):
        config = RenderConfig(
            after=datetime(2026, 3, 17, 14, 0, 0, tzinfo=timezone.utc)
        )
        msg = parse_message(sample_assistant_message)
        assert should_show_message(msg, sample_assistant_message, config) is True

    def test_message_before_cutoff_hidden(self, sample_assistant_message):
        config = RenderConfig(
            after=datetime(2026, 3, 17, 15, 0, 0, tzinfo=timezone.utc)
        )
        msg = parse_message(sample_assistant_message)
        assert should_show_message(msg, sample_assistant_message, config) is False


class TestTimestampFilterBefore:
    def test_message_before_cutoff_shown(self, sample_assistant_message):
        config = RenderConfig(
            before=datetime(2026, 3, 17, 15, 0, 0, tzinfo=timezone.utc)
        )
        msg = parse_message(sample_assistant_message)
        assert should_show_message(msg, sample_assistant_message, config) is True

    def test_message_after_cutoff_hidden(self, sample_assistant_message):
        config = RenderConfig(
            before=datetime(2026, 3, 17, 14, 0, 0, tzinfo=timezone.utc)
        )
        msg = parse_message(sample_assistant_message)
        assert should_show_message(msg, sample_assistant_message, config) is False


class TestTimestampFilterRange:
    def test_message_in_range_shown(self, sample_assistant_message):
        config = RenderConfig(
            after=datetime(2026, 3, 17, 14, 0, 0, tzinfo=timezone.utc),
            before=datetime(2026, 3, 17, 15, 0, 0, tzinfo=timezone.utc),
        )
        msg = parse_message(sample_assistant_message)
        assert should_show_message(msg, sample_assistant_message, config) is True

    def test_message_outside_range_hidden(self, sample_assistant_message):
        config = RenderConfig(
            after=datetime(2026, 3, 17, 15, 0, 0, tzinfo=timezone.utc),
            before=datetime(2026, 3, 17, 16, 0, 0, tzinfo=timezone.utc),
        )
        msg = parse_message(sample_assistant_message)
        assert should_show_message(msg, sample_assistant_message, config) is False


class TestTimestampFilterNoTimestamp:
    def test_message_without_timestamp_passes(self, sample_message_no_timestamp):
        """Messages without timestamps should not be filtered out."""
        config = RenderConfig(
            after=datetime(2026, 3, 17, 15, 0, 0, tzinfo=timezone.utc)
        )
        msg = parse_message(sample_message_no_timestamp)
        assert should_show_message(msg, sample_message_no_timestamp, config) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/guy/git/github.com/shitchell/claude-stream && pytest tests/test_timestamp_filter.py -v`
Expected: FAIL — `RenderConfig` has no `before`/`after` fields.

- [ ] **Step 3: Add before/after fields to RenderConfig**

In `src/claude_stream/models.py`, add to `RenderConfig` (import `datetime` at the top of the dataclass section):

```python
from datetime import datetime as _datetime

@dataclass
class RenderConfig:
    """Configuration for rendering messages."""

    show_thinking: bool = True
    show_tool_results: bool = True
    show_metadata: bool = False
    show_line_numbers: bool = False
    show_timestamps: bool = True
    timestamp_format: str = "%Y-%m-%d %H:%M:%S"

    # Timestamp filtering
    before: _datetime | None = None
    after: _datetime | None = None

    # ... rest unchanged
```

Note: Use `_datetime` alias to avoid shadowing the `datetime` module if already imported. Alternatively, import at the top of the file as `from datetime import datetime as dt_datetime`.

- [ ] **Step 4: Add timestamp filtering to should_show_message()**

In `src/claude_stream/stream.py`, add timestamp filtering near the top of `should_show_message()`, after the type filter check. Add the datetime import:

```python
from datetime import datetime, timezone

def should_show_message(
    msg: BaseMessage, data: dict[str, Any], config: RenderConfig
) -> bool:
    """Determine if a message should be displayed based on filters."""

    # Check type filter
    if config.show_types and msg.type not in config.show_types:
        return False

    # Check timestamp filters
    if config.before or config.after:
        ts_str = data.get("timestamp", "")
        if ts_str:
            try:
                msg_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if msg_dt.tzinfo is None:
                    msg_dt = msg_dt.replace(tzinfo=timezone.utc)
                if config.after and msg_dt < config.after:
                    return False
                if config.before and msg_dt > config.before:
                    return False
            except (ValueError, OSError):
                pass  # Can't parse timestamp — let it through
        # Messages without timestamps pass through (not filtered out)

    # ... rest of existing filters unchanged
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/guy/git/github.com/shitchell/claude-stream && pytest tests/test_timestamp_filter.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/claude_stream/models.py src/claude_stream/stream.py tests/test_timestamp_filter.py
git commit -m "feat: add --before/--after timestamp filtering to should_show_message"
```

---

### Task 7: Rename `resolve_watch_path` to `resolve_project_path`

**Files:**
- Modify: `src/claude_stream/cli.py:46,218`

- [ ] **Step 1: Rename function and update all call sites**

In `src/claude_stream/cli.py`:

1. Rename the function definition at line 46: `def resolve_watch_path(path: Path) -> Path:` → `def resolve_project_path(path: Path) -> Path:`
2. Update the docstring to remove "watch" reference.
3. Update the call site at line 218: `watch_target = resolve_watch_path(args.watch)` → `watch_target = resolve_project_path(args.watch)`

- [ ] **Step 2: Run existing tests to verify nothing broke**

Run: `cd /home/guy/git/github.com/shitchell/claude-stream && pytest tests/ -v`
Expected: All existing tests PASS.

- [ ] **Step 3: Commit**

```bash
git add src/claude_stream/cli.py
git commit -m "refactor: rename resolve_watch_path to resolve_project_path"
```

---

### Task 8: CLI Timestamp Flags

**Files:**
- Modify: `src/claude_stream/cli.py:95-164` (parse_args) and `167-266` (main)
- Create: `tests/test_cli_timestamps.py`

- [ ] **Step 1: Write failing tests for timestamp CLI flags**

```python
"""Tests for timestamp-related CLI flags."""

import sys
from unittest.mock import patch

from claude_stream.cli import parse_args


class TestTimestampFlags:
    def test_show_timestamps_default(self):
        with patch.object(sys, "argv", ["claude-stream", "--latest"]):
            args = parse_args()
        # Default: None (meaning use RenderConfig default of True)
        assert args.show_timestamps is None

    def test_hide_timestamps(self):
        with patch.object(
            sys, "argv", ["claude-stream", "--hide-timestamps", "--latest"]
        ):
            args = parse_args()
        assert args.show_timestamps is False

    def test_show_timestamps_explicit(self):
        with patch.object(
            sys, "argv", ["claude-stream", "--show-timestamps", "--latest"]
        ):
            args = parse_args()
        assert args.show_timestamps is True

    def test_timestamp_format(self):
        with patch.object(
            sys,
            "argv",
            ["claude-stream", "--timestamp-format", "%H:%M", "--latest"],
        ):
            args = parse_args()
        assert args.timestamp_format == "%H:%M"

    def test_timestamp_format_default(self):
        with patch.object(sys, "argv", ["claude-stream", "--latest"]):
            args = parse_args()
        assert args.timestamp_format is None

    def test_compact_hides_timestamps(self):
        """--compact should hide timestamps (applied in main, not parse_args)."""
        with patch.object(sys, "argv", ["claude-stream", "--compact", "--latest"]):
            args = parse_args()
        assert args.compact is True
        assert args.show_timestamps is None  # None = defer to compact
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/guy/git/github.com/shitchell/claude-stream && pytest tests/test_cli_timestamps.py -v`
Expected: FAIL — no `--show-timestamps` flag.

- [ ] **Step 3: Add timestamp flags to parse_args()**

In `src/claude_stream/cli.py`, add to the visibility controls section:

```python
parser.add_argument("--show-timestamps", dest="show_timestamps", action="store_true", default=None)
parser.add_argument("--hide-timestamps", dest="show_timestamps", action="store_false")
parser.add_argument("--timestamp-format", dest="timestamp_format", default=None,
                    help="Timestamp format string (default: %%Y-%%m-%%d %%H:%%M:%%S)")
```

- [ ] **Step 4: Update main() to apply timestamp flags to config**

In `main()`, add to the `--compact` block:

```python
if args.compact:
    config.show_metadata = False
    config.show_thinking = False
    config.show_tool_results = False
    config.show_timestamps = False
    config.show_types = {"assistant", "user"}
```

And add explicit override handling:

```python
if args.show_timestamps is not None:
    config.show_timestamps = args.show_timestamps
if args.timestamp_format is not None:
    config.timestamp_format = args.timestamp_format
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/guy/git/github.com/shitchell/claude-stream && pytest tests/test_cli_timestamps.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/claude_stream/cli.py tests/test_cli_timestamps.py
git commit -m "feat: add --show-timestamps/--hide-timestamps and --timestamp-format flags"
```

---

### Task 9: CLI Search Mode (`--search`, `--stream`)

**Files:**
- Modify: `src/claude_stream/cli.py`
- Create: `tests/test_search.py`

- [ ] **Step 1: Write failing tests for search mode**

```python
"""Tests for --search mode."""

import sys
from unittest.mock import patch

from claude_stream.cli import main
from conftest import create_session_file


class TestSearchFilepathMode:
    def test_search_finds_matching_file(self, tmp_path, capsys):
        """--search prints matching filepaths."""
        create_session_file(
            tmp_path,
            "session-001",
            [
                {
                    "type": "user",
                    "timestamp": "2026-03-17T14:00:00Z",
                    "message": {"content": "find the needle in the haystack"},
                }
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
                }
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
                }
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
        """--search --stream renders matching sessions."""
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
        # Should render the message, not just the filepath
        assert "find the needle" in out
        assert ".jsonl" not in out  # Filepath not in rendered output


class TestSearchMutualExclusivity:
    def test_search_with_watch_is_error(self, tmp_path, capsys):
        with patch.object(
            sys,
            "argv",
            [
                "claude-stream",
                "--search",
                "text",
                "--watch",
                str(tmp_path),
            ],
        ):
            code = main()
        assert code != 0
        err = capsys.readouterr().err
        assert "mutually exclusive" in err.lower() or "cannot combine" in err.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/guy/git/github.com/shitchell/claude-stream && pytest tests/test_search.py -v`
Expected: FAIL — no `--search` flag.

- [ ] **Step 3: Add --search and --stream flags to parse_args() and update help epilog**

In `src/claude_stream/cli.py`, add to the filtering section:

```python
# Search mode
parser.add_argument("--search", dest="search_text", metavar="TEXT",
                    help="Search JSONL files for matching text")
parser.add_argument("--stream", action="store_true",
                    help="With --search: render matching sessions instead of listing filepaths")
```

Also update the epilog `Examples:` section to include the new features:

```python
epilog="""
...existing examples...
    %(prog)s --search "error message"              # Find sessions containing text
    %(prog)s --search "bug" --stream ~/project     # Render matching sessions
    %(prog)s --latest --after "today"              # Today's messages only
    %(prog)s --after "now -2h" --before "now" .    # Messages from last 2 hours
    %(prog)s --latest --hide-timestamps            # Hide timestamp display
"""
```

- [ ] **Step 4: Add search mode handler to main()**

In `main()`, add search mode handling after the watch mode block and before the input source determination. Add necessary imports at the module-level top of `cli.py`:

```python
import json as _json
from datetime import datetime, timezone

from .blocks import DividerBlock, HeaderBlock, Style
from .dateparse import parse_datetime
from .models import parse_message
from .stream import should_show_message
```

Then in `main()`, after the watch mode block:

```python
# Handle search mode
if args.search_text:
    # Mutual exclusivity check
    if args.watch:
        print("error: cannot combine --search with --watch", file=sys.stderr)
        return 1
    if args.session:
        print("error: cannot combine --search with --session", file=sys.stderr)
        return 1
    if args.latest:
        print("error: cannot combine --search with --latest", file=sys.stderr)
        return 1

    # Determine search scope
    search_path = args.input_file or args.file
    if search_path:
        search_dir = resolve_project_path(search_path)
    else:
        search_dir = Path.home() / ".claude" / "projects"

    if not search_dir.exists():
        print(f"error: path not found: {search_dir}", file=sys.stderr)
        return 1

    # Collect matching files
    if search_dir.is_file():
        jsonl_files = [search_dir]
    else:
        jsonl_files = sorted(
            search_dir.rglob("*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

    matching_files: list[Path] = _find_matching_files(
        jsonl_files, args.search_text, config
    )

    if not args.stream:
        # Filepath-only mode
        for mf in matching_files:
            print(mf)
        return 0
    else:
        # Stream mode — render each matching file
        for mf in matching_files:
            if len(matching_files) > 1:
                # Print file header
                print(formatter.format([
                    DividerBlock(char="─", width=60),
                    HeaderBlock(text=str(mf), icon="📄", level=2, styles={Style.INFO}),
                ]))
            with open(mf) as f:
                process_stream(f, config, formatter, tail_lines=args.lines)
        return 0
```

Also add this helper function in `cli.py` (before `main()`):

```python
def _find_matching_files(
    jsonl_files: list[Path],
    search_text: str,
    config: RenderConfig,
) -> list[Path]:
    """Find JSONL files matching search text and optional time filters.

    Each line must satisfy BOTH the text match AND time range (if set)
    for a file to be considered matching.
    """
    has_time_filter = config.before is not None or config.after is not None
    matching: list[Path] = []

    for jf in jsonl_files:
        try:
            with open(jf) as f:
                for line in f:
                    if search_text not in line:
                        continue

                    # Text matched — check time filter if present
                    if not has_time_filter:
                        matching.append(jf)
                        break  # Early termination

                    # Parse timestamp from matching line
                    try:
                        data = _json.loads(line)
                        ts_str = data.get("timestamp", "")
                        if not ts_str:
                            continue  # No timestamp on this line, keep looking
                        msg_dt = datetime.fromisoformat(
                            ts_str.replace("Z", "+00:00")
                        )
                        if msg_dt.tzinfo is None:
                            msg_dt = msg_dt.replace(tzinfo=timezone.utc)
                        in_range = True
                        if config.after and msg_dt < config.after:
                            in_range = False
                        if config.before and msg_dt > config.before:
                            in_range = False
                        if in_range:
                            matching.append(jf)
                            break  # Found a matching line
                    except (_json.JSONDecodeError, ValueError):
                        continue
        except (IOError, OSError):
            continue

    return matching
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/guy/git/github.com/shitchell/claude-stream && pytest tests/test_search.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/claude_stream/cli.py tests/test_search.py
git commit -m "feat: add --search and --stream flags for text search across sessions"
```

---

### Task 10: CLI `--before`/`--after` Flags + Directory Mode

**Files:**
- Modify: `src/claude_stream/cli.py`
- Create: `tests/test_before_after.py`

- [ ] **Step 1: Write failing tests for --before/--after flags and directory mode**

```python
"""Tests for --before/--after CLI flags and directory scanning."""

import sys
from unittest.mock import patch

from claude_stream.cli import main
from conftest import create_session_file


class TestBeforeAfterFlags:
    def test_after_flag_parses(self, tmp_path, capsys):
        """--after filters messages when streaming a file."""
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
        """Directory + --after renders matching messages with file headers."""
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
        """--search + --after narrows by both text and time."""
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/guy/git/github.com/shitchell/claude-stream && pytest tests/test_before_after.py -v`
Expected: FAIL — no `--before`/`--after` flags.

- [ ] **Step 3: Add --before/--after flags to parse_args()**

```python
# Timestamp filtering
parser.add_argument("--before", dest="before", metavar="DATETIME",
                    help="Only show messages before this time")
parser.add_argument("--after", dest="after", metavar="DATETIME",
                    help="Only show messages after this time")
```

- [ ] **Step 4: Add --before/--after parsing and config application to main()**

In `main()`, after the config is built and before mode handling, parse the datetime strings. Note: `parse_datetime` import was already added at module level in Task 9.

```python
# Parse --before/--after into datetimes
if args.before:
    try:
        config.before = parse_datetime(args.before)
    except ValueError:
        print(f"error: cannot parse --before date: {args.before}", file=sys.stderr)
        return 1

if args.after:
    try:
        config.after = parse_datetime(args.after)
    except ValueError:
        print(f"error: cannot parse --after date: {args.after}", file=sys.stderr)
        return 1
```

- [ ] **Step 5: Add directory scanning mode to main()**

In `main()`, add directory mode handling **between the search mode block and the existing "Determine input source" block**. The key is to check if the resolved path is a directory *before* the existing file-input logic runs:

```python
# Handle directory mode (directory + filters, no --search, no --watch)
# This goes BEFORE the existing "Determine input source" block.
# The existing file_path assignment (line 235 of original cli.py) must be
# restructured: extract it once, check if directory, then fall through to
# file handling if not.
file_path = args.input_file or args.file
if file_path:
    resolved_path = resolve_project_path(file_path)
    if resolved_path.is_dir():
        # Directory mode: scan all JSONL files, apply filters
        jsonl_files = sorted(
            resolved_path.rglob("*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for jf in jsonl_files:
            # Check if any lines pass the filters before printing header
            has_output = False
            with open(jf) as f:
                for line in f:
                    line_stripped = line.strip()
                    if not line_stripped:
                        continue
                    try:
                        data = _json.loads(line_stripped)
                        msg = parse_message(data)
                        if should_show_message(msg, data, config):
                            has_output = True
                            break
                    except _json.JSONDecodeError:
                        continue

            if has_output:
                # Print file header + matching messages
                print(formatter.format([
                    DividerBlock(char="─", width=60),
                    HeaderBlock(
                        text=str(jf), icon="📄", level=2, styles={Style.INFO}
                    ),
                ]))
                with open(jf) as f:
                    process_stream(f, config, formatter, tail_lines=args.lines)

        return 0

# Determine input source (existing block — file_path already resolved above)
# NOTE: Restructure this block to reuse `file_path` from above instead of
# re-assigning it. The original `file_path = args.input_file or args.file`
# at line 235 should be removed since we already computed it above.
```

**Important:** The existing "Determine input source" block (original lines 232-258) starts with `file_path = args.input_file or args.file`. Since we now compute `file_path` before the directory check, remove that duplicate assignment and reuse the variable. If `file_path` is set and is not a directory, execution falls through to the existing file-handling path naturally.

Note: `parse_message` and `should_show_message` imports were already added at module level in Task 9.

- [ ] **Step 6: No separate step needed — search + time filter logic already handled**

The `_find_matching_files` helper added in Task 9 Step 4 already handles the combined search+time filter case correctly. Each line is checked for both text match AND time range on the same line. No additional changes needed here.

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /home/guy/git/github.com/shitchell/claude-stream && pytest tests/test_before_after.py -v`
Expected: All tests PASS.

- [ ] **Step 8: Run all tests**

Run: `cd /home/guy/git/github.com/shitchell/claude-stream && pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 9: Commit**

```bash
git add src/claude_stream/cli.py tests/test_before_after.py
git commit -m "feat: add --before/--after flags and directory scanning mode"
```

---

### Task 11: Exports, Version Bump, and Cleanup

**Files:**
- Modify: `src/claude_stream/__init__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Update __init__.py exports**

Add `parse_datetime` export. Note: `resolve_project_path` stays internal to `cli.py` — it is not a library API, so no export needed.

In `src/claude_stream/__init__.py`, add:

```python
from .dateparse import parse_datetime
```

Add to the `__all__` list:

```python
"parse_datetime",
```

- [ ] **Step 2: Bump version in pyproject.toml**

Change `version = "0.2.3"` to `version = "0.3.0"`.

- [ ] **Step 3: Run full test suite**

Run: `cd /home/guy/git/github.com/shitchell/claude-stream && pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add src/claude_stream/__init__.py pyproject.toml
git commit -m "chore: export parse_datetime, bump version to 0.3.0"
```

---

### Task 12: Integration Smoke Test

**Files:**
- No files created — manual verification

- [ ] **Step 1: Test timestamp display with a real session**

Run: `cd /home/guy/git/github.com/shitchell/claude-stream && python -m claude_stream --latest -n 5`
Expected: Messages display with `· YYYY-MM-DD HH:MM:SS` timestamps.

- [ ] **Step 2: Test --hide-timestamps**

Run: `python -m claude_stream --latest -n 5 --hide-timestamps`
Expected: Messages display without timestamps.

- [ ] **Step 3: Test --search**

Run: `python -m claude_stream --search "some known text from a recent session"`
Expected: Matching filepaths printed.

- [ ] **Step 4: Test --before/--after**

Run: `python -m claude_stream --latest --after "today" -n 10`
Expected: Only messages from today shown.

- [ ] **Step 5: Test --compact**

Run: `python -m claude_stream --latest -n 5 --compact`
Expected: No timestamps, no thinking, no tool results.

- [ ] **Step 6: Test directory mode**

Run: `python -m claude_stream --after "today" ~/.claude/projects/ | head -30`
Expected: File headers + matching messages from today.
