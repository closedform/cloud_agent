"""ADK-based multi-agent system for Cloud Agent."""

from src.agents.calendar_agent import calendar_agent
from src.agents.personal_data_agent import personal_data_agent
from src.agents.automation_agent import automation_agent
from src.agents.web_search_agent import web_search_agent
from src.agents.research_agent import research_agent
from src.agents.system_agent import system_agent
from src.agents.system_admin_agent import system_admin_agent
from src.agents.router import router_agent

__all__ = [
    "calendar_agent",
    "personal_data_agent",
    "automation_agent",
    "web_search_agent",
    "research_agent",
    "system_agent",
    "system_admin_agent",
    "router_agent",
]
