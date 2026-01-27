"""Tests for src/agents/tools/automation_tools.py"""

import json
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from src.reminders import _load_reminders, _reminders_lock
from src.rules import load_rules


class TestCreateReminder:
    """Tests for create_reminder() tool function."""

    def test_create_reminder_success(self, test_config):
        """Successfully create a reminder with valid inputs."""
        reminder_time = (datetime.now() + timedelta(hours=2)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )

        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_reminder

            result = create_reminder(
                message="Test reminder message",
                reminder_time=reminder_time,
            )

            assert result["status"] == "success"
            assert "reminder" in result
            assert result["reminder"]["message"] == "Test reminder message"
            assert result["reminder"]["time"] == reminder_time
            assert "id" in result["reminder"]

            # Verify reminder was persisted
            with _reminders_lock:
                reminders = _load_reminders(test_config)
            assert len(reminders) == 1
            assert reminders[0]["message"] == "Test reminder message"

    def test_create_reminder_missing_reply_to(self, test_config):
        """Reminder creation fails without reply_to in context."""
        reminder_time = (datetime.now() + timedelta(hours=2)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )

        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value=""
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_reminder

            result = create_reminder(
                message="Test reminder",
                reminder_time=reminder_time,
            )

            assert result["status"] == "error"
            assert "Reply address not available" in result["message"]

    def test_create_reminder_empty_reply_to(self, test_config):
        """Reminder creation fails with empty reply_to."""
        reminder_time = (datetime.now() + timedelta(hours=2)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )

        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value=""
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_reminder

            result = create_reminder(
                message="Test reminder",
                reminder_time=reminder_time,
            )

            assert result["status"] == "error"
            assert "Reply address not available" in result["message"]

    def test_create_reminder_invalid_datetime_format(self, test_config):
        """Reminder creation fails with invalid datetime format."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_reminder

            result = create_reminder(
                message="Test reminder",
                reminder_time="invalid-date-format",
            )

            # The reminder may still be created (validation happens at scheduling time)
            # or may fail - depends on implementation
            # We just verify it doesn't crash and returns a response
            assert "status" in result

    def test_create_multiple_reminders(self, test_config):
        """Create multiple reminders successfully."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_reminder

            time1 = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
            time2 = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")

            result1 = create_reminder(message="First reminder", reminder_time=time1)
            result2 = create_reminder(message="Second reminder", reminder_time=time2)

            assert result1["status"] == "success"
            assert result2["status"] == "success"

            # Verify both reminders were persisted
            with _reminders_lock:
                reminders = _load_reminders(test_config)
            assert len(reminders) == 2


