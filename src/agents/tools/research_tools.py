"""Research tool functions for ResearchAgent.

Handles web search, weather, and diary queries.
"""

from typing import Any

from google.genai.types import GenerateContentConfig, GoogleSearch, Tool

from src.agents.tools._context import get_user_email, get_services
from src.config import get_config
from src.diary import get_user_diary_entries
from src.weather import get_weekly_forecast, MANHATTAN_LAT, MANHATTAN_LON

# Validation constants
MAX_SEARCH_QUERY_LENGTH = 10000  # Prevent excessively long queries
MAX_DIARY_WEEKS = 52  # Maximum weeks to query (1 year)


def web_search(query: str) -> dict[str, Any]:
    """Perform a web search using Google Search grounding.

    Args:
        query: Search query.

    Returns:
        Dictionary with search results.
    """
    # Validate query
    if not query or not query.strip():
        return {"status": "error", "message": "Search query cannot be empty"}

    query = query.strip()
    if len(query) > MAX_SEARCH_QUERY_LENGTH:
        return {
            "status": "error",
            "message": f"Query too long (max {MAX_SEARCH_QUERY_LENGTH} characters)",
        }

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

        result_text = response.text if hasattr(response, "text") else None
        if result_text is None:
            return {
                "status": "error",
                "message": "Search returned no results",
            }

        return {
            "status": "success",
            "query": query,
            "result": result_text,
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
        weeks: Number of recent weeks to search (default: 4, max: 52).

    Returns:
        Dictionary with matching diary entries.
    """
    email = get_user_email()
    if not email:
        return {"status": "error", "message": "User email not available"}

    # Validate weeks parameter
    if weeks < 1:
        weeks = 1
    elif weeks > MAX_DIARY_WEEKS:
        weeks = MAX_DIARY_WEEKS

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
        # Format for display with safe key access
        days = []
        for day in forecast.get("forecasts", []):
            precip = day.get("precipitation_chance")
            days.append({
                "date": day.get("date"),
                "day": day.get("day"),
                "high_f": day.get("high"),
                "low_f": day.get("low"),
                "condition": day.get("condition", "Unknown"),
                "rain_chance": f"{precip}%" if precip else "0%",
            })

        return {
            "status": "success",
            "location": location_name,
            "forecast": days,
        }

    return forecast

