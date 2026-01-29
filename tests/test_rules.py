"""Tests for src/rules.py - Rule storage and CRUD operations."""

import json
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from src.rules import (
    Rule,
    add_rule,
    cleanup_old_triggered,
    delete_rule,
    get_user_rules,
    is_event_triggered,
    load_rules,
    load_triggered,
    mark_event_triggered,
    save_rules,
    save_triggered,
    update_rule_last_fired,
)


class TestRuleDataclass:
    """Tests for Rule dataclass creation and factory methods."""

    def test_create_rule_with_required_fields(self):
        """Test creating a Rule with required fields only."""
        rule = Rule(
            id="rule-123",
            user_email="user@example.com",
            type="time",
            action="send_reminder",
        )
        assert rule.id == "rule-123"
        assert rule.user_email == "user@example.com"
        assert rule.type == "time"
        assert rule.action == "send_reminder"
        assert rule.enabled is True
        assert rule.schedule is None
        assert rule.description is None
        assert rule.trigger == {}
        assert rule.params == {}
        assert rule.last_fired is None
        # created_at should be set automatically
        assert rule.created_at is not None

    def test_create_rule_with_all_fields(self):
        """Test creating a Rule with all fields specified."""
        rule = Rule(
            id="rule-456",
            user_email="user@example.com",
            type="event",
            action="weekly_schedule_summary",
            enabled=False,
            schedule="0 9 * * 1",
            description="Vet appointment",
            trigger={"days_before": 3},
            params={"include_weather": True},
            created_at="2026-01-01T10:00:00",
            last_fired="2026-01-15T09:00:00",
        )
        assert rule.id == "rule-456"
        assert rule.enabled is False
        assert rule.schedule == "0 9 * * 1"
        assert rule.description == "Vet appointment"
        assert rule.trigger == {"days_before": 3}
        assert rule.params == {"include_weather": True}
        assert rule.created_at == "2026-01-01T10:00:00"
        assert rule.last_fired == "2026-01-15T09:00:00"

    def test_create_time_rule(self):
        """Test creating a time-based rule via factory method."""
        with patch("src.rules.time.time", return_value=1700000000.123):
            rule = Rule.create_time_rule(
                user_email="user@example.com",
                schedule="0 9 * * 1",
                action="weekly_schedule_summary",
                params={"days": 7},
            )

        assert rule.id == "1700000000123"
        assert rule.user_email == "user@example.com"
        assert rule.type == "time"
        assert rule.action == "weekly_schedule_summary"
        assert rule.schedule == "0 9 * * 1"
        assert rule.params == {"days": 7}
        assert rule.enabled is True
        assert rule.description is None
        assert rule.trigger == {}

    def test_create_time_rule_without_params(self):
        """Test creating a time-based rule without params."""
        rule = Rule.create_time_rule(
            user_email="user@example.com",
            schedule="0 8 * * *",
            action="generate_diary",
        )
        assert rule.params == {}

    def test_create_event_rule(self):
        """Test creating an event-based rule via factory method."""
        with patch("src.rules.time.time", return_value=1700000000.456):
            rule = Rule.create_event_rule(
                user_email="user@example.com",
                description="vet appointment",
                trigger={"days_before": 2},
                action="send_reminder",
                params={"message": "Don't forget the cat carrier!"},
            )

        assert rule.id == "1700000000456"
        assert rule.user_email == "user@example.com"
        assert rule.type == "event"
        assert rule.action == "send_reminder"
        assert rule.description == "vet appointment"
        assert rule.trigger == {"days_before": 2}
        assert rule.params == {"message": "Don't forget the cat carrier!"}
        assert rule.enabled is True
        assert rule.schedule is None

    def test_create_event_rule_without_params(self):
        """Test creating an event-based rule without params."""
        rule = Rule.create_event_rule(
            user_email="user@example.com",
            description="meeting",
            trigger={"hours_before": 1},
            action="send_reminder",
        )
        assert rule.params == {}


