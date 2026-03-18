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
        suffix_start = result.index("·")
        before_suffix = result[:suffix_start]
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
        block = HeaderBlock(text="ASSISTANT", level=2, suffix="· 2026-03-17 14:23:05")
        result = PlainFormatter().format_block(block)
        assert "ASSISTANT" in result
        assert "· 2026-03-17 14:23:05" in result
