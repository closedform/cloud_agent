# Architecture Overview

This document explains how the cloud agent works under the hood.

## The Three Layers

### 1. The Ears: Poller (`src/poller.py`)

The poller is intentionally thin. It does one thing: watch Gmail and create task files.

**Flow:**
1. Connect to Gmail via IMAP
2. Check for unread emails from allowed senders
3. Parse the subject to determine intent
4. Extract body and attachments
5. Write a task file to `inputs/`

**Intent parsing:**
- Subject starts with `Research:` → research task
- Subject starts with `Calendar:` → calendar query task
- Subject contains "schedule" or "appointment" → schedule task
- Anything else → ignored

**Task file format:**
```json
{
  "id": "1706000000000",
  "intent": "research",
  "subject": "Research: me@example.com",
  "body": "What is async programming?",
  "reply_to": "me@example.com",
  "attachments": [],
  "created_at": "2026-01-26T12:00:00"
}
```

### 2. The Brain: Orchestrator (`src/orchestrator.py`)

The orchestrator is the central router. It watches the `inputs/` folder and dispatches tasks to the right handler.

**Handlers:**
- `handle_schedule()` → Parse with Gemini, create calendar event
- `handle_research()` → Query Gemini, email response
- `handle_calendar_query()` → Fetch events, query Gemini, email response

Each handler can use any combination of:
- Gemini for reasoning
- Clients for external APIs
- Email for responses

**Adding new handlers:**

1. Add a new intent in `src/poller.py`:
```python
elif subject_lower.startswith("todo:"):
    return "todo", reply_to
```

2. Add a handler in `src/orchestrator.py`:
```python
def handle_todo(task: dict):
    # Your logic here
    pass
```

3. Register it in `process_task()`:
```python
elif intent == "todo":
    handle_todo(task)
```

### 3. The Hands: Clients (`src/clients/`)

Clients wrap external APIs:

- `calendar.py` - Google Calendar (auth, create events, list events)
- `email.py` - SMTP (send responses)

**Adding new clients:**

Create a new file in `src/clients/` with functions for the API you're integrating. Keep it focused on a single service.

## Data Flow

```
Email arrives
    ↓
Poller parses intent
    ↓
Task file created in inputs/
    ↓
Orchestrator picks up task
    ↓
Routes to handler
    ↓
Handler uses Gemini + clients
    ↓
Response sent (email) or action taken (calendar)
    ↓
Task moved to processed/
```

## Why This Architecture?

**Separation of concerns:**
- Poller only does email → task conversion
- Orchestrator only does task → action routing
- Clients only do API operations

**Easy to extend:**
- New intent = new handler
- New API = new client
- No need to touch the core loop

**Debuggable:**
- Task files are JSON, easy to inspect
- Processed tasks are kept for review
- Each layer logs what it's doing

**Resilient:**
- Poller can fail without losing the orchestrator
- Tasks persist as files, survive restarts
- Handlers are isolated, one failure doesn't break others
