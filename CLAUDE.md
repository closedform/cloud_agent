# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Cloud Agent is an autonomous AI agent running 24/7 on Google Cloud's free tier (e2-micro VM). It listens for commands via email and uses a multi-agent architecture (Google ADK) to handle requests. Supports multi-turn email conversations with specialized agents for different domains.

## Commands

```bash
# Install dependencies
uv sync

# Run locally (two terminals)
uv run python -m src.adk_orchestrator  # Brain - multi-agent orchestrator
uv run python -m src.poller            # Ears - watches email

# Cloud deployment with tmux
tmux new -s agent -d 'uv run python -m src.adk_orchestrator' \; split-window -h 'uv run python -m src.poller'

# Calendar OAuth authorization
uv run python -m src.cli.calendar_cli --list-calendars

# Run tests
uv run pytest                       # Run all tests
uv run pytest -v                    # Verbose output
uv run pytest --cov=src             # With coverage
uv run pytest -k "test_add_todo"    # Run specific tests
```

## Architecture

```
Email → IMAP Poller → Task File → ADK Orchestrator → RouterAgent (orchestrator)
                                         ↓                    ↓
                               Session Store          Sub-agents return via state
                               Memory Store                   ↓
                                                    RouterAgent sends email
```

**Agent Hierarchy** (`src/agents/`):

RouterAgent is the **orchestrator** - it's the only agent that sends emails. Sub-agents return results via `output_key` state, which RouterAgent uses to compose the final response.

```
RouterAgent (orchestrator, sends emails, has memory)
├── CalendarAgent → {calendar_results}
├── PersonalDataAgent → {personal_data_results}
├── AutomationAgent → {automation_results}
├── ResearchAgent (sub-orchestrator) → {research_results}
│   └── WebSearchAgent → {web_search_results}
├── SystemAgent → {system_results}
└── SystemAdminAgent → {system_admin_results}
```

**Agents**:

- **RouterAgent** (`router.py`): Orchestrator that analyzes intent, delegates to specialists, and sends email responses. Has memory tools for persistent user facts.

- **CalendarAgent** (`calendar_agent.py`): Schedules events, queries calendar, lists calendars.

- **PersonalDataAgent** (`personal_data_agent.py`): Manages lists (movies, groceries, etc.) and todos with reminder scheduling.

- **AutomationAgent** (`automation_agent.py`): Creates reminders and automation rules (cron-based and event-triggered).

- **ResearchAgent** (`research_agent.py`): Sub-orchestrator for weather forecasts, diary queries. Delegates web searches to WebSearchAgent and synthesizes results.

- **WebSearchAgent** (`web_search_agent.py`): Web search using gemini-2.5-flash for free Google Search grounding. Returns summarized findings to ResearchAgent.

- **SystemAgent** (`system_agent.py`): Status checks and help/capabilities.

- **SystemAdminAgent** (`system_admin_agent.py`): System administration - crontab management, disk/memory monitoring, git operations, running tests, updating dependencies.

**Agent Tools** (`src/agents/tools/`): Each agent has domain-specific tools that wrap the underlying data functions. Shared utilities in `_context.py` provide thread-safe access to request context and services.

**Sessions** (`src/sessions/`): Multi-turn conversation tracking via `FileSessionStore`. Thread ID computed from normalized subject + sender.

### Core Components

- **Poller** (`src/poller.py`): Ultra-thin email watcher. Only creates task files in `inputs/` from unread emails.

- **ADK Orchestrator** (`src/adk_orchestrator.py`): Main orchestrator using Google ADK. Processes task files, manages sessions, runs background scheduler thread.

- **Scheduler** (`src/scheduler.py`): Background thread (60s interval) that checks time-based rules (cron), event-based rules (calendar triggers with AI matching), and generates weekly diaries on Sunday 11pm.

- **Config** (`src/config.py`): Centralized configuration via frozen dataclass with `@lru_cache`.

- **Task I/O** (`src/task_io.py`): Atomic file operations (temp file + rename) to prevent race conditions.

- **Services** (`src/services.py`): Factory for Gemini client, Calendar service, and calendars dict.

- **Identities** (`src/identities.py`): Maps email addresses to user identities for personalization.

- **User Data** (`src/user_data.py`): Per-user persistent storage for lists and todos with atomic file I/O.

- **Rules** (`src/rules.py`): Automation rules - time-based (cron) and event-based (calendar triggers).

- **Reminders** (`src/reminders.py`): Reminder scheduling using `threading.Timer` with JSON persistence.

- **Diary** (`src/diary.py`): Weekly activity summaries generated from todos, reminders, and calendar.

