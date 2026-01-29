"""Stress tests for research tools - hunting for edge case bugs.

Tests cover:
1. Invalid location for weather
2. Very long search queries
3. Special characters in queries
4. Missing API responses
"""

import json
from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest


class TestWeatherInvalidLocations:
    """Tests for weather with invalid or edge case locations."""

    @pytest.fixture
    def mock_research_services(self):
        """Create mock services for research tools."""
        mock_services = MagicMock()
        mock_services.gemini_client = MagicMock()
        return mock_services

    def test_valid_manhattan_location(self, mock_research_services, test_config):
        """Manhattan location should work."""
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.research_tools.get_weekly_forecast"
        ) as mock_forecast:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config
            mock_forecast.return_value = {
                "status": "success",
                "forecasts": [
                    {
                        "date": "2026-01-28",
                        "day": "Wednesday",
                        "high": 45,
                        "low": 32,
                        "condition": "Clear",
                        "precipitation_chance": 10,
                    }
                ],
            }

            from src.agents.tools.research_tools import get_weather_forecast

            result = get_weather_forecast("manhattan")

            assert result["status"] == "success"
            assert result["location"] == "Manhattan, NY"

    def test_nyc_aliases(self, mock_research_services, test_config):
        """Various NYC aliases should work."""
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.research_tools.get_weekly_forecast"
        ) as mock_forecast:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config
            mock_forecast.return_value = {
                "status": "success",
                "forecasts": [],
            }

            from src.agents.tools.research_tools import get_weather_forecast

            for alias in ["manhattan", "new york", "nyc", "ny", "MANHATTAN", "NYC"]:
                result = get_weather_forecast(alias)
                assert result["status"] == "success"
                assert "Manhattan, NY" in result["location"]

    def test_unrecognized_location_defaults_to_manhattan(
        self, mock_research_services, test_config
    ):
        """BUG HUNT: Unrecognized locations silently default to Manhattan.

        This could confuse users who ask for weather in Tokyo and get
        Manhattan weather instead. The message mentions it but is subtle.
        """
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.research_tools.get_weekly_forecast"
        ) as mock_forecast:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config
            mock_forecast.return_value = {
                "status": "success",
                "forecasts": [
                    {
                        "date": "2026-01-28",
                        "day": "Wednesday",
                        "high": 45,
                        "low": 32,
                        "condition": "Clear",
                        "precipitation_chance": 10,
                    }
                ],
            }

            from src.agents.tools.research_tools import get_weather_forecast

            # User asks for Tokyo but gets Manhattan!
            result = get_weather_forecast("tokyo")

            assert result["status"] == "success"
            # The location shows it's not recognized, but still returns data
            assert "'tokyo' not recognized" in result["location"]
            # This could be confusing - user asked for Tokyo!
            assert "Manhattan" in result["location"]

    def test_empty_location_string(self, mock_research_services, test_config):
        """BUG HUNT: Empty location string behavior."""
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.research_tools.get_weekly_forecast"
        ) as mock_forecast:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config
            mock_forecast.return_value = {
                "status": "success",
                "forecasts": [],
            }

            from src.agents.tools.research_tools import get_weather_forecast

            # Empty string - defaults to Manhattan
            result = get_weather_forecast("")

            assert result["status"] == "success"
            # Empty string shows as "not recognized"
            assert "'' not recognized" in result["location"]

    def test_whitespace_only_location(self, mock_research_services, test_config):
        """BUG HUNT: Whitespace-only location string."""
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.research_tools.get_weekly_forecast"
        ) as mock_forecast:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config
            mock_forecast.return_value = {
                "status": "success",
                "forecasts": [],
            }

            from src.agents.tools.research_tools import get_weather_forecast

            # Whitespace only - would fail case-insensitive check
            result = get_weather_forecast("   ")

            assert result["status"] == "success"
            # Whitespace is not stripped before checking
            assert "'   ' not recognized" in result["location"]

    def test_very_long_location_name(self, mock_research_services, test_config):
        """BUG HUNT: Very long location name."""
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.research_tools.get_weekly_forecast"
        ) as mock_forecast:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config
            mock_forecast.return_value = {
                "status": "success",
                "forecasts": [],
            }

            from src.agents.tools.research_tools import get_weather_forecast

            # 10KB location name
            long_location = "A" * 10240
            result = get_weather_forecast(long_location)

            # Still works, just defaults to Manhattan
            assert result["status"] == "success"
            # Very long string in the location message!
            assert "not recognized" in result["location"]

    def test_special_characters_in_location(self, mock_research_services, test_config):
        """BUG HUNT: Special characters in location."""
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.research_tools.get_weekly_forecast"
        ) as mock_forecast:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config
            mock_forecast.return_value = {
                "status": "success",
                "forecasts": [],
            }

            from src.agents.tools.research_tools import get_weather_forecast

            # Various special characters
            special_locations = [
                "San Francisco, CA",
                "Paris; DROP TABLE cities;--",
                "<script>alert('xss')</script>",
                "Location\nwith\nnewlines",
                "Location\twith\ttabs",
                "\x00null\x00bytes",
            ]

            for loc in special_locations:
                result = get_weather_forecast(loc)
                # All default to Manhattan, but special chars pass through
                assert result["status"] == "success"

    def test_unicode_location_names(self, mock_research_services, test_config):
        """BUG HUNT: Unicode location names."""
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.research_tools.get_weekly_forecast"
        ) as mock_forecast:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config
            mock_forecast.return_value = {
                "status": "success",
                "forecasts": [],
            }

            from src.agents.tools.research_tools import get_weather_forecast

            # Unicode location names
            unicode_locations = [
                "\u6771\u4eac",  # Tokyo in Japanese
                "\u5317\u4eac",  # Beijing in Chinese
                "\u041c\u043e\u0441\u043a\u0432\u0430",  # Moscow in Russian
            ]

            for loc in unicode_locations:
                result = get_weather_forecast(loc)
                assert result["status"] == "success"
                assert "not recognized" in result["location"]

    def test_weather_api_network_error(self, mock_research_services, test_config):
        """Test handling of network errors from weather API."""
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.research_tools.get_weekly_forecast"
        ) as mock_forecast:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config
            mock_forecast.return_value = {
                "status": "error",
                "message": "Network error: Connection timed out",
            }

            from src.agents.tools.research_tools import get_weather_forecast

            result = get_weather_forecast("manhattan")

            # Error passed through from weather module
            assert result["status"] == "error"
            assert "Network error" in result["message"]

    def test_weather_api_returns_empty_forecasts(
        self, mock_research_services, test_config
    ):
        """BUG HUNT: Empty forecasts array handling."""
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.research_tools.get_weekly_forecast"
        ) as mock_forecast:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config
            mock_forecast.return_value = {
                "status": "success",
                "forecasts": [],  # Empty!
            }

            from src.agents.tools.research_tools import get_weather_forecast

            result = get_weather_forecast("manhattan")

            # Success with empty forecast list
            assert result["status"] == "success"
            assert result["forecast"] == []

    def test_weather_missing_precipitation_chance(
        self, mock_research_services, test_config
    ):
        """Test handling of missing precipitation_chance field."""
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.research_tools.get_weekly_forecast"
        ) as mock_forecast:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config
            mock_forecast.return_value = {
                "status": "success",
                "forecasts": [
                    {
                        "date": "2026-01-28",
                        "day": "Wednesday",
                        "high": 45,
                        "low": 32,
                        "condition": "Clear",
                        # No precipitation_chance!
                    }
                ],
            }

            from src.agents.tools.research_tools import get_weather_forecast

            result = get_weather_forecast("manhattan")

            assert result["status"] == "success"
            # Should handle missing precipitation_chance gracefully
            assert result["forecast"][0]["rain_chance"] == "0%"