class TestRuleSerialization:
    """Tests for Rule serialization (to_dict, from_dict)."""

    def test_to_dict(self):
        """Test converting a Rule to dictionary."""
        rule = Rule(
            id="rule-789",
            user_email="user@example.com",
            type="time",
            action="weekly_schedule_summary",
            enabled=True,
            schedule="0 9 * * 1",
            description="Weekly summary",
            trigger={"weekday": "monday"},
            params={"format": "brief"},
            created_at="2026-01-01T10:00:00",
            last_fired="2026-01-20T09:00:00",
        )

        result = rule.to_dict()

        assert result == {
            "id": "rule-789",
            "user_email": "user@example.com",
            "type": "time",
            "action": "weekly_schedule_summary",
            "enabled": True,
            "schedule": "0 9 * * 1",
            "description": "Weekly summary",
            "trigger": {"weekday": "monday"},
            "params": {"format": "brief"},
            "created_at": "2026-01-01T10:00:00",
            "last_fired": "2026-01-20T09:00:00",
        }

    def test_to_dict_with_none_values(self):
        """Test converting a Rule with None values to dictionary."""
        rule = Rule(
            id="rule-simple",
            user_email="user@example.com",
            type="time",
            action="send_reminder",
        )

        result = rule.to_dict()

        assert result["schedule"] is None
        assert result["description"] is None
        assert result["last_fired"] is None

    def test_from_dict_full(self):
        """Test creating a Rule from a complete dictionary."""
        data = {
            "id": "rule-abc",
            "user_email": "test@example.com",
            "type": "event",
            "action": "send_reminder",
            "enabled": False,
            "schedule": "0 10 * * *",
            "description": "Doctor appointment",
            "trigger": {"days_before": 1},
            "params": {"urgent": True},
            "created_at": "2026-01-10T12:00:00",
            "last_fired": "2026-01-25T10:00:00",
        }

        rule = Rule.from_dict(data)

        assert rule.id == "rule-abc"
        assert rule.user_email == "test@example.com"
        assert rule.type == "event"
        assert rule.action == "send_reminder"
        assert rule.enabled is False
        assert rule.schedule == "0 10 * * *"
        assert rule.description == "Doctor appointment"
        assert rule.trigger == {"days_before": 1}
        assert rule.params == {"urgent": True}
        assert rule.created_at == "2026-01-10T12:00:00"
        assert rule.last_fired == "2026-01-25T10:00:00"

    def test_from_dict_minimal(self):
        """Test creating a Rule from minimal dictionary (missing optional fields)."""
        data = {
            "id": "rule-min",
            "user_email": "user@example.com",
            "type": "time",
            "action": "generate_diary",
        }

        rule = Rule.from_dict(data)

        assert rule.id == "rule-min"
        assert rule.user_email == "user@example.com"
        assert rule.type == "time"
        assert rule.action == "generate_diary"
        assert rule.enabled is True  # default
        assert rule.schedule is None
        assert rule.description is None
        assert rule.trigger == {}  # default
        assert rule.params == {}  # default
        assert rule.last_fired is None
        # created_at gets a default when missing
        assert rule.created_at is not None

    def test_from_dict_enabled_false(self):
        """Test that enabled=False is preserved when loading from dict."""
        data = {
            "id": "rule-disabled",
            "user_email": "user@example.com",
            "type": "time",
            "action": "send_reminder",
            "enabled": False,
        }

        rule = Rule.from_dict(data)

        assert rule.enabled is False

    def test_roundtrip_serialization(self):
        """Test that to_dict -> from_dict preserves all data."""
        original = Rule(
            id="rule-roundtrip",
            user_email="roundtrip@example.com",
            type="event",
            action="send_reminder",
            enabled=False,
            schedule="30 14 * * 5",
            description="Friday meeting prep",
            trigger={"hours_before": 2},
            params={"notes": "Bring laptop"},
            created_at="2026-01-05T08:00:00",
            last_fired="2026-01-24T14:30:00",
        )

        data = original.to_dict()
        restored = Rule.from_dict(data)

        assert restored.id == original.id
        assert restored.user_email == original.user_email
        assert restored.type == original.type
        assert restored.action == original.action
        assert restored.enabled == original.enabled
        assert restored.schedule == original.schedule
        assert restored.description == original.description
        assert restored.trigger == original.trigger
        assert restored.params == original.params
        assert restored.created_at == original.created_at
        assert restored.last_fired == original.last_fired


