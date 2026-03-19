"""Tests for FilterConfig visibility resolution."""

import pytest
from claude_logs.models import FilterConfig


class TestFilterConfigDefaults:
    def test_shown_by_default(self):
        fc = FilterConfig()
        assert fc.is_visible("assistant") is True
        assert fc.is_visible("user") is True
        assert fc.is_visible("thinking") is True

    def test_default_hidden(self):
        fc = FilterConfig()
        assert fc.is_visible("metadata") is False
        assert fc.is_visible("line-numbers") is False
        assert fc.is_visible("file-history-snapshot") is False


class TestFilterConfigHide:
    def test_hide_makes_invisible(self):
        fc = FilterConfig(hidden={"thinking"})
        assert fc.is_visible("thinking") is False

    def test_hide_does_not_affect_others(self):
        fc = FilterConfig(hidden={"thinking"})
        assert fc.is_visible("assistant") is True


class TestFilterConfigShow:
    def test_show_overrides_hide(self):
        fc = FilterConfig(shown={"thinking"}, hidden={"thinking"})
        assert fc.is_visible("thinking") is True

    def test_show_overrides_default_hidden(self):
        fc = FilterConfig(shown={"metadata"})
        assert fc.is_visible("metadata") is True


class TestFilterConfigShowOnly:
    def test_show_only_hides_unlisted(self):
        fc = FilterConfig(show_only={"assistant", "user"})
        assert fc.is_visible("assistant") is True
        assert fc.is_visible("user") is True
        assert fc.is_visible("system") is False
        assert fc.is_visible("thinking") is False

    def test_show_only_plus_show(self):
        fc = FilterConfig(show_only={"assistant"}, shown={"metadata"})
        assert fc.is_visible("assistant") is True
        assert fc.is_visible("metadata") is True
        assert fc.is_visible("user") is False

    def test_show_only_plus_hide(self):
        fc = FilterConfig(show_only={"assistant", "thinking"}, hidden={"thinking"})
        assert fc.is_visible("assistant") is True
        assert fc.is_visible("thinking") is False

    def test_show_overrides_show_only_hide(self):
        fc = FilterConfig(show_only={"assistant"}, shown={"metadata"}, hidden={"metadata"})
        assert fc.is_visible("metadata") is True


class TestFilterConfigPriorityChain:
    def test_full_chain(self):
        fc = FilterConfig(
            show_only={"assistant", "user"},
            shown={"metadata"},
            hidden={"timestamps"},
        )
        assert fc.is_visible("assistant") is True
        assert fc.is_visible("user") is True
        assert fc.is_visible("system") is False
        assert fc.is_visible("metadata") is True
        assert fc.is_visible("timestamps") is False
        assert fc.is_visible("thinking") is False

    def test_empty_show_only_means_no_whitelist(self):
        fc = FilterConfig(show_only=set())
        assert fc.is_visible("assistant") is True
