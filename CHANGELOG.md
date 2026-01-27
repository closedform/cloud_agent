# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- AI-powered intent classification: Gemini parses natural language requests instead of rigid subject formats
- Status command: check agent health, API connectivity, and recent tasks
- Reminder feature: set reminders that fire at scheduled times using threading.Timer
- Help feature: ask the agent about its own capabilities
- Separate research model (gemini-2.5-flash) for free Google Search grounding

### Changed

- Refactored to flexible orchestrator architecture
- Poller is now ultra-thin: just extracts email data and creates task files
- Orchestrator classifies intent with Gemini, then routes to handlers
- Reminders use threading.Timer for precise scheduling (no polling)
- Default poll interval changed to 60 seconds (was 1800)

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