class TestLoadSaveRules:
    """Tests for load_rules and save_rules functions."""

    def test_load_rules_nonexistent_file(self, test_config):
        """Test loading rules when file doesn't exist returns empty dict."""
        result = load_rules(test_config)
        assert result == {}

    def test_load_rules_empty_file(self, test_config):
        """Test loading rules from empty JSON file returns empty dict."""
        test_config.rules_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.rules_file.write_text("{}")

        result = load_rules(test_config)

        assert result == {}

    def test_load_rules_valid_data(self, test_config):
        """Test loading rules with valid data."""
        rules_data = {
            "user@example.com": [
                {
                    "id": "rule-1",
                    "user_email": "user@example.com",
                    "type": "time",
                    "action": "send_reminder",
                    "enabled": True,
                    "schedule": "0 9 * * *",
                }
            ]
        }
        test_config.rules_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.rules_file.write_text(json.dumps(rules_data))

        result = load_rules(test_config)

        assert result == rules_data

    def test_load_rules_invalid_json(self, test_config):
        """Test loading rules from invalid JSON returns empty dict."""
        test_config.rules_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.rules_file.write_text("not valid json {{{")

        result = load_rules(test_config)

        assert result == {}

    def test_save_rules_creates_directory(self, test_config):
        """Test that save_rules creates parent directories."""
        rules_data = {"user@example.com": []}

        save_rules(rules_data, test_config)

        assert test_config.rules_file.exists()
        assert json.loads(test_config.rules_file.read_text()) == rules_data

    def test_save_rules_overwrites_existing(self, test_config):
        """Test that save_rules overwrites existing file."""
        test_config.rules_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.rules_file.write_text('{"old": "data"}')

        new_data = {"user@example.com": [{"id": "new-rule"}]}
        save_rules(new_data, test_config)

        assert json.loads(test_config.rules_file.read_text()) == new_data

    def test_save_rules_atomic_no_temp_file_on_success(self, test_config):
        """Test that successful save doesn't leave temp files."""
        rules_data = {"user@example.com": []}
        test_config.rules_file.parent.mkdir(parents=True, exist_ok=True)

        save_rules(rules_data, test_config)

        # Check no .tmp files remain
        tmp_files = list(test_config.rules_file.parent.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_save_load_roundtrip(self, test_config):
        """Test that save followed by load returns same data."""
        original_data = {
            "user1@example.com": [
                {"id": "r1", "user_email": "user1@example.com", "type": "time", "action": "a1"},
                {"id": "r2", "user_email": "user1@example.com", "type": "event", "action": "a2"},
            ],
            "user2@example.com": [
                {"id": "r3", "user_email": "user2@example.com", "type": "time", "action": "a3"},
            ],
        }

        save_rules(original_data, test_config)
        loaded_data = load_rules(test_config)

        assert loaded_data == original_data


class TestRuleCRUD:
    """Tests for Rule CRUD operations."""

    def test_get_user_rules_no_file(self, test_config):
        """Test getting rules when no file exists returns empty list."""
        result = get_user_rules("user@example.com", test_config)
        assert result == []

    def test_get_user_rules_no_user_data(self, test_config):
        """Test getting rules for user not in file returns empty list."""
        rules_data = {"other@example.com": [{"id": "r1", "user_email": "other@example.com", "type": "time", "action": "a"}]}
        test_config.rules_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.rules_file.write_text(json.dumps(rules_data))

        result = get_user_rules("user@example.com", test_config)

        assert result == []

    def test_get_user_rules_returns_rule_objects(self, test_config):
        """Test that get_user_rules returns Rule objects, not dicts."""
        rules_data = {
            "user@example.com": [
                {
                    "id": "rule-1",
                    "user_email": "user@example.com",
                    "type": "time",
                    "action": "send_reminder",
                    "schedule": "0 9 * * *",
                },
                {
                    "id": "rule-2",
                    "user_email": "user@example.com",
                    "type": "event",
                    "action": "weekly_schedule_summary",
                    "description": "meeting",
                    "trigger": {"days_before": 1},
                },
            ]
        }
        test_config.rules_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.rules_file.write_text(json.dumps(rules_data))

        result = get_user_rules("user@example.com", test_config)

        assert len(result) == 2
        assert all(isinstance(r, Rule) for r in result)
        assert result[0].id == "rule-1"
        assert result[0].type == "time"
        assert result[1].id == "rule-2"
        assert result[1].type == "event"

    def test_add_rule_to_empty_file(self, test_config):
        """Test adding a rule when no file exists."""
        rule = Rule.create_time_rule(
            user_email="user@example.com",
            schedule="0 8 * * *",
            action="generate_diary",
        )

        add_rule(rule, test_config)

        data = load_rules(test_config)
        assert "user@example.com" in data
        assert len(data["user@example.com"]) == 1
        assert data["user@example.com"][0]["action"] == "generate_diary"

    def test_add_rule_to_existing_user(self, test_config):
        """Test adding a rule to an existing user's rules."""
        existing_data = {
            "user@example.com": [
                {"id": "existing", "user_email": "user@example.com", "type": "time", "action": "action1"}
            ]
        }
        test_config.rules_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.rules_file.write_text(json.dumps(existing_data))

        rule = Rule.create_time_rule(
            user_email="user@example.com",
            schedule="0 10 * * *",
            action="action2",
        )
        add_rule(rule, test_config)

        data = load_rules(test_config)
        assert len(data["user@example.com"]) == 2
        assert data["user@example.com"][0]["id"] == "existing"
        assert data["user@example.com"][1]["action"] == "action2"

    def test_add_rule_new_user(self, test_config):
        """Test adding a rule for a new user to existing file."""
        existing_data = {
            "user1@example.com": [
                {"id": "r1", "user_email": "user1@example.com", "type": "time", "action": "a"}
            ]
        }
        test_config.rules_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.rules_file.write_text(json.dumps(existing_data))

        rule = Rule.create_event_rule(
            user_email="user2@example.com",
            description="meeting",
            trigger={"hours_before": 1},
            action="send_reminder",
        )
        add_rule(rule, test_config)

        data = load_rules(test_config)
        assert "user1@example.com" in data
        assert "user2@example.com" in data
        assert len(data["user2@example.com"]) == 1

    def test_delete_rule_success(self, test_config):
        """Test successfully deleting a rule."""
        rules_data = {
            "user@example.com": [
                {"id": "rule-1", "user_email": "user@example.com", "type": "time", "action": "a1"},
                {"id": "rule-2", "user_email": "user@example.com", "type": "time", "action": "a2"},
            ]
        }
        test_config.rules_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.rules_file.write_text(json.dumps(rules_data))

        result = delete_rule("user@example.com", "rule-1", test_config)

        assert result is True
        data = load_rules(test_config)
        assert len(data["user@example.com"]) == 1
        assert data["user@example.com"][0]["id"] == "rule-2"

    def test_delete_rule_not_found(self, test_config):
        """Test deleting a rule that doesn't exist."""
        rules_data = {
            "user@example.com": [
                {"id": "rule-1", "user_email": "user@example.com", "type": "time", "action": "a1"},
            ]
        }
        test_config.rules_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.rules_file.write_text(json.dumps(rules_data))

        result = delete_rule("user@example.com", "nonexistent", test_config)

        assert result is False
        data = load_rules(test_config)
        assert len(data["user@example.com"]) == 1

    def test_delete_rule_user_not_found(self, test_config):
        """Test deleting a rule for a user that doesn't exist."""
        rules_data = {
            "other@example.com": [
                {"id": "rule-1", "user_email": "other@example.com", "type": "time", "action": "a1"},
            ]
        }
        test_config.rules_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.rules_file.write_text(json.dumps(rules_data))

        result = delete_rule("user@example.com", "rule-1", test_config)

        assert result is False

    def test_delete_rule_no_file(self, test_config):
        """Test deleting a rule when no file exists."""
        result = delete_rule("user@example.com", "rule-1", test_config)
        assert result is False


class TestUpdateLastFired:
    """Tests for update_rule_last_fired function."""

    def test_update_last_fired_success(self, test_config):
        """Test updating last_fired timestamp."""
        rules_data = {
            "user@example.com": [
                {"id": "rule-1", "user_email": "user@example.com", "type": "time", "action": "a1", "last_fired": None},
            ]
        }
        test_config.rules_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.rules_file.write_text(json.dumps(rules_data))

        from zoneinfo import ZoneInfo

        local_tz = ZoneInfo(test_config.timezone)
        before = datetime.now(local_tz)
        update_rule_last_fired("user@example.com", "rule-1", test_config)
        after = datetime.now(local_tz)

        data = load_rules(test_config)
        last_fired = data["user@example.com"][0]["last_fired"]
        assert last_fired is not None
        # Verify timestamp is reasonable (now stores timezone-aware datetime)
        fired_dt = datetime.fromisoformat(last_fired)
        assert before <= fired_dt <= after

    def test_update_last_fired_rule_not_found(self, test_config):
        """Test updating last_fired for nonexistent rule does nothing."""
        rules_data = {
            "user@example.com": [
                {"id": "rule-1", "user_email": "user@example.com", "type": "time", "action": "a1", "last_fired": None},
            ]
        }
        test_config.rules_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.rules_file.write_text(json.dumps(rules_data))

        update_rule_last_fired("user@example.com", "nonexistent", test_config)

        data = load_rules(test_config)
        assert data["user@example.com"][0]["last_fired"] is None

    def test_update_last_fired_user_not_found(self, test_config):
        """Test updating last_fired for nonexistent user does nothing."""
        rules_data = {
            "other@example.com": [
                {"id": "rule-1", "user_email": "other@example.com", "type": "time", "action": "a1"},
            ]
        }
        test_config.rules_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.rules_file.write_text(json.dumps(rules_data))

        # Should not raise, just do nothing
        update_rule_last_fired("user@example.com", "rule-1", test_config)

        data = load_rules(test_config)
        assert "other@example.com" in data

    def test_update_last_fired_no_file(self, test_config):
        """Test updating last_fired when no file exists does nothing."""
        # Should not raise
        update_rule_last_fired("user@example.com", "rule-1", test_config)

    def test_update_last_fired_multiple_rules(self, test_config):
        """Test updating last_fired only affects the correct rule."""
        rules_data = {
            "user@example.com": [
                {"id": "rule-1", "user_email": "user@example.com", "type": "time", "action": "a1", "last_fired": None},
                {"id": "rule-2", "user_email": "user@example.com", "type": "time", "action": "a2", "last_fired": None},
            ]
        }
        test_config.rules_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.rules_file.write_text(json.dumps(rules_data))

        update_rule_last_fired("user@example.com", "rule-1", test_config)

        data = load_rules(test_config)
        assert data["user@example.com"][0]["last_fired"] is not None
        assert data["user@example.com"][1]["last_fired"] is None

    def test_update_last_fired_twice_with_tz_aware_comparison(self, test_config):
        """Test firing a rule twice validates tz-aware last_fired handling.

        This test ensures that:
        1. last_fired is stored with timezone info
        2. Subsequent comparisons with tz-aware now() work correctly
        3. The second fire can be compared against the first without TypeError
        """
        from zoneinfo import ZoneInfo

        rules_data = {
            "user@example.com": [
                {
                    "id": "rule-tz",
                    "user_email": "user@example.com",
                    "type": "time",
                    "action": "test_action",
                    "last_fired": None,
                    "schedule": "0 8 * * *",
                    "enabled": True,
                },
            ]
        }
        test_config.rules_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.rules_file.write_text(json.dumps(rules_data))

        local_tz = ZoneInfo(test_config.timezone)

        # First fire
        update_rule_last_fired("user@example.com", "rule-tz", test_config)

        data = load_rules(test_config)
        first_fired = data["user@example.com"][0]["last_fired"]
        assert first_fired is not None

        # Parse and verify it has timezone info
        first_dt = datetime.fromisoformat(first_fired)
        assert first_dt.tzinfo is not None, "last_fired should be timezone-aware"

        # Simulate scheduler comparison (this would fail before the fix)
        now = datetime.now(local_tz)
        time_since_first = (now - first_dt).total_seconds()
        assert time_since_first >= 0, "Should be able to compare tz-aware datetimes"

        # Second fire
        import time
        time.sleep(0.01)  # Small delay to ensure different timestamp
        update_rule_last_fired("user@example.com", "rule-tz", test_config)

        data = load_rules(test_config)
        second_fired = data["user@example.com"][0]["last_fired"]
        second_dt = datetime.fromisoformat(second_fired)

        # Verify second fire is after first (tz-aware comparison)
        assert second_dt > first_dt, "Second fire should be after first"

        # Verify scheduler-style comparison works
        time_since_second = (now - second_dt).total_seconds()
        # This comparison working without TypeError confirms the fix
        assert isinstance(time_since_second, float)


class TestTriggeredEvents:
    """Tests for triggered events tracking."""

    def test_load_triggered_no_file(self, test_config):
        """Test loading triggered events when no file exists."""
        result = load_triggered(test_config)
        assert result == {}

    def test_load_triggered_empty_file(self, test_config):
        """Test loading triggered events from empty JSON file."""
        test_config.triggered_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.triggered_file.write_text("{}")

        result = load_triggered(test_config)

        assert result == {}

    def test_load_triggered_valid_data(self, test_config):
        """Test loading triggered events with valid data."""
        triggered_data = {
            "rule1:event1": "2026-01-25T10:00:00",
            "rule2:event2": "2026-01-26T11:00:00",
        }
        test_config.triggered_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.triggered_file.write_text(json.dumps(triggered_data))

        result = load_triggered(test_config)

        assert result == triggered_data

    def test_load_triggered_invalid_json(self, test_config):
        """Test loading triggered events from invalid JSON returns empty dict."""
        test_config.triggered_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.triggered_file.write_text("invalid json")

        result = load_triggered(test_config)

        assert result == {}

    def test_save_triggered_creates_directory(self, test_config):
        """Test that save_triggered creates parent directories."""
        triggered_data = {"rule:event": "2026-01-27T12:00:00"}

        save_triggered(triggered_data, test_config)

        assert test_config.triggered_file.exists()
        assert json.loads(test_config.triggered_file.read_text()) == triggered_data

    def test_save_triggered_atomic_no_temp_files(self, test_config):
        """Test that save_triggered doesn't leave temp files on success."""
        triggered_data = {"rule:event": "2026-01-27T12:00:00"}
        test_config.triggered_file.parent.mkdir(parents=True, exist_ok=True)

        save_triggered(triggered_data, test_config)

        tmp_files = list(test_config.triggered_file.parent.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_mark_event_triggered(self, test_config):
        """Test marking an event as triggered."""
        from zoneinfo import ZoneInfo

        local_tz = ZoneInfo(test_config.timezone)
        before = datetime.now(local_tz)
        mark_event_triggered("rule-123", "event-456", test_config)
        after = datetime.now(local_tz)

        triggered = load_triggered(test_config)
        assert "rule-123:event-456" in triggered
        # Verify timestamp is reasonable (timezone-aware comparison)
        timestamp = datetime.fromisoformat(triggered["rule-123:event-456"])
        assert before <= timestamp <= after

    def test_mark_event_triggered_adds_to_existing(self, test_config):
        """Test marking an event adds to existing triggered events."""
        existing = {"rule-1:event-a": "2026-01-25T10:00:00"}
        test_config.triggered_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.triggered_file.write_text(json.dumps(existing))

        mark_event_triggered("rule-2", "event-b", test_config)

        triggered = load_triggered(test_config)
        assert "rule-1:event-a" in triggered
        assert "rule-2:event-b" in triggered

    def test_mark_event_triggered_updates_existing(self, test_config):
        """Test marking an already-triggered event updates timestamp."""
        existing = {"rule-1:event-a": "2026-01-20T10:00:00"}
        test_config.triggered_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.triggered_file.write_text(json.dumps(existing))

        mark_event_triggered("rule-1", "event-a", test_config)

        triggered = load_triggered(test_config)
        # Timestamp should be updated
        assert triggered["rule-1:event-a"] != "2026-01-20T10:00:00"

    def test_is_event_triggered_true(self, test_config):
        """Test checking if an event is triggered (true case)."""
        triggered_data = {"rule-1:event-a": "2026-01-25T10:00:00"}
        test_config.triggered_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.triggered_file.write_text(json.dumps(triggered_data))

        result = is_event_triggered("rule-1", "event-a", test_config)

        assert result is True

    def test_is_event_triggered_false(self, test_config):
        """Test checking if an event is triggered (false case)."""
        triggered_data = {"rule-1:event-a": "2026-01-25T10:00:00"}
        test_config.triggered_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.triggered_file.write_text(json.dumps(triggered_data))

        result = is_event_triggered("rule-1", "event-b", test_config)

        assert result is False

    def test_is_event_triggered_no_file(self, test_config):
        """Test checking if an event is triggered when no file exists."""
        result = is_event_triggered("rule-1", "event-a", test_config)
        assert result is False

    def test_mark_and_check_event_triggered(self, test_config):
        """Test marking and then checking an event is triggered."""
        # Initially not triggered
        assert is_event_triggered("rule-x", "event-y", test_config) is False

        # Mark as triggered
        mark_event_triggered("rule-x", "event-y", test_config)

        # Now should be triggered
        assert is_event_triggered("rule-x", "event-y", test_config) is True


class TestAtomicFileOperations:
    """Tests for atomic file operation guarantees."""

    def test_save_rules_atomic_on_error(self, test_config):
        """Test that save_rules cleans up temp file on error."""
        test_config.rules_file.parent.mkdir(parents=True, exist_ok=True)

        # Create an object that can't be JSON serialized
        class NotSerializable:
            pass

        bad_data = {"user": [NotSerializable()]}

        with pytest.raises(TypeError):
            save_rules(bad_data, test_config)

        # No temp files should remain
        tmp_files = list(test_config.rules_file.parent.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_save_triggered_atomic_on_error(self, test_config):
        """Test that save_triggered cleans up temp file on error."""
        test_config.triggered_file.parent.mkdir(parents=True, exist_ok=True)

        class NotSerializable:
            pass

        bad_data = {"key": NotSerializable()}

        with pytest.raises(TypeError):
            save_triggered(bad_data, test_config)

        # No temp files should remain
        tmp_files = list(test_config.triggered_file.parent.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_concurrent_operations_file_integrity(self, test_config):
        """Test that file remains valid JSON after multiple operations."""
        # Perform multiple operations
        rule1 = Rule.create_time_rule(
            user_email="user1@example.com",
            schedule="0 9 * * *",
            action="action1",
        )
        rule2 = Rule.create_event_rule(
            user_email="user2@example.com",
            description="event",
            trigger={"days_before": 1},
            action="action2",
        )

        add_rule(rule1, test_config)
        add_rule(rule2, test_config)
        delete_rule("user1@example.com", rule1.id, test_config)

        # File should be valid JSON
        data = json.loads(test_config.rules_file.read_text())
        assert isinstance(data, dict)
        assert "user2@example.com" in data


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_rule_with_empty_strings(self):
        """Test creating a Rule with empty strings."""
        rule = Rule(
            id="",
            user_email="",
            type="",
            action="",
            description="",
        )
        assert rule.id == ""
        assert rule.user_email == ""

    def test_rule_with_special_characters(self):
        """Test Rule with special characters in fields."""
        rule = Rule(
            id="rule-123",
            user_email="user+test@example.com",
            type="event",
            action="send_reminder",
            description="Meeting @ 10am with $100 budget & \"special\" notes",
        )

        data = rule.to_dict()
        restored = Rule.from_dict(data)

        assert restored.description == "Meeting @ 10am with $100 budget & \"special\" notes"

    def test_rule_with_unicode(self):
        """Test Rule with unicode characters."""
        rule = Rule(
            id="rule-unicode",
            user_email="user@example.com",
            type="event",
            action="send_reminder",
            description="Rendez-vous cafe with Pierre",
            params={"message": "N'oublie pas!"},
        )

        data = rule.to_dict()
        restored = Rule.from_dict(data)

        assert restored.description == "Rendez-vous cafe with Pierre"
        assert restored.params["message"] == "N'oublie pas!"

    def test_large_params_dict(self):
        """Test Rule with large params dictionary."""
        large_params = {f"key_{i}": f"value_{i}" for i in range(100)}
        rule = Rule(
            id="rule-large",
            user_email="user@example.com",
            type="time",
            action="test",
            params=large_params,
        )

        data = rule.to_dict()
        restored = Rule.from_dict(data)

        assert len(restored.params) == 100

    def test_nested_trigger_dict(self):
        """Test Rule with nested trigger dictionary."""
        nested_trigger = {
            "conditions": {
                "days_before": 2,
                "time": {"hour": 9, "minute": 0},
            },
            "options": ["notify", "email"],
        }
        rule = Rule.create_event_rule(
            user_email="user@example.com",
            description="event",
            trigger=nested_trigger,
            action="send_reminder",
        )

        data = rule.to_dict()
        restored = Rule.from_dict(data)

        assert restored.trigger == nested_trigger

class TestCleanupOldTriggered:
    """Tests for cleanup_old_triggered function."""

    def test_cleanup_empty_file(self, test_config):
        """Test cleanup when no triggered file exists."""
        removed = cleanup_old_triggered(test_config)
        assert removed == 0

    def test_cleanup_no_old_entries(self, test_config):
        """Test cleanup when all entries are recent."""
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        local_tz = ZoneInfo(test_config.timezone)
        now = datetime.now(local_tz)

        # Create recent entries (within 90 days)
        triggered_data = {
            "rule-1:event-a": now.isoformat(),
            "rule-2:event-b": (now - timedelta(days=30)).isoformat(),
            "rule-3:event-c": (now - timedelta(days=89)).isoformat(),
        }
        test_config.triggered_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.triggered_file.write_text(json.dumps(triggered_data))

        removed = cleanup_old_triggered(test_config)
        assert removed == 0

        # All entries should still be there
        result = load_triggered(test_config)
        assert len(result) == 3

    def test_cleanup_old_entries(self, test_config):
        """Test cleanup removes entries older than max_age_days."""
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        local_tz = ZoneInfo(test_config.timezone)
        now = datetime.now(local_tz)

        # Mix of old and new entries
        triggered_data = {
            "rule-1:event-a": now.isoformat(),  # Recent
            "rule-2:event-b": (now - timedelta(days=91)).isoformat(),  # Old
            "rule-3:event-c": (now - timedelta(days=180)).isoformat(),  # Very old
            "rule-4:event-d": (now - timedelta(days=30)).isoformat(),  # Recent
        }
        test_config.triggered_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.triggered_file.write_text(json.dumps(triggered_data))

        removed = cleanup_old_triggered(test_config, max_age_days=90)
        assert removed == 2

        # Only recent entries should remain
        result = load_triggered(test_config)
        assert len(result) == 2
        assert "rule-1:event-a" in result
        assert "rule-4:event-d" in result
        assert "rule-2:event-b" not in result
        assert "rule-3:event-c" not in result

    def test_cleanup_invalid_timestamps(self, test_config):
        """Test cleanup removes entries with invalid timestamps."""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        local_tz = ZoneInfo(test_config.timezone)
        now = datetime.now(local_tz)

        triggered_data = {
            "rule-1:event-a": now.isoformat(),  # Valid
            "rule-2:event-b": "invalid-timestamp",  # Invalid
            "rule-3:event-c": "",  # Empty
            "rule-4:event-d": "2026-13-45T99:99:99",  # Invalid date
        }
        test_config.triggered_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.triggered_file.write_text(json.dumps(triggered_data))

        removed = cleanup_old_triggered(test_config)
        assert removed == 3  # All invalid entries removed

        result = load_triggered(test_config)
        assert len(result) == 1
        assert "rule-1:event-a" in result

    def test_cleanup_custom_max_age(self, test_config):
        """Test cleanup with custom max_age_days."""
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        local_tz = ZoneInfo(test_config.timezone)
        now = datetime.now(local_tz)

        triggered_data = {
            "rule-1:event-a": (now - timedelta(days=5)).isoformat(),
            "rule-2:event-b": (now - timedelta(days=15)).isoformat(),
        }
        test_config.triggered_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.triggered_file.write_text(json.dumps(triggered_data))

        # With 7 day max age, only rule-1 should remain
        removed = cleanup_old_triggered(test_config, max_age_days=7)
        assert removed == 1

        result = load_triggered(test_config)
        assert len(result) == 1
        assert "rule-1:event-a" in result

    def test_cleanup_naive_timestamps(self, test_config):
        """Test cleanup handles naive (timezone-unaware) timestamps."""
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        local_tz = ZoneInfo(test_config.timezone)
        now = datetime.now(local_tz)

        # Mix of aware and naive timestamps
        triggered_data = {
            "rule-1:event-a": now.isoformat(),  # Timezone-aware
            "rule-2:event-b": datetime.now().isoformat(),  # Naive (no tz)
            "rule-3:event-c": (datetime.now() - timedelta(days=91)).isoformat(),  # Naive, old
        }
        test_config.triggered_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.triggered_file.write_text(json.dumps(triggered_data))

        removed = cleanup_old_triggered(test_config, max_age_days=90)
        assert removed == 1  # Only the old naive one

        result = load_triggered(test_config)
        assert len(result) == 2

