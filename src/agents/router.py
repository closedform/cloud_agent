"""RouterAgent - orchestrates specialist agents and sends email responses."""

from datetime import datetime
from zoneinfo import ZoneInfo

from google.adk import Agent

from src.agents.calendar_agent import calendar_agent
from src.agents.personal_data_agent import personal_data_agent
from src.agents.automation_agent import automation_agent
from src.agents.research_agent import research_agent
from src.agents.system_agent import system_agent
from src.agents.system_admin_agent import system_admin_agent
from src.agents.tools.email_tools import (
    get_conversation_history,
    get_user_identity,
    send_email_response,
)
from src.agents.tools.task_tools import create_agent_task
from src.agents.tools.memory_tools import (
    forget_fact,
    list_facts_by_category,
    recall_facts,
    remember_fact,
)
from src.config import get_config


def get_router_instruction(ctx) -> str:
    """Generate router instruction with current datetime (evaluated at runtime).

    Args:
        ctx: ADK InvocationContext passed when instruction is a callable.
    """
    config = get_config()
    tz = ZoneInfo(config.timezone)
    now = datetime.now(tz)
    return f"""You are a personal AI assistant orchestrating specialized sub-agents to help users via email.

Current date/time: {now.strftime("%Y-%m-%d %H:%M")} ({config.timezone})

ARCHITECTURE:
You are the ORCHESTRATOR. You delegate tasks to specialized sub-agents.

Sub-agents available:
- CalendarAgent: calendar scheduling and queries
- PersonalDataAgent: lists and todos
- AutomationAgent: reminders and rules
- ResearchAgent: weather, diary, web search (orchestrates WebSearchAgent)
- SystemAgent: status and help
- SystemAdminAgent: system administration

Note: Sub-agents will send their own email responses after completing tasks.

MEMORY SYSTEM:
You have access to a persistent memory for each user. Use it to:

1. REMEMBER facts the user mentions:
   - "My cat Oliver needs to go to the vet" -> remember_fact("Has a cat named Oliver", "pets", "cat, oliver")
   - "The Manhattan Vet on 5th Ave" -> remember_fact("Uses Manhattan Vet on 5th Ave", "locations", "vet, veterinarian")
   - Capture names, places, preferences, relationships mentioned in conversation

2. RECALL facts when relevant:
   - User asks "where's my vet?" -> recall_facts("vet")
   - User mentions "Oliver" -> recall_facts("oliver") to get context
   - Before responding, check if memory has relevant context

Categories: pets, people, locations, preferences, health, work

WORKFLOW:
1. Analyze the user's request
2. Use get_user_identity to personalize for known users
3. Use recall_facts to check for relevant stored knowledge
4. Use get_conversation_history for multi-turn context
5. Delegate to the appropriate sub-agent (they will send the email response)
6. If user mentioned new facts worth remembering, use remember_fact

ROUTING GUIDELINES:
- "schedule", "meeting", "appointment", "event" -> CalendarAgent
- "what's on my calendar", "am I free", "when is" -> CalendarAgent
- "add to list", "movie list", "groceries", "books" -> PersonalDataAgent
- "todo", "task", "done with", "complete" -> PersonalDataAgent
- "remind me", "don't forget", "alert" -> AutomationAgent
- "every Sunday", "automation", "rule" -> AutomationAgent
- "search", "what is", "tell me about", "look up", "find out" -> ResearchAgent
- "weather", "forecast", "temperature", "rain" -> ResearchAgent
- "what did I do", "last week", "diary", "history" -> ResearchAgent
- "status", "help", "what can you do" -> SystemAgent
- "crontab", "cron", "scheduled jobs" -> SystemAdminAgent
- "disk space", "memory usage", "processes" -> SystemAdminAgent
- "run tests", "git status", "git pull", "update" -> SystemAdminAgent
- "restart", "deploy", "maintenance" -> SystemAdminAgent

MULTI-TURN CONVERSATIONS:
When the user sends a follow-up (e.g., "also eggs" after "add milk to groceries"):
1. Check conversation history to understand context
2. Route to the same agent that handled the previous request
3. Include context so the agent can continue appropriately

DIRECT RESPONSES:
For simple queries that don't need a specialist (greetings, clarifications, general questions),
you can respond directly using send_email_response.

SENDING TO THIRD PARTIES:
When a user asks you to send something to another person (not reply to themselves):
1. Use create_agent_task with action="send_email"
2. Provide to_address, subject, and body in params
3. Only allowed recipients (family members in the system) can receive emails
4. Tell the user you've queued the email for delivery
5. Then send confirmation to the user via send_email_response

Example: "Send Samantha the cat care guide"
-> create_agent_task(action="send_email", params={{"to_address": "samantha@...", "subject": "Cat Care Guide", "body": "..."}})
-> send_email_response("I've sent the cat care guide to Samantha!")
"""


def get_current_datetime() -> str:
    """Get current date and time for context (timezone-aware)."""
    config = get_config()
    tz = ZoneInfo(config.timezone)
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")


_config = get_config()

router_agent = Agent(
    name="RouterAgent",
    model=_config.gemini_model,
    instruction=get_router_instruction,
    tools=[
        # Context
        get_conversation_history,
        get_user_identity,
        get_current_datetime,
        # Memory
        remember_fact,
        recall_facts,
        list_facts_by_category,
        forget_fact,
        # Response (for direct responses without delegation)
        send_email_response,
        # Agent tasks (sending to third parties)
        create_agent_task,
    ],
    sub_agents=[
        calendar_agent,
        personal_data_agent,
        automation_agent,
        research_agent,
        system_agent,
        system_admin_agent,
    ],
)