class TestWebSearchStress:
    """Tests for web search with various edge cases."""

    @pytest.fixture
    def mock_research_services(self):
        """Create mock services for research tools."""
        mock_services = MagicMock()
        mock_services.gemini_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Search results here"
        mock_services.gemini_client.models.generate_content.return_value = mock_response
        return mock_services

    def test_normal_search_query(self, mock_research_services, test_config):
        """Normal search query works."""
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config

            from src.agents.tools.research_tools import web_search

            result = web_search("What is the weather today?")

            assert result["status"] == "success"
            assert result["query"] == "What is the weather today?"

    def test_very_long_search_query(self, mock_research_services, test_config):
        """Test that very long search queries are rejected.

        Long queries could hit API limits or cause memory issues.
        Queries over 10000 chars are now rejected.
        """
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config

            from src.agents.tools.research_tools import web_search

            # 10KB query exceeds limit
            long_query = "A" * 10240
            result = web_search(long_query)

            # Now validated and rejected
            assert result["status"] == "error"
            assert "too long" in result["message"]

    def test_100kb_search_query(self, mock_research_services, test_config):
        """Test that 100KB search query is rejected."""
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config

            from src.agents.tools.research_tools import web_search

            # 100KB query - exceeds limit
            long_query = "B" * 102400
            result = web_search(long_query)

            # Now validated and rejected
            assert result["status"] == "error"
            assert "too long" in result["message"]

    def test_empty_search_query(self, mock_research_services, test_config):
        """Test that empty search query is rejected."""
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config

            from src.agents.tools.research_tools import web_search

            # Empty query
            result = web_search("")

            # Now validated and rejected
            assert result["status"] == "error"
            assert "cannot be empty" in result["message"]

    def test_whitespace_only_query(self, mock_research_services, test_config):
        """Test that whitespace-only query is rejected."""
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config

            from src.agents.tools.research_tools import web_search

            result = web_search("   \n\t   ")

            # Now validated and rejected
            assert result["status"] == "error"
            assert "cannot be empty" in result["message"]

    def test_special_characters_in_query(self, mock_research_services, test_config):
        """Test special characters in search queries."""
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config

            from src.agents.tools.research_tools import web_search

            special_queries = [
                "What is 2+2?",
                "Search for 'quotes' and \"double quotes\"",
                "Path/with/slashes",
                "Query with <html> tags",
                "SQL; DROP TABLE searches;--",
                "Query\nwith\nnewlines",
                "Query\twith\ttabs",
                "Query with \x00null\x00bytes",
                "Query with emoji \U0001F4BB",
            ]

            for query in special_queries:
                result = web_search(query)
                # All pass through without sanitization
                assert result["status"] == "success"
                assert result["query"] == query

    def test_unicode_search_queries(self, mock_research_services, test_config):
        """Test unicode in search queries."""
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config

            from src.agents.tools.research_tools import web_search

            unicode_queries = [
                "\u4eca\u5929\u306e\u5929\u6c17",  # Japanese
                "\u4eca\u5929\u7684\u5929\u6c14",  # Chinese
                "\u0421\u0435\u0433\u043e\u0434\u043d\u044f\u0448\u043d\u044f\u044f \u043f\u043e\u0433\u043e\u0434\u0430",  # Russian
                "\u0645\u0627 \u0647\u0648 \u0627\u0644\u0637\u0642\u0633 \u0627\u0644\u064a\u0648\u0645\u061f",  # Arabic
            ]

            for query in unicode_queries:
                result = web_search(query)
                assert result["status"] == "success"

    def test_services_not_available(self, test_config):
        """Test handling when services are not available."""
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config:
            mock_get_services.return_value = None
            mock_get_config.return_value = test_config

            from src.agents.tools.research_tools import web_search

            result = web_search("test query")

            assert result["status"] == "error"
            assert "Services not available" in result["message"]

    def test_gemini_client_not_available(self, test_config):
        """Test handling when Gemini client is None."""
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config:
            mock_services = MagicMock()
            mock_services.gemini_client = None
            mock_get_services.return_value = mock_services
            mock_get_config.return_value = test_config

            from src.agents.tools.research_tools import web_search

            result = web_search("test query")

            assert result["status"] == "error"
            assert "Services not available" in result["message"]

    def test_gemini_api_exception(self, mock_research_services, test_config):
        """Test handling of Gemini API exceptions."""
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config
            mock_research_services.gemini_client.models.generate_content.side_effect = (
                Exception("API rate limit exceeded")
            )

            from src.agents.tools.research_tools import web_search

            result = web_search("test query")

            assert result["status"] == "error"
            assert "Search failed" in result["message"]
            assert "API rate limit exceeded" in result["message"]

    def test_gemini_returns_none_text(self, mock_research_services, test_config):
        """Test that Gemini response with None text is handled properly."""
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config
            mock_response = MagicMock()
            mock_response.text = None
            mock_research_services.gemini_client.models.generate_content.return_value = (
                mock_response
            )

            from src.agents.tools.research_tools import web_search

            result = web_search("test query")

            # None text is now treated as an error
            assert result["status"] == "error"
            assert "no results" in result["message"]

    def test_gemini_returns_empty_text(self, mock_research_services, test_config):
        """Test Gemini response with empty text."""
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config
            mock_response = MagicMock()
            mock_response.text = ""
            mock_research_services.gemini_client.models.generate_content.return_value = (
                mock_response
            )

            from src.agents.tools.research_tools import web_search

            result = web_search("test query")

            assert result["status"] == "success"
            assert result["result"] == ""


