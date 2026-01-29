"""Weather forecast functionality using Open-Meteo API.

Provides free weather forecasts without requiring an API key.
"""

import json
import urllib.request
import urllib.error
from datetime import datetime
from typing import Any


# Manhattan coordinates
MANHATTAN_LAT = 40.7831
MANHATTAN_LON = -73.9712


def get_weekly_forecast(
    latitude: float = MANHATTAN_LAT,
    longitude: float = MANHATTAN_LON,
    timezone: str = "America/New_York",
) -> dict[str, Any]:
    """Get 7-day weather forecast.

    Args:
        latitude: Location latitude (default: Manhattan).
        longitude: Location longitude (default: Manhattan).
        timezone: Timezone for the forecast (default: America/New_York).

    Returns:
        Dictionary with forecast data or error.
    """
    import urllib.parse

    try:
        # URL-encode the timezone to handle slashes
        tz_encoded = urllib.parse.quote(timezone, safe="")
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={latitude}&longitude={longitude}"
            f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode"
            f"&temperature_unit=fahrenheit"
            f"&timezone={tz_encoded}"
        )

        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())

        daily = data.get("daily", {})
        dates = daily.get("time", [])
        highs = daily.get("temperature_2m_max", [])
        lows = daily.get("temperature_2m_min", [])
        precip = daily.get("precipitation_probability_max", [])
        codes = daily.get("weathercode", [])

        forecasts = []
        for i, date in enumerate(dates):
            forecasts.append({
                "date": date,
                "day": _get_day_name(date),
                "high": round(highs[i]) if i < len(highs) else None,
                "low": round(lows[i]) if i < len(lows) else None,
                "precipitation_chance": precip[i] if i < len(precip) else None,
                "condition": _weather_code_to_text(codes[i] if i < len(codes) else 0),
            })

        return {
            "status": "success",
            "location": "Manhattan, NY",
            "forecasts": forecasts,
        }

    except urllib.error.URLError as e:
        print(f"Weather API network error: {e}")
        return {"status": "error", "message": f"Network error: {e}"}
    except json.JSONDecodeError as e:
        print(f"Weather API returned invalid JSON: {e}")
        return {"status": "error", "message": "Weather service returned invalid data"}
    except Exception as e:
        print(f"Weather API unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


def format_forecast_for_email(forecast_data: dict[str, Any]) -> str:
    """Format forecast data as readable text for email.

    Args:
        forecast_data: Result from get_weekly_forecast().

    Returns:
        Formatted string for email inclusion.
    """
    if forecast_data.get("status") != "success":
        return f"Weather forecast unavailable: {forecast_data.get('message', 'Unknown error')}"

    lines = [f"Weather Forecast for {forecast_data.get('location', 'Unknown')}:", ""]

    for day in forecast_data.get("forecasts", [])[:7]:
        date = day.get("date", "")
        day_name = day.get("day", "")
        high = day.get("high", "?")
        low = day.get("low", "?")
        condition = day.get("condition", "Unknown")
        precip = day.get("precipitation_chance", 0)

        precip_str = f", {precip}% rain" if precip and precip > 20 else ""
        lines.append(f"  {day_name} ({date}): High {high}°F / Low {low}°F, {condition}{precip_str}")

    return "\n".join(lines)


def _get_day_name(date_str: str) -> str:
    """Convert date string to day name."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%A")
    except ValueError:
        return "Unknown"


def _weather_code_to_text(code: int) -> str:
    """Convert WMO weather code to human-readable text.

    See: https://open-meteo.com/en/docs (Weather codes section)
    """
    codes = {
        0: "Clear",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Foggy",
        48: "Fog with frost",
        51: "Light drizzle",
        53: "Drizzle",
        55: "Heavy drizzle",
        56: "Freezing drizzle",
        57: "Heavy freezing drizzle",
        61: "Light rain",
        63: "Rain",
        65: "Heavy rain",
        66: "Freezing rain",
        67: "Heavy freezing rain",
        71: "Light snow",
        73: "Snow",
        75: "Heavy snow",
        77: "Snow grains",
        80: "Light showers",
        81: "Showers",
        82: "Heavy showers",
        85: "Light snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with hail",
        99: "Severe thunderstorm",
    }
    return codes.get(code, f"Code {code}")
