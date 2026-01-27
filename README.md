# Cloud Agent

**Your own AI agent running 24/7 in the cloud. For free.**

An autonomous agent that runs on Google's free infrastructure. It listens for commands via email, routes them to the right handler, and responds.

## What You Get

- **Always-on AI agent** - Runs 24/7 on GCP's free tier (e2-micro VM)
- **Gemini 3 Flash** - Google's multimodal model, free tier available
- **Email interface** - Send commands from anywhere, no app needed
- **Extensible architecture** - Add new capabilities easily

**Total monthly cost: $0.00** (within free tier limits)

## Architecture

```
              (inbound)                              (outbound)
+------+    email    +-------+   IMAP   +---------+
| You  | ---------> | Gmail | -------> | Poller  |
+------+            +-------+          +---------+
   ^                                        |
   |                                        | creates task files
   |                                        v
   |                                   +-------------+
   |                                   | Orchestrator |
   |                                   +-------------+
   |                                        |
   |         routes by intent:              |
   |         - schedule    -> Calendar API  |
   |         - research    -> Gemini -------+---> SMTP --> You
   |         - calendar_query -> Gemini ----+
   |         - reminder    -> reminders.json +
   |         - status      -> Health check --+
   |                                        |
   +----------------------------------------+
```

**Poller** (`src/poller.py`) - Watches Gmail, parses intent, drops task files
**Orchestrator** (`src/orchestrator.py`) - Processes tasks, routes to handlers
**Clients** (`src/clients/`) - Calendar, email, and future integrations

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
- **Google Calendar**: Run `uv run python -m src.clients.calendar --list-calendars` to authorize

### Run Locally

```bash
# Terminal 1: Orchestrator (brain)
uv run python -m src.orchestrator

# Terminal 2: Poller (ears)
uv run python -m src.poller
```

### Deploy to Cloud

See [docs/deployment.md](docs/deployment.md) for the full GCP setup guide.

Quick version:
```bash
git clone https://github.com/closedform/cloud_agent.git
cd cloud_agent && uv sync
tmux new -s agent -d 'uv run python -m src.orchestrator' \; split-window -h 'uv run python -m src.poller'
```

## Project Structure

```
cloud_agent/
├── src/
│   ├── orchestrator.py      # Brain: routes tasks to handlers
│   ├── poller.py            # Ears: parses email, creates tasks
│   └── clients/
│       ├── calendar.py      # Google Calendar operations
│       └── email.py         # SMTP email sending
├── docs/
│   ├── deployment.md        # GCP deployment guide
│   └── tutorial.md          # Architecture deep-dive
├── inputs/                  # Task queue (created at runtime)
├── processed/               # Completed tasks (created at runtime)
├── .env.example
├── pyproject.toml
└── README.md
```

## Extending

Add new capabilities:

1. Create a client in `src/clients/` (e.g., `tasks.py`, `notes.py`)
2. Add intent parsing in `src/poller.py`
3. Add handler in `src/orchestrator.py`

Ideas: task management, home automation, expense tracking, flight monitoring.

## Documentation

- [docs/deployment.md](docs/deployment.md) - GCP deployment guide
- [docs/tutorial.md](docs/tutorial.md) - Architecture overview

## License

MIT
