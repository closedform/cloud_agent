# Architecture Overview

This document explains how the cloud agent works under the hood.

## The Four Layers

### 1. Configuration: `src/config.py`

Centralized, immutable configuration that loads `.env` once and caches the result.

```python
from src.config import get_config

config = get_config()  # Cached via @lru_cache
print(config.gemini_model)      # "gemini-3-flash-preview"
print(config.input_dir)         # /path/to/project/inputs
print(config.timezone)          # "America/New_York"
print(config.gemini_api_key)    # Your API key
```

Key features:
- **Single `load_dotenv()` call** - No scattered env loading
- **Path anchoring** - All paths relative to project root (found via `pyproject.toml`)
- **Immutable** - `@dataclass(frozen=True)` prevents accidental modification
- **Type-safe** - All config values are typed

### 2. The Ears: Poller (`src/poller.py`)

The poller is intentionally thin. It does one thing: watch Gmail and create task files.

**Flow:**
1. Connect to Gmail via IMAP
2. Check for unread emails from allowed senders
3. Extract subject, body, and attachments
4. Write a task file atomically to `inputs/`

The poller doesn't parse intent--it just passes the raw email data to the orchestrator.

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

**Atomic writes:** Task files are written using `write_task_atomic()` from `src/task_io.py`, which uses temp file + rename to prevent the orchestrator from reading partially-written files.

### 3. The Brain: Orchestrator (`src/orchestrator.py`)

The orchestrator is the central router. It watches the `inputs/` folder, classifies intent using Gemini, and dispatches tasks to the right handler.

**Intent Classification:**
When a task arrives, `classify_intent()` sends the subject and body to Gemini, which returns:
- Intent type (schedule, research, calendar_query, reminder, status, help)
- Summary of what the user wants
- Extracted data (e.g., reminder time and message)

**Services:** The orchestrator initializes services once at startup via `create_services()`:
```python
from src.services import create_services
from src.config import get_config

config = get_config()
services = create_services(config)  # Gemini client, Calendar service
```

This eliminates import-time side effects--`import src.orchestrator` no longer makes API calls or exits.

### 4. The Handlers: `src/handlers/`

Each handler is a separate module with a function decorated with `@register_handler`:

```
src/handlers/
  __init__.py       # Registry exports
  base.py           # @register_handler decorator, HANDLERS dict
  schedule.py       # Calendar event creation
  research.py       # Web research with Google Search
  calendar_query.py # Calendar Q&A
  reminder.py       # Scheduled reminders
  status.py         # Health reports
  help.py           # Usage information
```

**Handler signature:**
```python
from src.config import Config
from src.handlers.base import register_handler
from src.models import Task
from src.services import Services

@register_handler("schedule")
def handle_schedule(task: Task, config: Config, services: Services) -> None:
    # Use task.subject, task.body, etc.
    # Use config.gemini_model, config.input_dir, etc.
    # Use services.gemini_client, services.calendar_service, etc.
    pass
```

**Adding new handlers:**

1. Create a new handler file `src/handlers/todo.py`:
```python
from src.config import Config
from src.handlers.base import register_handler
from src.models import Task
from src.services import Services

@register_handler("todo")
def handle_todo(task: Task, config: Config, services: Services) -> None:
    # Your logic here
    pass
```

2. Import it in `src/handlers/__init__.py`:
```python
from src.handlers.todo import handle_todo
```

3. Add the intent to `classify_intent()` in orchestrator.py:
```python
# In the prompt, add to AVAILABLE INTENTS:
- "todo": Manage todo items (add, list, complete tasks)
```

### 5. The Hands: Clients (`src/clients/`)

Clients wrap external APIs:

- `calendar.py` - Google Calendar (auth, create events, list events)
- `email.py` - SMTP (send responses)

**Key change:** Clients now accept configuration as parameters rather than reading from environment directly. This makes them testable and removes import-time side effects.

```python
# Old (import-time side effects)
from dotenv import load_dotenv
load_dotenv()
EMAIL_USER = os.getenv("EMAIL_USER")

# New (explicit parameters)
def send_email(to_address, subject, body, email_user, email_pass, ...):
    ...
```

**Adding new clients:**

Create a new file in `src/clients/` with functions for the API you're integrating. Accept config values as parameters rather than reading from environment.

## Data Flow

```
Email arrives
    ↓
Poller creates Task object
    ↓
Task file written atomically to inputs/
    ↓
Orchestrator reads task safely (skips on parse error)
    ↓
classify_intent() determines handler
    ↓
Handler retrieved from registry: get_handler(intent)
    ↓
Handler executes with (task, config, services)
    ↓
Response sent (email) or action taken (calendar)
    ↓
Task moved to processed/
```

## Why This Architecture?

**No import-time side effects:**
- `import src.orchestrator` doesn't call APIs or exit
- Services initialized explicitly in `main()`
- Safe for testing and tooling

**Separation of concerns:**
- Config handles all environment/path logic
- Poller only does email → task conversion
- Orchestrator only does task → action routing
- Handlers focus on single intents
- Clients only do API operations

**Easy to extend:**
- New intent = new handler file with `@register_handler`
- New API = new client with explicit parameters
- No need to touch the core loop

**Race condition safe:**
- Atomic file writes prevent partial reads
- Safe reads return None on any parse error

**Debuggable:**
- Task files are JSON, easy to inspect
- Processed tasks are kept for review
- Each layer logs what it's doing

**Resilient:**
- Poller can fail without losing the orchestrator
- Tasks persist as files, survive restarts
- Handlers are isolated, one failure doesn't break others

## Models

The `src/models/` directory contains typed dataclasses:

**Task** (`src/models/task.py`):
```python
@dataclass
class Task:
    id: str
    subject: str
    body: str
    sender: str
    reply_to: str
    attachments: list[str]
    created_at: str
    intent: str | None
    classification: dict | None
```

**Reminder** (`src/models/task.py`):
```python
@dataclass
class Reminder:
    id: str
    message: str
    datetime: str  # ISO 8601
    reply_to: str
    created_at: str
```

Both have `to_dict()` and `from_dict()` methods for serialization.
