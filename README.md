# Cloud Agent

**Your own AI agent running 24/7 in the cloud. For free.**

An autonomous agent that runs on Google's free infrastructure forever.

## What You Get

- **Always-on AI agent** - Runs 24/7 on GCP's free tier (e2-micro VM)
- **Gemini 3 Flash** - Google's latest multimodal model, free tier available
- **Email interface** - Send commands from anywhere, no app needed
- **Smart calendar management** - Natural language scheduling with auto-routing
- **Extensible foundation** - Add your own tools and capabilities

**Total monthly cost: $0.00**

## How It Works

```
You ──email──> Gmail ──IMAP──> Agent ──Gemini──> Google Calendar
                                 │
                           (your VM, always on)
```

Email the agent: *"Schedule dentist appointment next Tuesday at 2pm"*

The agent parses it with Gemini, creates the event, and routes it to the right calendar. It handles recurring events, multiple calendars, and creates new ones on demand.

### Research Mode

Email with subject `Research: <email>` (case-insensitive) and your question in the body. The agent will research and send the response to the specified email.

Example:
- Subject: `Research: me@example.com`
- Body: `What are the best practices for Python async programming?`

### Calendar Query Mode

Email with subject `Calendar: <email>` (case-insensitive) and your question in the body. The agent will check your calendars and respond.

Examples:
- Subject: `Calendar: me@example.com`
- Body: `When is my next dentist appointment?`

- Subject: `Calendar: me@example.com`
- Body: `What events do I have this week on the work calendar?`

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/closedform/cloud_agent.git
cd cloud_agent

# Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Configure your API keys
cp .env.example .env
# Edit .env with your Gemini API key and Gmail app password
```

### 2. Get your credentials

- **Gemini API Key**: Free from [aistudio.google.com](https://aistudio.google.com)
- **Gmail App Password**: From [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
- **Google Calendar**: Run `uv run python -m src.clients.calendar --auth` to authorize

### 3. Run locally (to test)

```bash
# Terminal 1: The brain (processes tasks)
uv run python -m src.orchestrator

# Terminal 2: The ears (listens for emails)
uv run python -m src.poller
```

### 4. Deploy to the cloud

Follow [docs/deployment.md](docs/deployment.md) to set up your free GCP VM.

## Project Structure

```
cloud_agent/
├── src/
│   ├── orchestrator.py      # Brain: Gemini-powered task processor
│   ├── poller.py            # Ears: IMAP listener for commands
│   └── clients/
│       └── calendar.py      # Hands: Google Calendar operations
├── docs/
│   ├── deployment.md        # Cloud deployment guide
│   └── tutorial.md          # Architecture deep-dive
├── .env.example
├── pyproject.toml
├── README.md
└── CHANGELOG.md
```

## Extending the Agent

This is a starting point. The architecture is intentionally simple - add new "tools" by:

1. Writing a new client in `src/clients/`
2. Adding routing logic to `src/poller.py`
3. Updating the system prompt in `src/orchestrator.py`

Ideas: task management, home automation, expense tracking, flight monitoring.

### Deploying Updates

Once your VM is set up, deploy changes with git:

```bash
# On your local machine: make changes, commit, push
git add . && git commit -m "Add new feature" && git push

# On your VM: pull and restart
cd ~/cloud_agent
git pull
uv sync
tmux kill-session -t agent
tmux new -s agent -d 'uv run python -m src.orchestrator' \; split-window -h 'uv run python -m src.poller'
```

## Documentation

- [docs/tutorial.md](docs/tutorial.md) - Architecture deep-dive and philosophy
- [docs/deployment.md](docs/deployment.md) - Step-by-step cloud deployment guide

## License

MIT
