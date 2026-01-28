# Cloud Agent - Advanced Setup

An autonomous AI assistant that runs 24/7, controlled entirely via email. Built with Google's ADK (Agent Development Kit) for multi-agent orchestration.

## Features

| Category | Capabilities |
|----------|-------------|
| **Multi-User** | Isolated data per user (lists, todos, memory, reminders, rules) with shared calendar access |
| **Conversations** | Multi-turn email threads with persistent memory across sessions |
| **Calendar** | Schedule events, query calendars, multi-calendar support |
| **Lists & Todos** | Personal lists (groceries, movies, etc.) and todo tracking |
| **Reminders** | Time-based reminders with natural language scheduling |
| **Automation** | Cron-based rules + AI-powered calendar event triggers |
| **Research** | Web search, weather forecasts, weekly diary summaries |
| **Images** | Multimodal support - send photos for analysis |
| **Admin** | System administration commands for authorized users |
| **Formatting** | Beautiful HTML email responses |

---

## Table of Contents

- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Multi-User Support](#multi-user-support)
- [Capabilities](#capabilities)
- [Deployment](#deployment)
- [Project Structure](#project-structure)
- [Testing](#testing)
- [Comparison with Basic Setup](#comparison-with-basic-setup)

---

## Architecture

```
Email → IMAP Poller → Task File → ADK Orchestrator → RouterAgent
                                         ↓                 ↓
                               Session Store        Sub-agents
                               Memory Store              ↓
                                              Email Response
```

### Agent Hierarchy

```
RouterAgent (orchestrator, sends emails, has memory)
├── CalendarAgent      → calendar events, scheduling
├── PersonalDataAgent  → lists, todos
├── AutomationAgent    → reminders, automation rules
├── ResearchAgent      → weather, diary, web search
│   └── WebSearchAgent → Google Search grounding
├── SystemAgent        → status, help
└── SystemAdminAgent   → system administration (admin only)
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- Google Cloud project with Gemini API + Calendar API
- Gmail account with App Password

### Installation

```bash
# 1. Install dependencies
uv sync

# 2. Configure environment
cp .env.example .env
# Edit .env with your credentials

# 3. Set up Google Calendar OAuth
# Download credentials.json from Google Cloud Console, then:
uv run python -m src.cli.calendar_cli --list-calendars
# This opens browser for OAuth flow

# 4. (Optional) Add known users for personalized greetings
# Edit src/identities.py

# 5. Run
# Terminal 1: Orchestrator
uv run python -m src.adk_orchestrator

# Terminal 2: Email poller
uv run python -m src.poller
```

---

## Configuration

All settings are in `.env` (copy from `.env.example`):

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google AI API key |
| `GEMINI_MODEL` | Model for agents (default: `gemini-3-flash-preview`) |
| `EMAIL_USER` | Gmail address for sending/receiving |
| `EMAIL_PASS` | Gmail App Password |
| `ALLOWED_SENDERS` | Comma-separated list of allowed email addresses |
| `ADMIN_EMAILS` | Emails allowed to use SystemAdminAgent |
| `TIMEZONE` | Your timezone (default: `America/New_York`) |

---

## Multi-User Support

The agent supports multiple users, each with **completely isolated data**:

| Data Type | Isolation |
|-----------|-----------|
| Lists & Todos | Per-user (groceries, movies, etc.) |
| Memory | Per-user (facts about one user aren't visible to others) |
| Reminders | Per-user scheduling |
| Automation Rules | Per-user weekly summaries and event triggers |
| Conversation History | Per-user multi-turn sessions |
| Weekly Diary | Per-user activity summaries |
| **Calendar** | **Shared** - all users access the same Google Calendar |

### Setup

1. Add allowed users to `ALLOWED_SENDERS` in `.env`
2. (Optional) Add identities to `src/identities.py` for personalized greetings:

```python
IDENTITIES = {
    "user@example.com": Identity(
        email="user@example.com",
        name="John Doe",
        short_name="John",
    ),
}
```

---

## Capabilities

### Calendar
- **Schedule events**: "Schedule a meeting tomorrow at 2pm"
- **Query calendar**: "What's on my calendar this week?"
- **Multi-calendar**: Supports multiple calendars (work, personal, shared)

### Lists & Todos
- **Manage lists**: "Add Inception to my movie list"
- **Track todos**: "Add todo: call mom"
- **Mark complete**: "Done with call mom"

### Reminders
- **Immediate**: "Remind me to take medicine at 9pm"
- **Future**: "Remind me about the meeting tomorrow at 3pm"

### Automation Rules
- **Weekly summaries**: "Send me my schedule every Sunday" (includes weather forecast)
- **Event triggers**: "Remind me 3 days before any dentist appointment"
- **AI-powered matching**: Rules use AI to match events semantically (e.g., "dentist" matches "Dr. Smith DDS appointment")

### Research
- **Web search**: "What are the best hiking trails in Colorado?"
- **Weather**: "What's the weather tomorrow?"
- **Diary**: "What did I do last week?"

### Memory
The agent remembers facts you mention across conversations:
- "My cat Oliver needs to go to the vet" → Stores pet info
- Later: "Where's my vet?" → Recalls relevant facts

### Image Attachments
Send images via email for multimodal analysis:
- "What's in this photo?"
- "Can you read this handwritten note?"

### System Administration
Admin users (`ADMIN_EMAILS`) can run system commands:
- `"Show crontab"` - view scheduled jobs
- `"Check disk space"` - storage status
- `"Run tests"` - execute test suite
- `"Git pull"` - update from repository

---

## Deployment

### Cloud Deployment (Google Cloud e2-micro)

```bash
# Using tmux for persistent sessions
tmux new -s agent -d 'uv run python -m src.adk_orchestrator' \; \
    split-window -h 'uv run python -m src.poller'
```

### Reattach to session
```bash
tmux attach -t agent
```

---

## Project Structure

```
src/
├── adk_orchestrator.py    # Main orchestrator loop
├── poller.py              # Email watcher (IMAP)
├── scheduler.py           # Background scheduler thread
├── config.py              # Centralized configuration
├── identities.py          # User identity management
├── memory.py              # Persistent fact storage
├── agents/
│   ├── router.py          # RouterAgent (main orchestrator)
│   ├── calendar_agent.py
│   ├── personal_data_agent.py
│   ├── automation_agent.py
│   ├── research_agent.py
│   ├── system_agent.py
│   ├── system_admin_agent.py
│   ├── web_search_agent.py
│   └── tools/             # Agent tool functions
├── clients/
│   ├── calendar.py        # Google Calendar API
│   └── email.py           # SMTP email sending
├── sessions/              # Multi-turn conversation tracking
└── models/                # Data models (Task, Reminder)
```

---

## Testing

```bash
uv run pytest              # Run all tests
uv run pytest -v           # Verbose output
uv run pytest --cov=src    # With coverage
uv run pytest -k "test_calendar"  # Run specific tests
```

---

## Comparison with Basic Setup

| Feature | Basic | Advanced |
|---------|-------|----------|
| Architecture | Single handler | Multi-agent ADK |
| Users | Single user | Multi-user with isolated data |
| Conversations | Single-turn | Multi-turn with persistent memory |
| Scheduling | Basic reminders | Cron + AI-powered event triggers |
| Research | Simple queries | Sub-orchestrator with web search |
| Memory | None | Persistent fact storage per user |
| Images | None | Multimodal attachment support |
| Email Format | Plain text | HTML templates |
| Admin Tools | None | System administration commands |
| Calendar | Single | Shared across users |

---

## License

MIT License - See [LICENSE](LICENSE) file