class TestQueryDiaryStress:
    """Tests for diary queries with edge cases."""

    @pytest.fixture
    def mock_research_services(self):
        """Create mock services for research tools."""
        mock_services = MagicMock()
        return mock_services

    def test_no_user_email(self, mock_research_services, test_config):
        """Test when user email is not available."""
        with patch(
            "src.agents.tools.research_tools.get_user_email"
        ) as mock_get_email, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config:
            mock_get_email.return_value = None
            mock_get_config.return_value = test_config

            from src.agents.tools.research_tools import query_diary

            result = query_diary()

            assert result["status"] == "error"
            assert "User email not available" in result["message"]

    def test_empty_user_email(self, mock_research_services, test_config):
        """BUG HUNT: Empty string user email."""
        with patch(
            "src.agents.tools.research_tools.get_user_email"
        ) as mock_get_email, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.research_tools.get_user_diary_entries"
        ) as mock_get_entries:
            mock_get_email.return_value = ""  # Empty string is truthy in check
            mock_get_config.return_value = test_config
            mock_get_entries.return_value = []

            from src.agents.tools.research_tools import query_diary

            # Empty string passes the "if not email" check!
            # This is a potential bug - empty string is falsy
            result = query_diary()

            # Actually empty string IS falsy, so this returns error
            assert result["status"] == "error"

    def test_no_diary_entries(self, mock_research_services, test_config):
        """Test when there are no diary entries."""
        with patch(
            "src.agents.tools.research_tools.get_user_email"
        ) as mock_get_email, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.research_tools.get_user_diary_entries"
        ) as mock_get_entries:
            mock_get_email.return_value = "user@example.com"
            mock_get_config.return_value = test_config
            mock_get_entries.return_value = []

            from src.agents.tools.research_tools import query_diary

            result = query_diary()

            assert result["status"] == "success"
            assert result["entries"] == []
            assert "No diary entries found" in result["message"]

    def test_query_with_entries(self, mock_research_services, test_config):
        """Test query with existing entries."""
        from src.diary import DiaryEntry

        with patch(
            "src.agents.tools.research_tools.get_user_email"
        ) as mock_get_email, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.research_tools.get_user_diary_entries"
        ) as mock_get_entries:
            mock_get_email.return_value = "user@example.com"
            mock_get_config.return_value = test_config
            mock_get_entries.return_value = [
                DiaryEntry(
                    id="2026-W04",
                    user_email="user@example.com",
                    week_start="2026-01-20",
                    week_end="2026-01-26",
                    content="Weekly summary",
                    sources={"todos": ["Buy groceries"]},
                )
            ]

            from src.agents.tools.research_tools import query_diary

            result = query_diary(query="What did I do?")

            assert result["status"] == "success"
            assert result["query"] == "What did I do?"
            assert len(result["entries"]) == 1
            assert result["entries"][0]["week_id"] == "2026-W04"

    def test_very_long_query(self, mock_research_services, test_config):
        """BUG HUNT: Very long diary query string."""
        from src.diary import DiaryEntry

        with patch(
            "src.agents.tools.research_tools.get_user_email"
        ) as mock_get_email, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.research_tools.get_user_diary_entries"
        ) as mock_get_entries:
            mock_get_email.return_value = "user@example.com"
            mock_get_config.return_value = test_config
            mock_get_entries.return_value = [
                DiaryEntry(
                    id="2026-W04",
                    user_email="user@example.com",
                    week_start="2026-01-20",
                    week_end="2026-01-26",
                    content="Weekly summary",
                    sources={},
                )
            ]

            from src.agents.tools.research_tools import query_diary

            # 10KB query
            long_query = "A" * 10240
            result = query_diary(query=long_query)

            # No length validation
            assert result["status"] == "success"
            assert len(result["query"]) == 10240

    def test_special_characters_in_query(self, mock_research_services, test_config):
        """Test special characters in diary query."""
        from src.diary import DiaryEntry

        with patch(
            "src.agents.tools.research_tools.get_user_email"
        ) as mock_get_email, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.research_tools.get_user_diary_entries"
        ) as mock_get_entries:
            mock_get_email.return_value = "user@example.com"
            mock_get_config.return_value = test_config
            mock_get_entries.return_value = [
                DiaryEntry(
                    id="2026-W04",
                    user_email="user@example.com",
                    week_start="2026-01-20",
                    week_end="2026-01-26",
                    content="Weekly summary",
                    sources={},
                )
            ]

            from src.agents.tools.research_tools import query_diary

            special_queries = [
                "What about 'quoted' things?",
                "Query with <tags>",
                "Query\nwith\nnewlines",
                "\u4eca\u9031\u306f\u4f55\u3092\u3057\u307e\u3057\u305f\u304b\uff1f",  # Japanese
            ]

            for q in special_queries:
                result = query_diary(query=q)
                assert result["status"] == "success"
                assert result["query"] == q

    def test_negative_weeks_parameter(self, mock_research_services, test_config):
        """BUG HUNT: Negative weeks parameter."""
        with patch(
            "src.agents.tools.research_tools.get_user_email"
        ) as mock_get_email, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.research_tools.get_user_diary_entries"
        ) as mock_get_entries:
            mock_get_email.return_value = "user@example.com"
            mock_get_config.return_value = test_config
            mock_get_entries.return_value = []

            from src.agents.tools.research_tools import query_diary

            # Negative weeks - no validation
            result = query_diary(weeks=-5)

            # Passed to get_user_diary_entries which may handle it
            assert result["status"] == "success"

    def test_zero_weeks_parameter(self, mock_research_services, test_config):
        """BUG HUNT: Zero weeks parameter."""
        with patch(
            "src.agents.tools.research_tools.get_user_email"
        ) as mock_get_email, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.research_tools.get_user_diary_entries"
        ) as mock_get_entries:
            mock_get_email.return_value = "user@example.com"
            mock_get_config.return_value = test_config
            mock_get_entries.return_value = []

            from src.agents.tools.research_tools import query_diary

            # Zero weeks - would return empty
            result = query_diary(weeks=0)

            assert result["status"] == "success"

    def test_very_large_weeks_parameter(self, mock_research_services, test_config):
        """BUG HUNT: Very large weeks parameter.

        Could cause performance issues if not bounded.
        """
        with patch(
            "src.agents.tools.research_tools.get_user_email"
        ) as mock_get_email, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.research_tools.get_user_diary_entries"
        ) as mock_get_entries:
            mock_get_email.return_value = "user@example.com"
            mock_get_config.return_value = test_config
            mock_get_entries.return_value = []

            from src.agents.tools.research_tools import query_diary

            # Very large weeks - no upper bound validation
            result = query_diary(weeks=1000000)

            # No validation, passed directly to function
            assert result["status"] == "success"

    def test_diary_entry_with_missing_sources(self, mock_research_services, test_config):
        """Test diary entry formatting when sources is empty."""
        from src.diary import DiaryEntry

        with patch(
            "src.agents.tools.research_tools.get_user_email"
        ) as mock_get_email, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.research_tools.get_user_diary_entries"
        ) as mock_get_entries:
            mock_get_email.return_value = "user@example.com"
            mock_get_config.return_value = test_config
            mock_get_entries.return_value = [
                DiaryEntry(
                    id="2026-W04",
                    user_email="user@example.com",
                    week_start="2026-01-20",
                    week_end="2026-01-26",
                    content="Weekly summary",
                    sources={},  # Empty sources
                )
            ]

            from src.agents.tools.research_tools import query_diary

            result = query_diary()

            assert result["status"] == "success"
            assert result["entries"][0]["sources"] == {}

    def test_diary_entry_with_unicode_content(
        self, mock_research_services, test_config
    ):
        """Test diary entry with unicode content."""
        from src.diary import DiaryEntry

        with patch(
            "src.agents.tools.research_tools.get_user_email"
        ) as mock_get_email, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.research_tools.get_user_diary_entries"
        ) as mock_get_entries:
            mock_get_email.return_value = "user@example.com"
            mock_get_config.return_value = test_config
            mock_get_entries.return_value = [
                DiaryEntry(
                    id="2026-W04",
                    user_email="user@example.com",
                    week_start="2026-01-20",
                    week_end="2026-01-26",
                    content="\u4eca\u9031\u306f\u65e5\u672c\u8a9e\u3067\u66f8\u304d\u307e\u3057\u305f\u3002\U0001F389 emoji too!",
                    sources={"todos": ["\u8cb7\u3044\u7269"]},
                )
            ]

            from src.agents.tools.research_tools import query_diary

            result = query_diary()

            assert result["status"] == "success"
            assert "\u4eca\u9031" in result["entries"][0]["content"]