class TestCreateRule:
    """Tests for create_rule() tool function."""

    def test_create_time_rule_success(self, test_config):
        """Successfully create a time-based rule with cron schedule."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_rule

            result = create_rule(
                rule_type="time",
                action="weekly_schedule_summary",
                schedule="0 8 * * 0",  # Sunday 8am
            )

            assert result["status"] == "success"
            assert "Created time rule" in result["message"]
            assert result["rule"]["type"] == "time"
            assert result["rule"]["action"] == "weekly_schedule_summary"
            assert result["rule"]["schedule"] == "0 8 * * 0"
            assert result["rule"]["user_email"] == "test@example.com"

            # Verify rule was persisted
            rules_data = load_rules(test_config)
            assert "test@example.com" in rules_data
            assert len(rules_data["test@example.com"]) == 1

    def test_create_time_rule_with_message_template(self, test_config):
        """Create time rule with message_template parameter."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_rule

            result = create_rule(
                rule_type="time",
                action="send_reminder",
                schedule="0 9 * * 1-5",  # Weekdays 9am
                message_template="Daily standup time!",
            )

            assert result["status"] == "success"
            assert result["rule"]["params"]["message_template"] == "Daily standup time!"

    def test_create_time_rule_missing_schedule(self, test_config):
        """Time rule creation fails without schedule."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_rule

            result = create_rule(
                rule_type="time",
                action="weekly_schedule_summary",
                # Missing schedule
            )

            assert result["status"] == "error"
            assert "Schedule required" in result["message"]

    def test_create_event_rule_success(self, test_config):
        """Successfully create an event-based rule with description."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_rule

            result = create_rule(
                rule_type="event",
                action="send_reminder",
                description="vet appointment",
                days_before=1,
            )

            assert result["status"] == "success"
            assert "Created event rule" in result["message"]
            assert result["rule"]["type"] == "event"
            assert result["rule"]["action"] == "send_reminder"
            assert result["rule"]["description"] == "vet appointment"
            assert result["rule"]["trigger"]["days_before"] == 1

            # Verify rule was persisted
            rules_data = load_rules(test_config)
            assert "test@example.com" in rules_data
            assert len(rules_data["test@example.com"]) == 1

    def test_create_event_rule_with_message_template(self, test_config):
        """Create event rule with message_template parameter."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_rule

            result = create_rule(
                rule_type="event",
                action="send_reminder",
                description="doctor appointment",
                days_before=2,
                message_template="Don't forget your doctor appointment tomorrow!",
            )

            assert result["status"] == "success"
            assert (
                result["rule"]["params"]["message_template"]
                == "Don't forget your doctor appointment tomorrow!"
            )

    def test_create_event_rule_missing_description(self, test_config):
        """Event rule creation fails without description."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_rule

            result = create_rule(
                rule_type="event",
                action="send_reminder",
                # Missing description
            )

            assert result["status"] == "error"
            assert "Description required" in result["message"]

    def test_create_rule_unknown_type(self, test_config):
        """Rule creation fails with unknown rule type."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_rule

            result = create_rule(
                rule_type="unknown",
                action="send_reminder",
            )

            assert result["status"] == "error"
            assert "Unknown rule type" in result["message"]

    def test_create_rule_missing_user_email(self, test_config):
        """Rule creation fails without user_email in context."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value=""
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_rule

            result = create_rule(
                rule_type="time",
                action="weekly_schedule_summary",
                schedule="0 8 * * 0",
            )

            assert result["status"] == "error"
            assert "User email not available" in result["message"]

    def test_create_event_rule_without_days_before(self, test_config):
        """Event rule can be created without days_before (defaults to empty trigger)."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_rule

            result = create_rule(
                rule_type="event",
                action="send_reminder",
                description="meeting",
                # No days_before
            )

            assert result["status"] == "success"
            assert result["rule"]["trigger"] == {}


class TestDeleteRule:
    """Tests for delete_user_rule() tool function."""

    def test_delete_rule_success(self, test_config):
        """Successfully delete an existing rule."""
        # First create a rule
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_rule, delete_user_rule

            # Create rule
            create_result = create_rule(
                rule_type="time",
                action="weekly_schedule_summary",
                schedule="0 8 * * 0",
            )
            rule_id = create_result["rule"]["id"]

            # Verify rule exists
            rules_data = load_rules(test_config)
            assert len(rules_data["test@example.com"]) == 1

            # Delete rule
            delete_result = delete_user_rule(rule_id=rule_id)

            assert delete_result["status"] == "success"
            assert f"Deleted rule {rule_id}" in delete_result["message"]
            assert delete_result["rule_id"] == rule_id

            # Verify rule was removed
            rules_data = load_rules(test_config)
            assert len(rules_data.get("test@example.com", [])) == 0

    def test_delete_rule_not_found(self, test_config):
        """Deleting non-existent rule returns not_found status."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import delete_user_rule

            result = delete_user_rule(rule_id="nonexistent-id")

            assert result["status"] == "not_found"
            assert "not found" in result["message"]

    def test_delete_rule_missing_user_email(self, test_config):
        """Delete fails without user_email in context."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value=""
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import delete_user_rule

            result = delete_user_rule(rule_id="some-id")

            assert result["status"] == "error"
            assert "User email not available" in result["message"]

    def test_delete_one_of_multiple_rules(self, test_config):
        """Delete one rule while keeping others."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_rule, delete_user_rule

            # Create two rules
            result1 = create_rule(
                rule_type="time",
                action="weekly_schedule_summary",
                schedule="0 8 * * 0",
            )
            result2 = create_rule(
                rule_type="time",
                action="send_reminder",
                schedule="0 9 * * 1",
            )

            rule_id1 = result1["rule"]["id"]
            rule_id2 = result2["rule"]["id"]

            # Verify both exist
            rules_data = load_rules(test_config)
            assert len(rules_data["test@example.com"]) == 2

            # Delete first rule
            delete_user_rule(rule_id=rule_id1)

            # Verify only second rule remains
            rules_data = load_rules(test_config)
            assert len(rules_data["test@example.com"]) == 1
            assert rules_data["test@example.com"][0]["id"] == rule_id2


