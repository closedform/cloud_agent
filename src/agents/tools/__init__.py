"""ADK tool functions for specialized agents."""

from src.agents.tools.calendar_tools import (
    create_calendar_event,
    list_calendars,
    query_calendar_events,
)
from src.agents.tools.personal_data_tools import (
    add_item_to_list,
    add_todo_item,
    complete_todo_item,
    get_list_items,
    get_user_lists,
    get_user_todos,
    remove_item_from_list,
)
from src.agents.tools.automation_tools import (
    create_reminder,
    create_rule,
    delete_user_rule,
    get_rules,
)
from src.agents.tools.research_tools import (
    get_weather_forecast,
    query_diary,
    web_search,
)
from src.agents.tools.memory_tools import (
    forget_fact,
    list_facts_by_category,
    recall_facts,
    remember_fact,
)
from src.agents.tools.email_tools import (
    get_conversation_history,
    get_user_identity,
    send_email_response,
)
from src.agents.tools.task_tools import (
    create_agent_task,
)

__all__ = [
    # Calendar
    "create_calendar_event",
    "list_calendars",
    "query_calendar_events",
    # Personal data
    "add_item_to_list",
    "add_todo_item",
    "complete_todo_item",
    "get_list_items",
    "get_user_lists",
    "get_user_todos",
    "remove_item_from_list",
    # Automation
    "create_reminder",
    "create_rule",
    "delete_user_rule",
    "get_rules",
    # Research
    "get_weather_forecast",
    "query_diary",
    "web_search",
    # Memory
    "forget_fact",
    "list_facts_by_category",
    "recall_facts",
    "remember_fact",
    # Email
    "get_conversation_history",
    "get_user_identity",
    "send_email_response",
    # Task creation
    "create_agent_task",
]