class TestMissingAPIResponses:
    """Tests for missing or malformed API responses."""

    @pytest.fixture
    def mock_research_services(self):
        """Create mock services for research tools."""
        mock_services = MagicMock()
        mock_services.gemini_client = MagicMock()
        return mock_services

    def test_weather_api_missing_forecasts_key(
        self, mock_research_services, test_config
    ):
        """BUG HUNT: Weather API response missing forecasts key."""
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.research_tools.get_weekly_forecast"
        ) as mock_forecast:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config
            # Missing 'forecasts' key
            mock_forecast.return_value = {
                "status": "success",
                # No 'forecasts' key!
            }

            from src.agents.tools.research_tools import get_weather_forecast

            result = get_weather_forecast("manhattan")

            # .get("forecasts", []) handles missing key
            assert result["status"] == "success"
            assert result["forecast"] == []

    def test_weather_forecast_missing_fields(
        self, mock_research_services, test_config
    ):
        """Test that missing forecast fields are handled gracefully.

        Previously, the code directly accessed day["date"], etc. causing KeyError.
        Now uses .get() with defaults for safe access.
        """
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.research_tools.get_weekly_forecast"
        ) as mock_forecast:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config
            mock_forecast.return_value = {
                "status": "success",
                "forecasts": [
                    {
                        # Missing date, day, condition, etc.
                        "high": 45,
                        "low": 32,
                    }
                ],
            }

            from src.agents.tools.research_tools import get_weather_forecast

            # BUG FIXED: Now uses .get() with defaults
            result = get_weather_forecast("manhattan")

            assert result["status"] == "success"
            # Missing fields are None or have defaults
            forecast = result["forecast"][0]
            assert forecast["date"] is None
            assert forecast["day"] is None
            assert forecast["high_f"] == 45
            assert forecast["low_f"] == 32
            assert forecast["condition"] == "Unknown"  # Default value
            assert forecast["rain_chance"] == "0%"  # Default for missing precip

    def test_weather_forecast_none_values(self, mock_research_services, test_config):
        """BUG HUNT: Forecast with None values for fields."""
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.research_tools.get_weekly_forecast"
        ) as mock_forecast:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config
            mock_forecast.return_value = {
                "status": "success",
                "forecasts": [
                    {
                        "date": None,
                        "day": None,
                        "high": None,
                        "low": None,
                        "condition": None,
                        "precipitation_chance": None,
                    }
                ],
            }

            from src.agents.tools.research_tools import get_weather_forecast

            result = get_weather_forecast("manhattan")

            assert result["status"] == "success"
            # None values are passed through
            forecast = result["forecast"][0]
            assert forecast["date"] is None
            assert forecast["high_f"] is None
            # rain_chance formatting handles None
            assert forecast["rain_chance"] == "0%"

    def test_gemini_response_missing_text_attribute(
        self, mock_research_services, test_config
    ):
        """Test that Gemini response object missing text attribute is handled."""
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config
            # Response without .text attribute
            mock_response = MagicMock(spec=[])  # Empty spec = no attributes
            del mock_response.text  # Ensure no text attribute
            mock_research_services.gemini_client.models.generate_content.return_value = (
                mock_response
            )

            from src.agents.tools.research_tools import web_search

            # Now handled gracefully with hasattr() check
            result = web_search("test query")

            # Returned as error since no text attribute means no results
            assert result["status"] == "error"
            assert "no results" in result["message"]

    def test_gemini_timeout(self, mock_research_services, test_config):
        """Test Gemini API timeout handling."""
        import socket

        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config
            mock_research_services.gemini_client.models.generate_content.side_effect = (
                socket.timeout("Connection timed out")
            )

            from src.agents.tools.research_tools import web_search

            result = web_search("test query")

            assert result["status"] == "error"
            assert "Search failed" in result["message"]

    def test_gemini_connection_error(self, mock_research_services, test_config):
        """Test Gemini API connection error handling."""
        with patch(
            "src.agents.tools.research_tools.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.research_tools.get_config"
        ) as mock_get_config:
            mock_get_services.return_value = mock_research_services
            mock_get_config.return_value = test_config
            mock_research_services.gemini_client.models.generate_content.side_effect = (
                ConnectionError("Network unreachable")
            )

            from src.agents.tools.research_tools import web_search

            result = web_search("test query")

            assert result["status"] == "error"
            assert "Search failed" in result["message"]
