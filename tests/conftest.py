"""Shared test fixtures and configuration."""

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest


@dataclass(frozen=True)
class TestConfig:
    """Test configuration matching the real Config interface."""

    gemini_api_key: str = "test-api-key"
    gemini_model: str = "test-model"
    gemini_research_model: str = "test-research-model"
    email_user: str = "test@example.com"
    email_pass: str = "test-password"
    allowed_senders: tuple[str, ...] = ("allowed@example.com",)
    admin_emails: tuple[str, ...] = ("admin@example.com",)
    poll_interval: int = 60
    imap_server: str = "imap.test.com"
    smtp_server: str = "smtp.test.com"
    smtp_port: int = 587
    project_root: Path = Path("/tmp/test_project")
    input_dir: Path = Path("/tmp/test_project/inputs")
    processed_dir: Path = Path("/tmp/test_project/processed")
    failed_dir: Path = Path("/tmp/test_project/failed")
    reminders_file: Path = Path("/tmp/test_project/reminders.json")
    reminder_log_file: Path = Path("/tmp/test_project/reminder_log.json")
    user_data_file: Path = Path("/tmp/test_project/user_data.json")
    rules_file: Path = Path("/tmp/test_project/rules.json")
    diary_file: Path = Path("/tmp/test_project/diary.json")
    triggered_file: Path = Path("/tmp/test_project/triggered.json")
    sessions_file: Path = Path("/tmp/test_project/sessions.json")
    token_path: Path = Path("/tmp/test_project/token.json")
    credentials_path: Path = Path("/tmp/test_project/credentials.json")
    max_task_retries: int = 3
    timezone: str = "America/New_York"
    default_calendar: str = "primary"


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_config(temp_dir: Path) -> TestConfig:
    """Create a test configuration with temporary paths."""
    return TestConfig(
        project_root=temp_dir,
        input_dir=temp_dir / "inputs",
        processed_dir=temp_dir / "processed",
        failed_dir=temp_dir / "failed",
        reminders_file=temp_dir / "reminders.json",
        reminder_log_file=temp_dir / "reminder_log.json",
        user_data_file=temp_dir / "user_data.json",
        rules_file=temp_dir / "rules.json",
        diary_file=temp_dir / "diary.json",
        triggered_file=temp_dir / "triggered.json",
        sessions_file=temp_dir / "sessions.json",
        token_path=temp_dir / "token.json",
        credentials_path=temp_dir / "credentials.json",
    )


@pytest.fixture
def mock_gemini_client():
    """Create a mock Gemini client."""
    client = MagicMock()

    def make_response(text: str):
        response = MagicMock()
        response.text = text
        return response

    client.models.generate_content.return_value = make_response('{"result": "test"}')
    client.make_response = make_response
    return client


@pytest.fixture
def mock_services(mock_gemini_client):
    """Create mock services container."""
    services = MagicMock()
    services.gemini_client = mock_gemini_client
    services.calendar_service = None
    services.calendars = {"primary": "primary"}
    services.get_identity.return_value = None
    return services


@pytest.fixture
def sample_task() -> dict[str, Any]:
    """Create a sample task dictionary."""
    return {
        "id": "test-task-123",
        "subject": "Test Subject",
        "body": "Test body content",
        "sender": "sender@example.com",
        "reply_to": "sender@example.com",
        "attachments": [],
        "created_at": "2026-01-27T12:00:00",
    }


@pytest.fixture
def user_data_file(temp_dir: Path) -> Path:
    """Create an empty user data file path."""
    return temp_dir / "user_data.json"


@pytest.fixture
def populated_user_data(user_data_file: Path) -> Path:
    """Create a user data file with sample data."""
    data = {
        "user1@example.com": {
            "lists": {
                "movies": ["Inception", "The Matrix"],
                "books": ["Dune"],
            },
            "todos": [
                {
                    "id": "todo-1",
                    "text": "Call Einstein",
                    "done": False,
                    "created_at": "2026-01-27T10:00:00",
                },
                {
                    "id": "todo-2",
                    "text": "Buy groceries",
                    "done": True,
                    "created_at": "2026-01-26T10:00:00",
                    "completed_at": "2026-01-26T15:00:00",
                },
            ],
        },
        "user2@example.com": {
            "lists": {
                "movies": ["Pride and Prejudice"],
            },
            "todos": [],
        },
    }
    user_data_file.parent.mkdir(parents=True, exist_ok=True)
    with open(user_data_file, "w") as f:
        json.dump(data, f)
    return user_data_file