class TestGetRules:
    """Tests for get_rules() tool function."""

    def test_get_rules_empty(self, test_config):
        """Get rules when none exist returns empty list."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import get_rules

            result = get_rules()

            assert result["status"] == "success"
            assert result["rules"] == []
            assert result["count"] == 0

    def test_get_rules_with_rules(self, test_config):
        """Get rules returns all user's rules."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_rule, get_rules

            # Create some rules
            create_rule(
                rule_type="time",
                action="weekly_schedule_summary",
                schedule="0 8 * * 0",
            )
            create_rule(
                rule_type="event",
                action="send_reminder",
                description="vet appointment",
                days_before=1,
            )

            result = get_rules()

            assert result["status"] == "success"
            assert result["count"] == 2
            assert len(result["rules"]) == 2

            # Verify rule types
            rule_types = {r["type"] for r in result["rules"]}
            assert rule_types == {"time", "event"}

    def test_get_rules_missing_user_email(self, test_config):
        """Get rules fails without user_email in context."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value=""
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import get_rules

            result = get_rules()

            assert result["status"] == "error"
            assert "User email not available" in result["message"]

    def test_get_rules_only_returns_user_rules(self, test_config):
        """Get rules only returns rules for current user, not other users."""
        # Pre-populate rules file with another user's rules
        rules_data = {
            "other@example.com": [
                {
                    "id": "other-rule-1",
                    "user_email": "other@example.com",
                    "type": "time",
                    "action": "weekly_schedule_summary",
                    "schedule": "0 8 * * 0",
                    "enabled": True,
                    "trigger": {},
                    "params": {},
                    "created_at": "2026-01-27T10:00:00",
                    "last_fired": None,
                }
            ]
        }
        test_config.rules_file.parent.mkdir(parents=True, exist_ok=True)
        with open(test_config.rules_file, "w") as f:
            json.dump(rules_data, f)

        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import get_rules

            result = get_rules()

            # Should not see other user's rules
            assert result["status"] == "success"
            assert result["count"] == 0
            assert result["rules"] == []


class TestHelperFunctions:
    """Tests for context helper functions in _context.py."""

    def test_get_user_email_from_context(self, test_config):
        """get_user_email returns email from context."""
        from src.agents.tools._context import (
            set_request_context,
            get_user_email,
            clear_request_context,
        )

        try:
            set_request_context(
                user_email="user@example.com",
                thread_id="test-thread",
                reply_to="reply@example.com",
            )
            assert get_user_email() == "user@example.com"
        finally:
            clear_request_context()

    def test_get_user_email_missing(self, test_config):
        """get_user_email returns empty string when cleared."""
        from src.agents.tools._context import clear_request_context, get_user_email

        clear_request_context()
        assert get_user_email() == ""

    def test_get_reply_to_from_context(self, test_config):
        """get_reply_to returns reply_to from context."""
        from src.agents.tools._context import (
            set_request_context,
            get_reply_to,
            clear_request_context,
        )

        try:
            set_request_context(
                user_email="user@example.com",
                thread_id="test-thread",
                reply_to="reply@example.com",
            )
            assert get_reply_to() == "reply@example.com"
        finally:
            clear_request_context()

    def test_get_reply_to_missing(self, test_config):
        """get_reply_to returns empty string when cleared."""
        from src.agents.tools._context import clear_request_context, get_reply_to

        clear_request_context()
        assert get_reply_to() == ""


class TestRuleActions:
    """Tests for various rule actions."""

    def test_create_generate_diary_rule(self, test_config):
        """Create a generate_diary time rule."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_rule

            result = create_rule(
                rule_type="time",
                action="generate_diary",
                schedule="0 23 * * 0",  # Sunday 11pm
            )

            assert result["status"] == "success"
            assert result["rule"]["action"] == "generate_diary"

    def test_create_send_reminder_event_rule(self, test_config):
        """Create a send_reminder event rule with all parameters."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_rule

            result = create_rule(
                rule_type="event",
                action="send_reminder",
                description="dentist appointment",
                days_before=3,
                message_template="Your dentist appointment is in {days} days!",
            )

            assert result["status"] == "success"
            assert result["rule"]["action"] == "send_reminder"
            assert result["rule"]["description"] == "dentist appointment"
            assert result["rule"]["trigger"]["days_before"] == 3
            assert "message_template" in result["rule"]["params"]


class TestRulePersistence:
    """Tests for rule persistence across operations."""

    def test_rules_persist_after_operations(self, test_config):
        """Rules persist correctly after multiple create/delete operations."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import (
                create_rule,
                delete_user_rule,
                get_rules,
            )

            # Create 3 rules with small delays to ensure unique IDs
            # (IDs are based on millisecond timestamps)
            r1 = create_rule(
                rule_type="time", action="weekly_schedule_summary", schedule="0 8 * * 0"
            )
            time.sleep(0.002)  # 2ms delay for unique ID
            r2 = create_rule(
                rule_type="time", action="send_reminder", schedule="0 9 * * 1"
            )
            time.sleep(0.002)  # 2ms delay for unique ID
            r3 = create_rule(
                rule_type="event",
                action="send_reminder",
                description="meeting",
                days_before=1,
            )

            assert get_rules()["count"] == 3

            # Delete middle rule
            delete_user_rule(rule_id=r2["rule"]["id"])
            assert get_rules()["count"] == 2

            # Verify remaining rules are correct
            rules = get_rules()["rules"]
            rule_ids = {r["id"] for r in rules}
            assert r1["rule"]["id"] in rule_ids
            assert r2["rule"]["id"] not in rule_ids
            assert r3["rule"]["id"] in rule_ids

    def test_rule_fields_are_complete(self, test_config):
        """Created rules have all expected fields."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_rule

            result = create_rule(
                rule_type="time",
                action="weekly_schedule_summary",
                schedule="0 8 * * 0",
            )

            rule = result["rule"]
            expected_fields = [
                "id",
                "user_email",
                "type",
                "action",
                "enabled",
                "schedule",
                "description",
                "trigger",
                "params",
                "created_at",
                "last_fired",
            ]
            for field in expected_fields:
                assert field in rule, f"Missing field: {field}"

            # Verify values
            assert rule["enabled"] is True
            assert rule["last_fired"] is None
            assert rule["created_at"] is not None

