"""Tests for weather forecast functionality."""

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from src.weather import (
    MANHATTAN_LAT,
    MANHATTAN_LON,
    _get_day_name,
    _weather_code_to_text,
    format_forecast_for_email,
    get_weekly_forecast,
)


class TestWeatherCodeToText:
    """Tests for weather code translation."""

    def test_clear_sky_code(self):
        """Test clear sky weather code."""
        assert _weather_code_to_text(0) == "Clear"

    def test_mainly_clear_code(self):
        """Test mainly clear weather code."""
        assert _weather_code_to_text(1) == "Mainly clear"

    def test_partly_cloudy_code(self):
        """Test partly cloudy weather code."""
        assert _weather_code_to_text(2) == "Partly cloudy"

    def test_overcast_code(self):
        """Test overcast weather code."""
        assert _weather_code_to_text(3) == "Overcast"

    def test_fog_codes(self):
        """Test fog weather codes."""
        assert _weather_code_to_text(45) == "Foggy"
        assert _weather_code_to_text(48) == "Fog with frost"

    def test_drizzle_codes(self):
        """Test drizzle weather codes."""
        assert _weather_code_to_text(51) == "Light drizzle"
        assert _weather_code_to_text(53) == "Drizzle"
        assert _weather_code_to_text(55) == "Heavy drizzle"
        assert _weather_code_to_text(56) == "Freezing drizzle"
        assert _weather_code_to_text(57) == "Heavy freezing drizzle"

    def test_rain_codes(self):
        """Test rain weather codes."""
        assert _weather_code_to_text(61) == "Light rain"
        assert _weather_code_to_text(63) == "Rain"
        assert _weather_code_to_text(65) == "Heavy rain"
        assert _weather_code_to_text(66) == "Freezing rain"
        assert _weather_code_to_text(67) == "Heavy freezing rain"

    def test_snow_codes(self):
        """Test snow weather codes."""
        assert _weather_code_to_text(71) == "Light snow"
        assert _weather_code_to_text(73) == "Snow"
        assert _weather_code_to_text(75) == "Heavy snow"
        assert _weather_code_to_text(77) == "Snow grains"

    def test_shower_codes(self):
        """Test shower weather codes."""
        assert _weather_code_to_text(80) == "Light showers"
        assert _weather_code_to_text(81) == "Showers"
        assert _weather_code_to_text(82) == "Heavy showers"
        assert _weather_code_to_text(85) == "Light snow showers"
        assert _weather_code_to_text(86) == "Heavy snow showers"

    def test_thunderstorm_codes(self):
        """Test thunderstorm weather codes."""
        assert _weather_code_to_text(95) == "Thunderstorm"
        assert _weather_code_to_text(96) == "Thunderstorm with hail"
        assert _weather_code_to_text(99) == "Severe thunderstorm"

    def test_unknown_code_returns_code_text(self):
        """Test that unknown codes return a fallback string."""
        assert _weather_code_to_text(999) == "Code 999"
        assert _weather_code_to_text(42) == "Code 42"
        assert _weather_code_to_text(-1) == "Code -1"


class TestGetDayName:
    """Tests for date to day name conversion."""

    def test_valid_date_returns_day_name(self):
        """Test that valid dates return correct day names."""
        # 2026-01-27 is a Tuesday
        assert _get_day_name("2026-01-27") == "Tuesday"
        # 2026-01-28 is a Wednesday
        assert _get_day_name("2026-01-28") == "Wednesday"
        # 2026-01-25 is a Sunday
        assert _get_day_name("2026-01-25") == "Sunday"

    def test_invalid_date_returns_unknown(self):
        """Test that invalid dates return Unknown."""
        assert _get_day_name("invalid-date") == "Unknown"
        assert _get_day_name("") == "Unknown"
        assert _get_day_name("2026/01/27") == "Unknown"  # Wrong format
        assert _get_day_name("27-01-2026") == "Unknown"  # Wrong order


