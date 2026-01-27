"""Research tool functions for ResearchAgent.

Handles web search, weather, and diary queries.
"""

from typing import Any

from google.genai.types import GenerateContentConfig, GoogleSearch, Tool

from src.agents.tools._context import get_user_email, get_services
from src.config import get_config
from src.diary import get_user_diary_entries
from src.weather import get_weekly_forecast, MANHATTAN_LAT, MANHATTAN_LON


def web_search(query: str) -> dict[str, Any]:
    """Perform a web search using Google Search grounding.

    Args:
        query: Search query.

    Returns:
        Dictionary with search results.
    """
    services = get_services()
    if not services or not services.gemini_client:
        return {"status": "error", "message": "Services not available"}

    config = get_config()

    prompt = f"""Answer the following query using web search:

Query: {query}

Provide a comprehensive, well-structured response with key facts and insights."""

    try:
        # Use research model for free Google Search grounding
        response = services.gemini_client.models.generate_content(
            model=config.gemini_research_model,
            contents=[prompt],
            config=GenerateContentConfig(tools=[Tool(google_search=GoogleSearch())]),
        )

        return {
            "status": "success",
            "query": query,
            "result": response.text,
        }

    except Exception as e:
        return {"status": "error", "message": f"Search failed: {e}"}


def query_diary(
    query: str | None = None,
    weeks: int = 4,
) -> dict[str, Any]:
    """Query past diary entries.

    Args:
        query: Optional search query to filter entries.
        weeks: Number of recent weeks to search (default: 4).

    Returns:
        Dictionary with matching diary entries.
    """
    email = get_user_email()
    if not email:
        return {"status": "error", "message": "User email not available"}

    config = get_config()
    entries = get_user_diary_entries(email, config, limit=weeks)

    if not entries:
        return {
            "status": "success",
            "message": "No diary entries found",
            "entries": [],
        }

    # Format entries
    formatted = []
    for entry in entries:
        formatted.append({
            "week_id": entry.id,
            "week_start": entry.week_start,
            "week_end": entry.week_end,
            "content": entry.content,
            "sources": entry.sources,
        })

    # If query provided, let the LLM filter/answer
    if query:
        return {
            "status": "success",
            "query": query,
            "entries": formatted,
            "message": f"Found {len(formatted)} diary entries to search",
        }

    return {
        "status": "success",
        "entries": formatted,
        "count": len(formatted),
    }


def get_weather_forecast(location: str = "manhattan") -> dict[str, Any]:
    """Get weather forecast for a location.

    Args:
        location: Location name (currently only 'manhattan' is supported).

    Returns:
        Dictionary with 7-day weather forecast.
    """
    # Currently only Manhattan is supported
    # Could be extended with a geocoding service
    if location.lower() in ["manhattan", "new york", "nyc", "ny"]:
        lat, lon = MANHATTAN_LAT, MANHATTAN_LON
        location_name = "Manhattan, NY"
    else:
        # Default to Manhattan with a note
        lat, lon = MANHATTAN_LAT, MANHATTAN_LON
        location_name = f"Manhattan, NY ('{location}' not recognized, using default)"

    forecast = get_weekly_forecast(lat, lon)

    if forecast.get("status") == "success":
        # Format for display
        days = []
        for day in forecast.get("forecasts", []):
            days.append({
                "date": day["date"],
                "day": day["day"],
                "high_f": day["high"],
                "low_f": day["low"],
                "condition": day["condition"],
                "rain_chance": f"{day['precipitation_chance']}%" if day.get("precipitation_chance") else "0%",
            })

        return {
            "status": "success",
            "location": location_name,
            "forecast": days,
        }

    return forecast

