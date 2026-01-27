"""Handler registry and exports."""

from src.handlers.base import HANDLERS, HandlerFunc, get_handler, register_handler
from src.handlers.calendar_query import handle_calendar_query
from src.handlers.help import handle_help
from src.handlers.reminder import handle_reminder
from src.handlers.research import handle_research
from src.handlers.schedule import handle_schedule
from src.handlers.status import handle_status

__all__ = [
    "HANDLERS",
    "HandlerFunc",
    "get_handler",
    "register_handler",
    "handle_schedule",
    "handle_research",
    "handle_calendar_query",
    "handle_status",
    "handle_reminder",
    "handle_help",
]