class TestGetWeeklyForecast:
    """Tests for API forecast fetching."""

    @pytest.fixture
    def mock_api_response(self):
        """Create a mock API response."""
        return {
            "daily": {
                "time": ["2026-01-27", "2026-01-28", "2026-01-29"],
                "temperature_2m_max": [45.5, 50.2, 48.8],
                "temperature_2m_min": [32.1, 35.7, 30.0],
                "precipitation_probability_max": [10, 45, 80],
                "weathercode": [0, 2, 63],
            }
        }

    def test_successful_forecast_fetch(self, mock_api_response):
        """Test successful API response parsing."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_api_response).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = get_weekly_forecast()

        assert result["status"] == "success"
        assert result["location"] == "Manhattan, NY"
        assert len(result["forecasts"]) == 3

        # Check first forecast
        first = result["forecasts"][0]
        assert first["date"] == "2026-01-27"
        assert first["day"] == "Tuesday"
        assert first["high"] == 46  # Rounded from 45.5
        assert first["low"] == 32  # Rounded from 32.1
        assert first["precipitation_chance"] == 10
        assert first["condition"] == "Clear"

        # Check second forecast has partly cloudy
        second = result["forecasts"][1]
        assert second["condition"] == "Partly cloudy"

        # Check third forecast has rain
        third = result["forecasts"][2]
        assert third["condition"] == "Rain"
        assert third["precipitation_chance"] == 80

    def test_custom_coordinates(self, mock_api_response):
        """Test that custom coordinates are used in the API request."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_api_response).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            get_weekly_forecast(latitude=34.0522, longitude=-118.2437)

        # Verify the URL contains the custom coordinates
        call_url = mock_urlopen.call_args[0][0]
        assert "latitude=34.0522" in call_url
        assert "longitude=-118.2437" in call_url

    def test_default_manhattan_coordinates(self, mock_api_response):
        """Test that default coordinates are Manhattan."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_api_response).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            get_weekly_forecast()

        call_url = mock_urlopen.call_args[0][0]
        assert f"latitude={MANHATTAN_LAT}" in call_url
        assert f"longitude={MANHATTAN_LON}" in call_url

    def test_network_error_returns_error_dict(self):
        """Test that network errors are handled gracefully."""
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("Connection refused"),
        ):
            result = get_weekly_forecast()

        assert result["status"] == "error"
        assert "Network error" in result["message"]
        assert "Connection refused" in result["message"]

    def test_timeout_error_returns_error_dict(self):
        """Test that timeout errors are handled gracefully."""
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("timed out"),
        ):
            result = get_weekly_forecast()

        assert result["status"] == "error"
        assert "Network error" in result["message"]

    def test_invalid_json_response(self):
        """Test handling of invalid JSON from API."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"not valid json"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = get_weekly_forecast()

        assert result["status"] == "error"

    def test_empty_daily_data(self):
        """Test handling of empty daily data from API."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"daily": {}}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = get_weekly_forecast()

        assert result["status"] == "success"
        assert result["forecasts"] == []

    def test_partial_daily_data(self):
        """Test handling when some daily arrays are shorter than dates."""
        partial_response = {
            "daily": {
                "time": ["2026-01-27", "2026-01-28"],
                "temperature_2m_max": [45.0],  # Only one value
                "temperature_2m_min": [],  # Empty
                "precipitation_probability_max": [20, 30],
                "weathercode": [0],  # Only one value
            }
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(partial_response).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = get_weekly_forecast()

        assert result["status"] == "success"
        assert len(result["forecasts"]) == 2

        # First day has high and code
        first = result["forecasts"][0]
        assert first["high"] == 45
        assert first["low"] is None  # Missing
        assert first["condition"] == "Clear"

        # Second day has None for missing values
        second = result["forecasts"][1]
        assert second["high"] is None
        assert second["low"] is None
        assert second["condition"] == "Clear"  # Default code 0 when missing

    def test_missing_daily_key(self):
        """Test handling when daily key is missing entirely."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = get_weekly_forecast()

        assert result["status"] == "success"
        assert result["forecasts"] == []


