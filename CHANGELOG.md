# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Agent task system** (`src/models/agent_task.py`): Agents can create tasks for system execution (e.g., sending emails to third parties). Includes recipient whitelist enforcement for security.
- **Google ADK Multi-Agent Architecture**: Complete rewrite using Google Agent Development Kit
  - RouterAgent: Orchestrator that analyzes intent, delegates to specialists, sends email responses
  - CalendarAgent: Schedules events, queries calendar, lists calendars
  - PersonalDataAgent: Manages lists (movies, groceries, etc.) and todos with reminder scheduling
  - AutomationAgent: Creates reminders and automation rules (cron-based and event-triggered)
  - ResearchAgent: Sub-orchestrator for weather forecasts, diary queries, delegates web searches
  - WebSearchAgent: Web search using gemini-2.5-flash for free Google Search grounding
  - SystemAgent: Status checks and help/capabilities
  - SystemAdminAgent: Crontab management, disk/memory monitoring, git operations, tests
- **Multi-turn conversations**: Thread ID from normalized subject + sender enables conversational context
- **Session management** (`src/sessions/`): FileSessionStore for conversation tracking
- **Persistent memory** (`src/memory.py`): Store/recall user facts across conversations
- **Weekly diary** (`src/diary.py`): Activity summaries generated from todos, reminders, and calendar
- **Automation rules** (`src/rules.py`): Time-based (cron) and event-based (calendar triggers)
- **Background scheduler** (`src/scheduler.py`): 60s interval thread for rules and weekly diary generation
- **User identities** (`src/identities.py`): Maps email addresses to user identities for personalization
- **Per-user data storage** (`src/user_data.py`): Persistent storage for lists and todos
- **Agent tools** (`src/agents/tools/`): Domain-specific tools with thread-safe context helpers
- **Test suite** (`tests/`): Comprehensive pytest tests with fixtures for all core components

### Fixed

- Consolidated atomic file writes in task_io module to prevent race conditions
- Critical bug fixes from stress testing (session handling, file operations)
- HTML detection and preservation in text_to_html conversion
- Request context now uses shared dict instead of threading.local for reliability
- Task processing only marks complete when email sent or response generated
- Timezone-naive datetime usage corrected throughout codebase
- ADK variable substitution errors in agent instructions
- Sub-agent response handling that could break orchestration flow
- Email fallback detection and research agent variable handling
- API retry logic now catches google.genai.errors.ServerError

### Changed

- **Replaced handler-based architecture with ADK agents**: Sub-agents return results via `output_key` state, RouterAgent composes responses
- **New orchestrator** (`src/adk_orchestrator.py`): Processes task files, manages sessions, runs background scheduler
- Default model changed to gemini-3-flash-preview
- Poller simplified to only create task files from unread emails
- Calendar client enhanced with better timezone handling and event querying
- Email client enhanced with conversation tracking and reply-to handling

### Removed

- Old handler-based system (`src/handlers/`)
- Old orchestrator (`src/orchestrator.py`)

## [0.1.0] - 2025-01-26

### Added

- Orchestrator with Gemini 3 Flash integration for natural language processing
- Configurable model selection via GEMINI_MODEL environment variable
- Email poller for IMAP-based command input with sender filtering
- Google Calendar client with full CRUD operations
- Dynamic calendar routing and auto-creation
- Support for recurring events via RRULE
- Multi-calendar support with fuzzy name matching
- Image and text input processing
- Research feature with web search
- Calendar query feature
- Task-based queue system (JSON files in inputs/ folder)
- Deployment guide for GCP free tier (e2-micro)
- Tutorial documentation with architecture overview

[Unreleased]: https://github.com/closedform/cloud_agent/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/closedform/cloud_agent/releases/tag/v0.1.0