- **Memory** (`src/memory.py`): Persistent fact storage for user knowledge. Stores facts like "Has cat named Oliver" or "Uses Manhattan Vet" for later recall.

**Models** (centralized in `config.py`):
- `gemini_model` (default: `gemini-3-flash`): Used by all agents except WebSearchAgent
- `gemini_research_model` (default: `gemini-2.5-flash`): Used by WebSearchAgent for free Google Search grounding

## Adding New Capabilities

1. **Add tools** in `src/agents/tools/your_tools.py`:
```python
from src.agents.tools._context import get_user_email, get_reply_to, get_services

def your_tool_function(param: str) -> dict:
    """Tool description for the agent."""
    email = get_user_email()  # Convenience helper for request context
    if not email:
        return {"status": "error", "message": "User email not available"}
    # Implementation
    return {"status": "success", "result": "..."}
```

**Context helpers** (`src/agents/tools/_context.py`):
- `get_user_email()` - Current user's email address
- `get_reply_to()` - Reply-to address for responses
- `get_thread_id()` - Conversation thread ID
- `get_body()` - Original message body
- `get_services()` - Services instance (Gemini client, Calendar, etc.)

2. **Create or update an agent** in `src/agents/`:
```python
from google.adk import Agent
from src.agents.tools.your_tools import your_tool_function
from src.config import get_config

_config = get_config()

your_agent = Agent(
    name="YourAgent",
    model=_config.gemini_model,  # Use centralized config
    instruction="Your agent's system prompt...",
    tools=[your_tool_function],
    output_key="your_results",  # Results flow back to RouterAgent via state
)
```

3. **Add as sub-agent to RouterAgent** in `src/agents/router.py`:
   - Import the agent
   - Add to `sub_agents` list
   - Update routing guidelines in instruction
   - Reference `{your_results}` state key in workflow documentation

## Key Design Decisions

- **Orchestrator pattern**: RouterAgent is the sole email sender. Sub-agents return results via `output_key` state, allowing RouterAgent to compose and personalize responses.
- **Sub-orchestrators**: ResearchAgent orchestrates WebSearchAgent, enabling multi-step research with follow-up queries before synthesizing results.
- **Persistent memory**: RouterAgent has tools to store/recall user facts across conversations (e.g., "Has cat named Oliver", "Uses Manhattan Vet").
- **Multi-turn conversations**: Thread ID from normalized subject + sender enables conversational context across email replies.
- **Tool context via thread-local**: `_context.py` provides thread-safe global access to services and request state for ADK tools. Convenience helpers (`get_user_email()`, `get_reply_to()`, etc.) eliminate boilerplate in tool functions.
- **Atomic file I/O**: Temp file + rename prevents orchestrator reading partial task files.
- **Centralized models**: All agents use `config.gemini_model` except WebSearchAgent which uses `config.gemini_research_model` for free Google Search grounding.
- **Threading timers**: Reminders use `threading.Timer` with JSON persistence for reload on restart.
- **Immutable config**: Frozen dataclass prevents accidental modification.

## Testing

Tests use pytest with fixtures defined in `tests/conftest.py`. Test structure mirrors `src/`:

```
tests/
  conftest.py               # Shared fixtures (test_config, mock_services, etc.)
  test_identities.py
  test_user_data.py
  test_task_io.py
  test_models.py
  test_sessions.py          # Multi-turn session management
  test_memory.py            # Persistent user fact storage
  test_diary.py             # Weekly activity summaries
  test_reminders.py         # Reminder scheduling and persistence
  test_scheduler.py         # Background scheduler (timezone handling)
  test_automation_tools.py  # Automation agent tools (rules, reminders)
  test_personal_data_tools.py  # Personal data tools (todos with reminders)
  test_calendar_tools.py    # Calendar agent tools
```

Key fixtures:
- `test_config`: Config with temporary file paths
- `mock_services`: Mocked Gemini client and services
- `sample_task`: Sample task dictionary
- `populated_user_data`: Pre-populated user data file

## Configuration

See `.env.example` for required environment variables. Key vars: `GEMINI_API_KEY`, `EMAIL_USER`, `EMAIL_PASS`, `ALLOWED_SENDERS`.

## Git Remotes

- **origin** → `closedform/cloud_agent_private` (private, push here)
- **public** → `closedform/cloud_agent` (public upstream)

To sync updates from public:
```bash
git fetch public && git merge public/main
```

## Deployment

VM access and deployment commands are in `SECRET.md` (not committed to git). Contains SSH access, deploy/restart one-liner, and VM details.