class TestFormatForecastForEmail:
    """Tests for email formatting."""

    def test_format_success_response(self):
        """Test formatting a successful forecast."""
        forecast_data = {
            "status": "success",
            "location": "Manhattan, NY",
            "forecasts": [
                {
                    "date": "2026-01-27",
                    "day": "Tuesday",
                    "high": 45,
                    "low": 32,
                    "precipitation_chance": 10,
                    "condition": "Clear",
                },
                {
                    "date": "2026-01-28",
                    "day": "Wednesday",
                    "high": 50,
                    "low": 35,
                    "precipitation_chance": 45,
                    "condition": "Partly cloudy",
                },
            ],
        }

        result = format_forecast_for_email(forecast_data)

        assert "Weather Forecast for Manhattan, NY:" in result
        assert "Tuesday (2026-01-27): High 45" in result
        assert "Low 32" in result
        assert "Clear" in result
        # Low precipitation should not show rain percentage
        assert "10% rain" not in result
        # High precipitation should show rain percentage
        assert "45% rain" in result
        assert "Partly cloudy" in result

    def test_format_error_response(self):
        """Test formatting an error response."""
        forecast_data = {
            "status": "error",
            "message": "Network error: Connection refused",
        }

        result = format_forecast_for_email(forecast_data)

        assert "Weather forecast unavailable" in result
        assert "Network error: Connection refused" in result

    def test_format_error_without_message(self):
        """Test formatting error response without message."""
        forecast_data = {"status": "error"}

        result = format_forecast_for_email(forecast_data)

        assert "Weather forecast unavailable" in result
        assert "Unknown error" in result

    def test_format_with_missing_fields(self):
        """Test formatting with missing forecast fields."""
        forecast_data = {
            "status": "success",
            "location": "Manhattan, NY",
            "forecasts": [
                {
                    "date": "2026-01-27",
                    # Missing: day, high, low, precipitation_chance, condition
                },
            ],
        }

        result = format_forecast_for_email(forecast_data)

        # Should use defaults for missing fields
        assert "Unknown" in result or "?" in result

    def test_format_empty_forecasts(self):
        """Test formatting with empty forecasts list."""
        forecast_data = {
            "status": "success",
            "location": "Manhattan, NY",
            "forecasts": [],
        }

        result = format_forecast_for_email(forecast_data)

        assert "Weather Forecast for Manhattan, NY:" in result
        # Should just have header, no forecast lines

    def test_format_limits_to_seven_days(self):
        """Test that formatting limits output to 7 days."""
        forecasts = []
        for i in range(10):
            forecasts.append({
                "date": f"2026-01-{27 + i}",
                "day": "Day",
                "high": 50,
                "low": 30,
                "precipitation_chance": 0,
                "condition": "Clear",
            })

        forecast_data = {
            "status": "success",
            "location": "Manhattan, NY",
            "forecasts": forecasts,
        }

        result = format_forecast_for_email(forecast_data)

        # Count the number of forecast lines (excluding header and empty line)
        lines = [l for l in result.split("\n") if l.strip().startswith("Day")]
        assert len(lines) == 7

    def test_format_precipitation_threshold(self):
        """Test that precipitation is only shown above 20%."""
        forecast_data = {
            "status": "success",
            "location": "Manhattan, NY",
            "forecasts": [
                {
                    "date": "2026-01-27",
                    "day": "Tuesday",
                    "high": 45,
                    "low": 32,
                    "precipitation_chance": 20,  # Exactly at threshold
                    "condition": "Clear",
                },
                {
                    "date": "2026-01-28",
                    "day": "Wednesday",
                    "high": 45,
                    "low": 32,
                    "precipitation_chance": 21,  # Just above threshold
                    "condition": "Clear",
                },
                {
                    "date": "2026-01-29",
                    "day": "Thursday",
                    "high": 45,
                    "low": 32,
                    "precipitation_chance": 0,  # Zero
                    "condition": "Clear",
                },
            ],
        }

        result = format_forecast_for_email(forecast_data)

        # 20% should NOT show (threshold is > 20)
        assert "20% rain" not in result
        # 21% should show
        assert "21% rain" in result
        # 0% should not show
        lines = result.split("\n")
        thursday_line = [l for l in lines if "Thursday" in l][0]
        assert "rain" not in thursday_line

    def test_format_with_none_precipitation(self):
        """Test formatting when precipitation_chance is None."""
        forecast_data = {
            "status": "success",
            "location": "Manhattan, NY",
            "forecasts": [
                {
                    "date": "2026-01-27",
                    "day": "Tuesday",
                    "high": 45,
                    "low": 32,
                    "precipitation_chance": None,
                    "condition": "Clear",
                },
            ],
        }

        result = format_forecast_for_email(forecast_data)

        # Should not crash and should not show rain percentage
        assert "Tuesday" in result
        assert "rain" not in result

    def test_format_missing_location(self):
        """Test formatting when location is missing."""
        forecast_data = {
            "status": "success",
            "forecasts": [],
        }

        result = format_forecast_for_email(forecast_data)

        assert "Weather Forecast for Unknown:" in result


class TestModuleConstants:
    """Tests for module-level constants."""

    def test_manhattan_coordinates(self):
        """Test that Manhattan coordinates are reasonable."""
        # Manhattan is roughly at these coordinates
        assert 40.7 < MANHATTAN_LAT < 40.9
        assert -74.1 < MANHATTAN_LON < -73.9
