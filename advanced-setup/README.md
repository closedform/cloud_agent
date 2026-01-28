# Cloud Agent - Advanced Setup

This is the advanced multi-agent version of Cloud Agent, featuring:

- **Multi-user support** - each user gets their own isolated data (lists, todos, memory, reminders, rules)
- **Google ADK (Agent Development Kit)** multi-agent orchestration
- **Specialized sub-agents** for different domains (calendar, lists, research, etc.)
- **Persistent memory** for user facts across conversations
- **Multi-turn email conversations** with session tracking
- **Automation rules** (cron-based and calendar event triggers)
- **Background scheduler** for reminders and automated tasks
- **Identity management** - personalized responses for known users

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
├── CalendarAgent → calendar events, scheduling
├── PersonalDataAgent → lists, todos
├── AutomationAgent → reminders, rules
├── ResearchAgent → weather, diary, web search
│   └── WebSearchAgent → Google Search grounding
├── SystemAgent → status, help
└── SystemAdminAgent → system administration
```

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- Google Cloud project with:
  - Gemini API access
  - Calendar API enabled
  - OAuth 2.0 credentials
- Gmail account with App Password for SMTP

## Quick Start

1. **Install dependencies:**
   ```bash
   uv sync
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

3. **Set up Google Calendar OAuth:**
   ```bash
   # Download credentials.json from Google Cloud Console
   uv run python -m src.cli.calendar_cli --list-calendars
   # This will open browser for OAuth flow
   ```

4. **Add known users (optional):**
   Edit `src/identities.py` to add personalized greetings for known email addresses.

5. **Run locally:**
   ```bash
   # Terminal 1: Orchestrator
   uv run python -m src.adk_orchestrator

   # Terminal 2: Email poller
   uv run python -m src.poller
   ```

## Configuration

See `.env.example` for all configuration options:

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google AI API key |
| `GEMINI_MODEL` | Model for agents (default: gemini-2.0-flash) |
| `EMAIL_USER` | Gmail address for sending/receiving |
| `EMAIL_PASS` | Gmail App Password |
| `ALLOWED_SENDERS` | Comma-separated list of allowed email addresses |
| `ADMIN_EMAILS` | Emails allowed to use SystemAdminAgent |
| `TIMEZONE` | Your timezone (default: America/New_York) |

## Multi-User Support

The agent supports multiple users, each with completely isolated data:

- **Lists & Todos** - each user has their own lists (groceries, movies, etc.) and todos
- **Memory** - facts remembered for one user aren't visible to others
- **Reminders** - per-user reminder scheduling
- **Automation Rules** - each user can set up their own weekly summaries and event triggers
- **Conversation History** - multi-turn sessions are tracked per user
- **Weekly Diary** - activity summaries generated for each user

Add allowed users to `ALLOWED_SENDERS` in `.env`, and optionally add their identities to `src/identities.py` for personalized greetings (e.g., "Hi Brandon" instead of "Hi there").

## Capabilities

### Calendar
- Schedule events: "Schedule a meeting tomorrow at 2pm"
- Query calendar: "What's on my calendar this week?"
- Multi-calendar support

### Lists & Todos
- Manage lists: "Add Inception to my movie list"
- Track todos: "Add todo: call mom"
- Mark complete: "Done with call mom"

### Reminders
- Set reminders: "Remind me to take medicine at 9pm"
- Future reminders: "Remind me about the meeting tomorrow at 3pm"

### Automation Rules
- Weekly summaries: "Send me my schedule every Sunday"
- Event triggers: "Remind me 3 days before any dentist appointment"

### Research
- Web search: "What are the best hiking trails in Colorado?"
- Weather: "What's the weather tomorrow?"
- Diary: "What did I do last week?"

### Memory
The agent remembers facts you mention:
- "My cat Oliver needs to go to the vet" → Remembers pet info
- Later: "Where's my vet?" → Recalls stored information

## Deployment

For cloud deployment (e.g., Google Cloud e2-micro VM):

```bash
# Using tmux for persistent sessions
tmux new -s agent -d 'uv run python -m src.adk_orchestrator' \; \
    split-window -h 'uv run python -m src.poller'
```

## Project Structure

```
src/
├── adk_orchestrator.py  # Main orchestrator loop
├── poller.py            # Email watcher
├── scheduler.py         # Background scheduler
├── config.py            # Centralized configuration
├── agents/              # ADK agents
│   ├── router.py        # Main RouterAgent
│   ├── calendar_agent.py
│   ├── personal_data_agent.py
│   ├── automation_agent.py
│   ├── research_agent.py
│   ├── system_agent.py
│   └── tools/           # Agent tool functions
├── clients/             # External service clients
├── sessions/            # Multi-turn conversation tracking
└── ...
```

## Testing

```bash
uv run pytest              # Run all tests
uv run pytest -v           # Verbose output
uv run pytest --cov=src    # With coverage
```

## Differences from Basic Setup

| Feature | Basic | Advanced |
|---------|-------|----------|
| Architecture | Single handler | Multi-agent ADK |
| Conversations | Single-turn | Multi-turn with memory |
| Scheduling | Basic | Cron + event triggers |
| Research | Simple | Sub-orchestrator pattern |
| Memory | None | Persistent fact storage |

## License

MIT License - See LICENSE file
