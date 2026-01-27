# Building a "Free" Always-On Cloud Agent

Every week there's a new AI "assistant" that wants (a) a subscription, (b) full access to everything you own, and (c) a permission slip to do security crimes on your behalf. I'm not saying all of them are bad. I'm saying I'd rather understand what's running, and I'd rather pay $0/month if I can.

This guide is the story (and the blueprint) for a small, purpose-built agent that runs 24/7, listens via email, and gives you a minimal, easy-to-extend framework for a personal assistant. It can manage your schedule, do research with web search, answer questions about your calendar, set reminders, and report its own status. We're starting with the basics on purpose--the whole point is that you can bolt on new capabilities as you need them. It's designed to be *cheap, persistent, and under your control*.

"Free" here means: if you stay inside the free tiers, you can keep monthly spend at $0. If you pick the wrong disk type/region or blow through quotas, you can absolutely get a bill.

## The economics (aka: no subscriptions)

The whole point is: this thing is an asset, not a liability. So we lean on services that already have generous free usage.

**The stack:**
- **Compute**: a GCP "Always Free" `e2-micro` VM (small, but fine for polling email + making API calls)
- **AI**: Gemini via the `google-genai` SDK. Two models:
  - `gemini-3-flash-preview` for general tasks (scheduling, calendar queries)
  - `gemini-2.5-flash` for research (because Google Search grounding is free on this model)
- **Email interface**: Gmail over IMAP/SMTP (with an app password)
- **Calendar**: Google Calendar API

If you keep it light, the steady-state is basically idle CPU + occasional API calls. That's exactly what free tiers are good at.

## The architecture (brain / ears / hands)

This is a task-based system. The poller listens for emails, parses intent, and creates task files. The orchestrator picks up those tasks and routes them to the right handler. Clean separation.

```
You --> [Email] --> Gmail --> [IMAP] --> Poller
                                           |
                                           | task files (atomic writes)
                                           v
                                      Orchestrator
                                           |
                                      [Gemini classifies intent]
                                           |
                    +----------------------+----------------------+
                    |                      |                      |
               schedule              research/help           reminder
                    |                      |                      |
               Calendar API           Gemini + Search         Timer
                    |                      |                      |
                    +----------+-----------+----------------------+
                               |
                               v
                         [SMTP] --> You
```

There are four moving parts:

### 1) The ears: `src/poller.py`

The poller is intentionally thin. It does one thing: watch Gmail and create task files.

**Flow:**
1. Connect to Gmail via IMAP
2. Check for unread emails from allowed senders
3. Extract subject, body, and attachments
4. Write a task file atomically to `inputs/` (prevents race conditions)

The poller doesn't think. It doesn't call Gemini. It just listens and creates work for the orchestrator to classify.

**Task file format (defined in `src/models/task.py`):**
```json
{
  "id": "1706000000000",
  "subject": "What is async programming?",
  "body": "",
  "sender": "me@example.com",
  "reply_to": "me@example.com",
  "attachments": [],
  "created_at": "2026-01-26T12:00:00"
}
```

### 2) The brain: `src/adk_orchestrator.py` and `src/agents/`

The ADK orchestrator watches the `inputs/` folder and delegates tasks to the RouterAgent, a multi-agent system built with Google ADK.

**Agent hierarchy:**
- `RouterAgent` (orchestrator) -> Routes to specialist agents, sends email responses
  - `CalendarAgent` -> Schedule events, query calendar
  - `ResearchAgent` -> Web search, weather, diary queries
  - `PersonalDataAgent` -> Lists, todos
  - `AutomationAgent` -> Reminders, rules
  - `SystemAgent` -> Status, help
  - `SystemAdminAgent` -> Crontab, git, tests (admin only)

Each agent has domain-specific tools in `src/agents/tools/`. Sub-agents return results via state (e.g., `{calendar_results}`), and RouterAgent composes the final email response.

After processing, tasks get moved to `processed/` for review. Tasks that fail to parse after `MAX_TASK_RETRIES` attempts (default: 3) are moved to `failed/` for manual inspection.

**Adding new capabilities:**

1. Add tools in `src/agents/tools/your_tools.py`:
```python
from src.agents.tools._context import get_user_email

def your_tool(param: str) -> dict:
    """Tool description for the agent."""
    email = get_user_email()
    return {"status": "success", "result": "..."}
```

2. Create an agent in `src/agents/your_agent.py`:
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

3. Add as sub-agent to RouterAgent in `src/agents/router.py` and update the routing guidelines in its instruction.

### 3) The config: `src/config.py`

Centralized configuration that loads `.env` once and caches the result. All paths are anchored to the project root (found by locating `pyproject.toml`).

```python
from src.config import get_config

config = get_config()  # Cached, safe to call multiple times
print(config.gemini_model)  # "gemini-3-flash-preview"
print(config.input_dir)     # /path/to/project/inputs
```

This eliminates scattered `load_dotenv()` calls and ensures consistent path handling.

### 4) The hands: `src/clients/`

Clients wrap external APIs:

- `calendar.py` - Google Calendar (auth, create events, list events)
- `email.py` - SMTP (send responses)

Want to add Todoist? Home Assistant? Notion? Create a new file in `src/clients/` with functions for the API you're integrating.

## What it can do (today)

The agent uses Gemini to understand your requests naturally. No rigid subject formats--just write what you want.

### Schedule events

```
Subject: Dentist appointment
Body: Dr. Smith next Tuesday at 2pm, should take about an hour
```

Gemini classifies this as a scheduling request, extracts the event details, and creates a calendar event. If you imply recurrence ("every Monday", "first Friday of the month"), it can create recurring events.

