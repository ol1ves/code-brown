"""CLI tests for xscraper."""

import asyncio
import json
import sys
from datetime import datetime, timezone
from io import StringIO
from unittest.mock import AsyncMock, patch

import pytest

from xscraper.cli import main
from xscraper.exceptions import (
    XAuthError,
    XConfigError,
    XSchemaError,
    XTimeoutError,
)
from xscraper.models import Tweet


# Sample tweets for testing
_SAMPLE_TWEETS = [
    Tweet(
        id="tweet1",
        text="hello world",
        created_at=1650000000,
        handle="alice",
        lang="en",
        like_count=1500,
        retweet_count=340,
        reply_count=89,
        quote_count=12,
    ),
    Tweet(
        id="tweet2",
        text="second tweet",
        created_at=1650001000,
        handle="bob",
        lang="en",
        like_count=100,
        retweet_count=20,
        reply_count=5,
        quote_count=1,
    ),
]


class TestSearchDefault:
    """Test default search subcommand (no explicit 'search' keyword)."""

    def test_default_subcommand_runs_search(self):
        """Bare query without 'search' keyword should route to search."""
        with patch("xscraper.cli.search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = _SAMPLE_TWEETS
            with patch("xscraper.cli.load_config") as mock_config:
                mock_config.return_value.log_format = "json"
                with patch("xscraper.cli.setup_logging"):
                    with patch("sys.stdout", new_callable=StringIO):
                        code = main(["hello world"])
                        assert code == 0
                        mock_search.assert_called_once_with("hello world", 20, headed=False)

    def test_explicit_search_subcommand(self):
        """Explicit 'search' subcommand should work."""
        with patch("xscraper.cli.search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = _SAMPLE_TWEETS
            with patch("xscraper.cli.load_config") as mock_config:
                mock_config.return_value.log_format = "json"
                with patch("xscraper.cli.setup_logging"):
                    with patch("sys.stdout", new_callable=StringIO):
                        code = main(["search", "hello world"])
                        assert code == 0
                        mock_search.assert_called_once_with("hello world", 20, headed=False)


class TestSearchLimitArgs:
    """Test limit argument variants."""

    def test_short_limit_alias(self):
        """Short alias -l should work."""
        with patch("xscraper.cli.search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = _SAMPLE_TWEETS
            with patch("xscraper.cli.load_config") as mock_config:
                mock_config.return_value.log_format = "json"
                with patch("xscraper.cli.setup_logging"):
                    with patch("sys.stdout", new_callable=StringIO):
                        code = main(["search", "query", "-l", "5"])
                        assert code == 0
                        mock_search.assert_called_once_with("query", 5, headed=False)

    def test_long_limit_flag(self):
        """Long --limit flag should work."""
        with patch("xscraper.cli.search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = _SAMPLE_TWEETS
            with patch("xscraper.cli.load_config") as mock_config:
                mock_config.return_value.log_format = "json"
                with patch("xscraper.cli.setup_logging"):
                    with patch("sys.stdout", new_callable=StringIO):
                        code = main(["search", "query", "--limit", "10"])
                        assert code == 0
                        mock_search.assert_called_once_with("query", 10, headed=False)


class TestOutputFormats:
    """Test output formatting."""

    def test_json_output_valid(self):
        """--json output should be valid JSON."""
        with patch("xscraper.cli.search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = _SAMPLE_TWEETS
            with patch("xscraper.cli.load_config") as mock_config:
                mock_config.return_value.log_format = "json"
                with patch("xscraper.cli.setup_logging"):
                    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                        code = main(["search", "query", "--json"])
                        assert code == 0
                        output = mock_stdout.getvalue()
                        data = json.loads(output)
                        assert isinstance(data, list)
                        assert len(data) == 2
                        assert data[0]["text"] == "hello world"

    def test_plain_output_contains_data(self):
        """Plain output should contain handle, counts, text."""
        with patch("xscraper.cli.search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = _SAMPLE_TWEETS
            with patch("xscraper.cli.load_config") as mock_config:
                mock_config.return_value.log_format = "json"
                with patch("xscraper.cli.setup_logging"):
                    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                        code = main(["search", "query"])
                        assert code == 0
                        output = mock_stdout.getvalue()
                        assert "@alice" in output
                        assert "hello world" in output
                        assert "1.5k" in output  # compact format for 1500

    def test_compact_format(self):
        """Compact formatting: 1500 -> 1.5k, 1000000 -> 1M, 42 -> 42."""
        # This will be tested indirectly through plain output
        # but we can also test the formatter directly if it's exposed
        with patch("xscraper.cli.search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = _SAMPLE_TWEETS
            with patch("xscraper.cli.load_config") as mock_config:
                mock_config.return_value.log_format = "json"
                with patch("xscraper.cli.setup_logging"):
                    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                        code = main(["search", "query"])
                        assert code == 0
                        output = mock_stdout.getvalue()
                        # alice has 1500 likes
                        assert "1.5k❤" in output


class TestLimitValidation:
    """Test limit argument validation."""

    def test_limit_zero_rejected(self):
        """Limit of 0 should be rejected by argparse (exit 2)."""
        with patch("xscraper.cli.load_config") as mock_config:
            mock_config.return_value.log_format = "json"
            with patch("xscraper.cli.setup_logging"):
                code = main(["search", "query", "-l", "0"])
                assert code == 2

    def test_limit_above_max_rejected(self):
        """Limit of 21 should be rejected by argparse (exit 2)."""
        with patch("xscraper.cli.load_config") as mock_config:
            mock_config.return_value.log_format = "json"
            with patch("xscraper.cli.setup_logging"):
                code = main(["search", "query", "-l", "21"])
                assert code == 2


class TestLoginSubcommand:
    """Test login subcommand."""

    def test_login_subcommand_dispatches(self):
        """Login subcommand should dispatch to run_login."""
        with patch("xscraper.cli.run_login", new_callable=AsyncMock) as mock_login:
            with patch("xscraper.cli.load_config") as mock_config:
                mock_config.return_value.log_format = "json"
                with patch("xscraper.cli.setup_logging"):
                    code = main(["login"])
                    assert code == 0
                    mock_login.assert_called_once()


class TestExceptionHandling:
    """Test exception to exit code mapping."""

    @pytest.mark.parametrize(
        "exception,expected_code",
        [
            (XConfigError("missing config"), 4),
            (XAuthError("auth failed"), 1),
            (XSchemaError("schema changed"), 3),
            (XTimeoutError("timeout"), 5),
        ],
    )
    def test_exception_exit_codes(self, exception, expected_code):
        """Exceptions should map to correct exit codes."""
        with patch("xscraper.cli.search", new_callable=AsyncMock) as mock_search:
            mock_search.side_effect = exception
            with patch("xscraper.cli.load_config") as mock_config:
                mock_config.return_value.log_format = "json"
                with patch("xscraper.cli.setup_logging"):
                    code = main(["search", "query"])
                    assert code == expected_code