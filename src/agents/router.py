"""RouterAgent - orchestrates specialist agents and sends email responses."""

from datetime import datetime

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
    return f"""You are a personal AI assistant orchestrating specialized sub-agents to help users via email.

Current date/time: {datetime.now().strftime("%Y-%m-%d %H:%M")}

ARCHITECTURE:
You are the ORCHESTRATOR. Sub-agents return results to you, and YOU send the final email response.

Sub-agents return their results via state:
- CalendarAgent -> {{calendar_results}}
- PersonalDataAgent -> {{personal_data_results}}
- AutomationAgent -> {{automation_results}}
- ResearchAgent -> {{research_results}} (orchestrates WebSearchAgent internally)
- SystemAgent -> {{system_results}}
- SystemAdminAgent -> {{system_admin_results}}

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
5. Delegate to the appropriate sub-agent
6. Review the results returned via state
7. If user mentioned new facts worth remembering, use remember_fact
8. Send a friendly, well-formatted email response using send_email_response

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

RESPONSE FORMAT:
- Be friendly and personalized when user identity is known
- Format responses clearly with sections/lists when appropriate
- Always use send_email_response to deliver the final response
"""


def get_current_datetime() -> str:
    """Get current date and time for context."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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
        # Response
        send_email_response,  # Only RouterAgent sends emails
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