You can also attach images (screenshots of event flyers, etc.) and Gemini will parse them.

### Research (with web search)

```
Subject: What are the best practices for Python async?
Body: (optional extra context)
```

The orchestrator asks Gemini 2.5 Flash (which has free Google Search grounding) and emails the response back. This is the one place where we use a different model--2.5 Flash gets free web search, 3 Flash doesn't.

### Calendar Q&A

```
Subject: What do I have this week?
Body: (optional)
```

The orchestrator fetches your upcoming events from all calendars, gives Gemini the context, and emails you a human answer.

### Reminders

```
Subject: Remind me to meet with Einstein tomorrow at 3pm
Body: (optional)
```

Gemini extracts the reminder message and time. The orchestrator schedules it with `threading.Timer` and sends you a confirmation. When the time comes, you get an email with the reminder message as the subject line.

Natural language times work: "tomorrow at noon", "next tuesday at 9am", "friday at 3pm".

### Status check

```
Subject: Status
Body: (optional)
```

The orchestrator generates a health report:
- Model configuration (which Gemini models are configured)
- API status (tests connectivity to both models)
- Recent task history (last 10 processed tasks)
- Pending task count

Useful for debugging when you're not sure if the agent is alive.

### Help

```
Subject: What can you do?
Body: (optional)
```

Ask the agent about its own capabilities. It'll email you back with instructions.

## Setup (local first)

1) Install dependencies:

```bash
uv sync
```

2) Create your `.env`:

```bash
cp .env.example .env
```

Required:
- `GEMINI_API_KEY` from [aistudio.google.com](https://aistudio.google.com)
- `EMAIL_USER` and `EMAIL_PASS` (Gmail app password)
- `ALLOWED_SENDERS` (comma-separated list of emails that can control the agent)

Optional (defaults work for Gmail):
- `TIMEZONE` (default: "America/New_York")
- `DEFAULT_CALENDAR` (default: "primary")
- `IMAP_SERVER`, `SMTP_SERVER`, `SMTP_PORT`

3) Set up Google Calendar credentials:

- Download an OAuth "Desktop app" client as `credentials.json` and put it in the repo root.
- Run any calendar command once; it'll pop a browser for auth and create `token.json`.

```bash
uv run python -m src.cli.calendar_cli --list-calendars
```

4) Run the two processes:

```bash
# Terminal 1 (brain)
uv run python -m src.adk_orchestrator

# Terminal 2 (ears)
uv run python -m src.poller
```

## Deployment (the "potato" VM)

If you want the always-on version, deploy to a GCP "Always Free" VM and keep it running in `tmux`.

- The detailed walkthrough lives in `docs/deployment.md`.
- The short version:

```bash
git clone https://github.com/closedform/cloud_agent.git
cd cloud_agent
uv sync
tmux new -s agent -d 'uv run python -m src.adk_orchestrator' \; split-window -h 'uv run python -m src.poller'
```

## The two-model trick

Here's a detail worth calling out: we use two different Gemini models.

- **gemini-3-flash-preview** (default): Fast, capable, handles scheduling and calendar queries
- **gemini-2.5-flash** (research only): Has free Google Search grounding

Google Search grounding is what lets Gemini cite up-to-date web results. It's free on 2.5 Flash but not on 3 Flash. So research tasks specifically route to the older model. You can configure both via environment variables:

```bash
GEMINI_MODEL="gemini-3-flash-preview"
GEMINI_RESEARCH_MODEL="gemini-2.5-flash"
```

If Google changes the pricing or you get API access to grounding on 3 Flash, just update the config.

## Extending it

The easiest mental model is: add more specialist agents with domain-specific tools.

1. Add tools in `src/agents/tools/your_tools.py`
2. Create an agent in `src/agents/your_agent.py`
3. Add as sub-agent to RouterAgent in `src/agents/router.py`

Ideas: task management, home automation, expense tracking, flight monitoring, weather alerts.

## Project structure

```
src/
  config.py           # Centralized configuration (cached, immutable)
  services.py         # Service factory (Gemini client, Calendar service)
  task_io.py          # Atomic file I/O for task files
  adk_orchestrator.py # Brain: processes tasks via RouterAgent
  poller.py           # Ears: watches email, creates tasks
  scheduler.py        # Background scheduler for rules and diaries
  models/
    __init__.py
    task.py           # Task and Reminder dataclasses
  agents/
    router.py         # RouterAgent - orchestrates sub-agents
    calendar_agent.py
    research_agent.py
    personal_data_agent.py
    automation_agent.py
    system_agent.py
    system_admin_agent.py
    tools/            # Agent tool functions
  clients/
    calendar.py       # Google Calendar API
    email.py          # SMTP email
  cli/
    calendar_cli.py   # Calendar CLI tool
```

## A quick reality check (security + cost)

- Email is a great interface because it's universal... and also because it's a giant attack surface.
  - Keep `ALLOWED_SENDERS` tight.
  - Use a dedicated Gmail account.
  - Use an app password (not your real Gmail password).
- "Free tier" is real, but it's not magic.
  - Stay in eligible regions and use the free disk type.
  - Watch quotas if you start hammering Gemini or the Calendar API.
  - Send yourself a `Status:` email periodically to make sure things are healthy.

## Wrap-up

You end up with a small, explainable system: always on, low maintenance, and yours. It schedules things, answers questions, does research with real web results, and reports its own health. Just enough automation to be useful without turning into a runaway science project.

---

Source: `github.com/closedform/cloud_agent`
