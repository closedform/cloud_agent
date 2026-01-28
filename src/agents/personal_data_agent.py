"""PersonalDataAgent - handles lists and todos.

Returns results to RouterAgent for email delivery.
"""

from google.adk import Agent

from src.agents.tools.email_tools import send_email_response
from src.agents.tools.personal_data_tools import (
    add_item_to_list,
    add_todo_item,
    complete_todo_item,
    get_list_items,
    get_user_lists,
    get_user_todos,
    remove_item_from_list,
)
from src.config import get_config

PERSONAL_DATA_AGENT_INSTRUCTION = """You are a personal data assistant managing the user's lists and todos.

Your capabilities:
- Lists: Create, view, add items to, and remove items from named lists (movies, books, groceries, etc.)
- Todos: Create todos with optional due dates and reminders, view todos, mark todos complete

For lists:
- List names are flexible - the user can create any list they want
- When adding items, the list is created automatically if it doesn't exist
- When viewing lists, show items numbered for easy reference
- Item removal uses case-insensitive matching

For todos:
- Todos can have optional due dates (YYYY-MM-DD format)
- Todos can have reminders that fire N days before the due date
- When marking complete, match by text (partial match works)
- Show both pending and completed todos when appropriate

IMPORTANT: After completing the task, you MUST call send_email_response to deliver the results to the user. Be friendly and concise in your email.
"""

_config = get_config()

personal_data_agent = Agent(
    name="PersonalDataAgent",
    model=_config.gemini_model,
    instruction=PERSONAL_DATA_AGENT_INSTRUCTION,
    tools=[
        get_user_lists,
        get_list_items,
        add_item_to_list,
        remove_item_from_list,
        get_user_todos,
        add_todo_item,
        complete_todo_item,
        send_email_response,  # Sub-agents send their own emails in ADK
    ],
    output_key="personal_data_results",
)
