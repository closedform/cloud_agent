# Cloud Agent

**Your own AI agent running 24/7 in the cloud. For free.**

An autonomous agent that runs on Google's free infrastructure. It listens for commands via email, routes them to the right handler, and responds.

## What You Get

- **Always-on AI agent** - Runs 24/7 on GCP's free tier (e2-micro VM)
- **Gemini 3 Flash Preview** - Google's multimodal model, free tier available
- **Email interface** - Send commands from anywhere, no app needed
- **Extensible architecture** - Add new capabilities with the `@register_handler` decorator

**Total monthly cost: $0.00** (within free tier limits)

## Architecture

```
You --> [Email] --> Gmail --> [IMAP] --> Poller
                                           |
                                           v
                                      RouterAgent (orchestrator)
                                           |
         +---------------------------------+----------------------------------+
         |              |              |              |              |        |
    CalendarAgent  ResearchAgent  PersonalData  AutomationAgent  System  SystemAdmin
         |              |           Agent            |            Agent    Agent
    Calendar API   WebSearch     Lists/Todos     Reminders/Rules  Status   Crontab
         |              |              |              |              |        |
         +--------------+--------------+--------------+--------------+--------+
                                           |
                                           v
                                      [SMTP] --> You
```

**Poller** (`src/poller.py`) - Watches Gmail, creates task files (atomic writes)
**ADK Orchestrator** (`src/adk_orchestrator.py`) - Processes tasks, manages sessions, runs scheduler
**RouterAgent** (`src/agents/router.py`) - Routes to specialist agents, sends email responses
**Agents** (`src/agents/`) - Specialist agents for calendar, research, personal data, automation, system
**Clients** (`src/clients/`) - Calendar, email, and weather integrations

## Commands

The agent uses Gemini to understand your requests naturally. Just write what you want.

### Schedule Events

```
Subject: Dentist appointment
Body: Dr. Smith next Tuesday at 2pm, should take about an hour
```

### Research (with web search)

```
Subject: What are the best practices for Python async?
Body: (optional extra context)
```

Uses Gemini 2.5 Flash with Google Search grounding (free tier) for up-to-date information.

### Calendar Query

```
Subject: What do I have this week?
Body: (optional)
```

### Reminders

```
Subject: Remind me to meet with Einstein tomorrow at 3pm
Body: (optional)
```

You'll get a confirmation email, then the reminder at the scheduled time.

### Status Check

```
Subject: Status
Body: (optional)
```

Returns agent configuration, API status, and recent task history.

### Help

```
Subject: What can you do?
Body: (optional)
```

Ask the agent about its capabilities.

## Quick Start

```bash
git clone https://github.com/closedform/cloud_agent.git
cd cloud_agent

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Configure
cp .env.example .env
# Edit .env with your API keys
```

### Credentials

- **Gemini API Key**: Free from [aistudio.google.com](https://aistudio.google.com)
- **Gmail App Password**: From [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
- **Google Calendar**: Run `uv run python -m src.cli.calendar_cli --list-calendars` to authorize

### Run Locally

```bash
# Terminal 1: ADK Orchestrator (brain - multi-agent)
uv run python -m src.adk_orchestrator

# Terminal 2: Poller (ears)
uv run python -m src.poller
```

### Deploy to Cloud

See [docs/deployment.md](docs/deployment.md) for the full GCP setup guide.

Quick version:
```bash
git clone https://github.com/closedform/cloud_agent.git
cd cloud_agent && uv sync
tmux new -s agent -d 'uv run python -m src.adk_orchestrator' \; split-window -h 'uv run python -m src.poller'
```

## Project Structure

```
cloud_agent/
├── src/
│   ├── config.py            # Centralized configuration
│   ├── services.py          # Service factory (Gemini, Calendar)
│   ├── task_io.py           # Atomic file I/O
│   ├── adk_orchestrator.py  # Brain: multi-agent orchestrator (Google ADK)
│   ├── poller.py            # Ears: watches email, creates tasks
│   ├── scheduler.py         # Background scheduler for rules and diaries
│   ├── models/
│   │   └── task.py          # Task and Reminder dataclasses
│   ├── agents/
│   │   ├── router.py        # RouterAgent - orchestrates sub-agents
│   │   ├── calendar_agent.py
│   │   ├── research_agent.py
│   │   ├── personal_data_agent.py
│   │   ├── automation_agent.py
│   │   ├── system_agent.py
│   │   ├── system_admin_agent.py
│   │   └── tools/           # Agent tool functions
│   ├── clients/
│   │   ├── calendar.py      # Google Calendar operations
│   │   └── email.py         # SMTP email sending
│   └── cli/
│       └── calendar_cli.py  # Calendar CLI tool
├── docs/
│   ├── deployment.md        # GCP deployment guide
│   └── tutorial.md          # Architecture deep-dive
├── inputs/                  # Task queue (created at runtime)
├── processed/               # Completed tasks (created at runtime)
├── failed/                  # Tasks that failed after max retries
├── .env.example
├── pyproject.toml
└── README.md
```

## Extending

Add new capabilities:

1. **Add tools** in `src/agents/tools/your_tools.py`:
```python
from src.agents.tools._context import get_user_email

def your_tool(param: str) -> dict:
    """Tool description for the agent."""
    email = get_user_email()
    return {"status": "success", "result": "..."}
```

2. **Create an agent** in `src/agents/`:
```python
from google.adk import Agent
from src.config import get_config

_config = get_config()

your_agent = Agent(
    name="YourAgent",
    model=_config.gemini_model,
    instruction="Your agent's system prompt...",
    tools=[your_tool],
    output_key="your_results",
)
```

3. **Add as sub-agent to RouterAgent** in `src/agents/router.py`

Ideas: task management, home automation, expense tracking, flight monitoring.

## Documentation

- [docs/deployment.md](docs/deployment.md) - GCP deployment guide
- [docs/tutorial.md](docs/tutorial.md) - Architecture overview

## License

MIT
