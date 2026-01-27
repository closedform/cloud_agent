# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Refactored to flexible orchestrator architecture
- Poller is now thin: parses emails, creates task files in inputs/
- Orchestrator is the central brain: processes all task types
- Extracted email sending to src/clients/email.py

### Added

- Research feature: email with subject "Research: <email>" and query in body
- Calendar query feature: email with subject "Calendar: <email>" and question in body
- Task-based queue system (JSON files in inputs/ folder)

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
- Deployment guide for GCP free tier (e2-micro)
- Tutorial documentation with architecture overview

[Unreleased]: https://github.com/closedform/cloud_agent/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/closedform/cloud_agent/releases/tag/v0.1.0
