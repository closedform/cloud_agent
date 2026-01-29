"""Stress tests for src/agents/tools/automation_tools.py

Tests edge cases and potential bugs:
1. Invalid cron syntax in rules
2. Event rules with no matching events
3. Reminder datetime edge cases
4. Rule deletion race conditions
"""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

import pytest

from src.reminders import _load_reminders, _reminders_lock, schedule_reminder
from src.rules import load_rules, _rules_lock, add_rule, delete_rule, Rule
from src.models import Reminder


class TestInvalidCronSyntax:
    """Tests for invalid cron syntax in time-based rules."""

    def test_create_rule_with_invalid_cron_basic(self, test_config):
        """Create rule with obviously invalid cron syntax - should fail at creation.

        FIX: The system now validates cron expressions at creation time.
        """
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_rule

            # Invalid cron syntax - should fail at creation
            result = create_rule(
                rule_type="time",
                action="weekly_schedule_summary",
                schedule="not a cron expression",
            )

            # Fixed: Now validates cron at creation time
            assert result["status"] == "error"
            assert "Invalid cron" in result["message"] or "cron" in result["message"].lower()

    def test_create_rule_with_invalid_cron_wrong_field_count(self, test_config):
        """Cron with wrong number of fields - should fail at creation."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_rule

            # Too few fields (only 3 instead of 5)
            result = create_rule(
                rule_type="time",
                action="send_reminder",
                schedule="0 8 *",  # Missing day-of-month and day-of-week
            )

            # Fixed: Now validates cron at creation time
            assert result["status"] == "error"

    def test_create_rule_with_invalid_cron_out_of_range(self, test_config):
        """Cron with out-of-range values - should fail at creation."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_rule

            # Hour 25 is invalid (0-23 valid)
            result = create_rule(
                rule_type="time",
                action="send_reminder",
                schedule="0 25 * * *",  # Invalid hour
            )

            # Fixed: Now validates cron at creation time
            assert result["status"] == "error"

    def test_create_rule_with_empty_cron(self, test_config):
        """Empty string cron schedule - properly rejected."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_rule

            # Empty schedule - this is handled correctly
            result = create_rule(
                rule_type="time",
                action="send_reminder",
                schedule="",
            )

            # Empty string is falsy, so this correctly fails
            assert result["status"] == "error"
            assert "Schedule required" in result["message"]

    def test_rule_creation_validates_cron_in_model(self, test_config, mock_services):
        """Rule.create_time_rule validates cron and raises ValueError for invalid cron."""
        from croniter import croniter

        # Attempt to create rule with invalid cron directly - should raise
        with pytest.raises(ValueError) as exc_info:
            Rule.create_time_rule(
                user_email="test@example.com",
                schedule="invalid cron here",
                action="send_reminder",
            )

        # Verify the error message mentions the invalid schedule
        assert "Invalid cron" in str(exc_info.value)

        # Verify no rule was created
        rules = load_rules(test_config)
        assert len(rules.get("test@example.com", [])) == 0

        # Also verify croniter raises on invalid cron
        with pytest.raises(Exception):  # croniter raises CroniterBadCronError
            croniter("invalid cron here", datetime.now())


class TestEventRulesNoMatchingEvents:
    """Tests for event rules when no events match."""

    def test_event_rule_with_no_calendar_events(self, test_config):
        """Event rule created when calendar is empty."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_rule, get_rules

            # Create event rule
            result = create_rule(
                rule_type="event",
                action="send_reminder",
                description="doctor appointment",
                days_before=1,
            )

            assert result["status"] == "success"

            # Verify rule exists
            rules = get_rules()
            assert rules["count"] == 1
            assert rules["rules"][0]["type"] == "event"
            assert rules["rules"][0]["description"] == "doctor appointment"

    def test_event_rule_with_impossible_match(self, test_config):
        """Event rule with description that will never match anything."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_rule

            # Very specific description unlikely to match
            result = create_rule(
                rule_type="event",
                action="send_reminder",
                description="xyz123 impossible event 456abc",
                days_before=7,
            )

            # Creation should succeed (matching happens at runtime)
            assert result["status"] == "success"

    def test_event_rule_negative_days_before(self, test_config):
        """Event rule with negative days_before - should be rejected."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_rule

            # Negative days_before - reminder AFTER event?
            result = create_rule(
                rule_type="event",
                action="send_reminder",
                description="meeting",
                days_before=-1,  # 1 day AFTER event?
            )

            # Fixed: Now rejects negative days_before
            assert result["status"] == "error"
            assert "days_before must be >= 0" in result["message"]

    def test_event_rule_very_large_days_before(self, test_config):
        """Event rule with unreasonably large days_before."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_rule

            # 1000 days before - roughly 3 years
            result = create_rule(
                rule_type="event",
                action="send_reminder",
                description="wedding",
                days_before=1000,
            )

            # Allowed but unlikely to ever match (events usually <30 days out)
            assert result["status"] == "success"


class TestReminderDatetimeEdgeCases:
    """Tests for reminder datetime edge cases."""

    def test_reminder_past_datetime(self, test_config):
        """Reminder with datetime in the past - should fire immediately."""
        past_time = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")

        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config, patch(
            "src.reminders.send_reminder_email"
        ) as mock_send:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_reminder

            result = create_reminder(
                message="Past reminder",
                reminder_time=past_time,
            )

            # Creation should succeed
            assert result["status"] == "success"

            # Reminder in past should trigger immediate send
            # Wait a bit for the immediate send to happen
            time.sleep(0.1)
            mock_send.assert_called()

    def test_reminder_very_far_future(self, test_config):
        """Reminder with datetime far in the future."""
        far_future = (datetime.now() + timedelta(days=365 * 10)).strftime("%Y-%m-%dT%H:%M:%S")

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
                message="Far future reminder",
                reminder_time=far_future,
            )

            # Should succeed but timer will be very long
            assert result["status"] == "success"

    def test_reminder_invalid_datetime_format(self, test_config):
        """Reminder with completely invalid datetime format - should be rejected."""
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
                message="Invalid datetime reminder",
                reminder_time="not-a-date",
            )

            # Fixed: Now validates datetime at creation time
            assert result["status"] == "error"
            assert "Invalid datetime" in result["message"]

    def test_reminder_malformed_iso_datetime(self, test_config):
        """Reminder with malformed ISO datetime - should be rejected."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_reminder

            # Month 13 is invalid
            result = create_reminder(
                message="Bad month reminder",
                reminder_time="2026-13-01T10:00:00",
            )

            # Fixed: Now validates datetime at creation time
            assert result["status"] == "error"
            assert "Invalid datetime" in result["message"]

    def test_reminder_timezone_aware_datetime(self, test_config):
        """Reminder with timezone-aware datetime string."""
        tz_time = datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S%z")

        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import create_reminder

            # Timezone-aware datetime
            future = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1))
            tz_time = future.isoformat()

            result = create_reminder(
                message="Timezone aware reminder",
                reminder_time=tz_time,
            )

            assert result["status"] == "success"

    def test_reminder_scheduling_with_different_timezones(self, test_config):
        """Test reminder scheduling handles timezone conversions correctly."""
        # Create a reminder for a specific time in a different timezone
        pacific = ZoneInfo("America/Los_Angeles")
        eastern = ZoneInfo("America/New_York")

        # Future time in Pacific
        pacific_time = datetime.now(pacific) + timedelta(hours=2)
        pacific_iso = pacific_time.isoformat()

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
                message="Cross timezone reminder",
                reminder_time=pacific_iso,
            )

            assert result["status"] == "success"


class TestRuleDeletionRaceConditions:
    """Tests for race conditions during rule deletion."""

    def test_concurrent_rule_creation(self, test_config):
        """Multiple threads creating rules simultaneously."""
        results = []
        errors = []

        def create_rule_thread(idx):
            try:
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
                        schedule=f"0 {idx % 24} * * *",
                    )
                    results.append(result)
            except Exception as e:
                errors.append(str(e))

        # Create 10 rules concurrently
        threads = [threading.Thread(target=create_rule_thread, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should succeed due to locking
        assert len(errors) == 0
        assert all(r["status"] == "success" for r in results)

        # Verify all rules were created
        rules_data = load_rules(test_config)
        assert len(rules_data.get("test@example.com", [])) == 10

    def test_concurrent_rule_deletion(self, test_config):
        """Multiple threads deleting the same rule - only one should succeed."""
        # First create a rule
        rule = Rule.create_time_rule(
            user_email="test@example.com",
            schedule="0 8 * * *",
            action="send_reminder",
        )
        add_rule(rule, test_config)
        rule_id = rule.id

        # Verify rule exists
        rules = load_rules(test_config)
        assert len(rules.get("test@example.com", [])) == 1

        results = []

        def delete_rule_thread():
            with patch(
                "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
            ), patch(
                "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
            ), patch(
                "src.agents.tools.automation_tools.get_config"
            ) as mock_get_config:
                mock_get_config.return_value = test_config

                from src.agents.tools.automation_tools import delete_user_rule

                result = delete_user_rule(rule_id=rule_id)
                results.append(result)

        # Try to delete the same rule from 5 threads
        threads = [threading.Thread(target=delete_rule_thread) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Exactly one should succeed, rest should be error (not found)
        success_count = sum(1 for r in results if r["status"] == "success")
        error_count = sum(1 for r in results if r["status"] == "error")

        assert success_count == 1
        assert error_count == 4

        # Verify rule is gone
        rules = load_rules(test_config)
        assert len(rules.get("test@example.com", [])) == 0

    def test_delete_during_create(self, test_config):
        """Delete a rule while another thread is creating rules."""
        created_ids = []
        deletion_results = []

        def create_rules():
            for i in range(5):
                rule = Rule.create_time_rule(
                    user_email="test@example.com",
                    schedule=f"0 {i} * * *",
                    action="send_reminder",
                )
                add_rule(rule, test_config)
                created_ids.append(rule.id)
                time.sleep(0.01)  # Small delay between creates

        def delete_rules():
            time.sleep(0.02)  # Let some rules be created first
            while len(created_ids) < 2:
                time.sleep(0.01)

            # Try to delete a rule that was just created
            rule_id = created_ids[0]
            result = delete_rule("test@example.com", rule_id, test_config)
            deletion_results.append(result)

        create_thread = threading.Thread(target=create_rules)
        delete_thread = threading.Thread(target=delete_rules)

        create_thread.start()
        delete_thread.start()

        create_thread.join()
        delete_thread.join()

        # All creates should have succeeded
        assert len(created_ids) == 5

        # Deletion should have succeeded (race condition handled by lock)
        assert len(deletion_results) == 1
        assert deletion_results[0] is True

        # Final count should be 4 rules
        rules = load_rules(test_config)
        assert len(rules.get("test@example.com", [])) == 4

    def test_concurrent_delete_different_rules(self, test_config):
        """Multiple threads deleting different rules simultaneously."""
        # Create 5 rules
        rule_ids = []
        for i in range(5):
            rule = Rule.create_time_rule(
                user_email="test@example.com",
                schedule=f"0 {i} * * *",
                action="send_reminder",
            )
            add_rule(rule, test_config)
            rule_ids.append(rule.id)
            time.sleep(0.002)  # Ensure unique IDs

        # Verify all rules exist
        rules = load_rules(test_config)
        assert len(rules.get("test@example.com", [])) == 5

        results = []

        def delete_rule_thread(rid):
            with patch(
                "src.agents.tools.automation_tools.get_user_email", return_value="test@example.com"
            ), patch(
                "src.agents.tools.automation_tools.get_reply_to", return_value="test@example.com"
            ), patch(
                "src.agents.tools.automation_tools.get_config"
            ) as mock_get_config:
                mock_get_config.return_value = test_config

                from src.agents.tools.automation_tools import delete_user_rule

                result = delete_user_rule(rule_id=rid)
                results.append((rid, result))

        # Delete all 5 rules concurrently
        threads = [threading.Thread(target=delete_rule_thread, args=(rid,)) for rid in rule_ids]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All 5 deletions should succeed
        assert len(results) == 5
        assert all(r[1]["status"] == "success" for r in results)

        # Verify all rules are gone
        rules = load_rules(test_config)
        assert len(rules.get("test@example.com", [])) == 0


class TestReminderEdgeCases:
    """Additional reminder edge cases."""

    def test_reminder_empty_message(self, test_config):
        """Reminder with empty message - should be rejected."""
        future_time = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")

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
                message="",  # Empty message
                reminder_time=future_time,
            )

            # Fixed: Now rejects empty messages
            assert result["status"] == "error"
            assert "cannot be empty" in result["message"]

    def test_reminder_very_long_message(self, test_config):
        """Reminder with extremely long message."""
        future_time = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        long_message = "x" * 10000  # 10KB message

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
                message=long_message,
                reminder_time=future_time,
            )

            # Accepts very long messages without truncation
            assert result["status"] == "success"
            assert len(result["reminder"]["message"]) == 10000

    def test_reminder_special_characters(self, test_config):
        """Reminder with special characters and unicode."""
        future_time = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        special_message = "Reminder: \n\t<script>alert('xss')</script> & \u2764 \U0001F600"

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
                message=special_message,
                reminder_time=future_time,
            )

            # Should handle special chars (no sanitization in tool)
            assert result["status"] == "success"
            assert result["reminder"]["message"] == special_message

    def test_concurrent_reminder_creation(self, test_config):
        """Multiple threads creating reminders simultaneously."""
        results = []

        def create_reminder_thread(idx):
            future_time = (datetime.now() + timedelta(hours=idx + 1)).strftime("%Y-%m-%dT%H:%M:%S")

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
                    message=f"Reminder {idx}",
                    reminder_time=future_time,
                )
                results.append(result)

        threads = [threading.Thread(target=create_reminder_thread, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should succeed
        assert all(r["status"] == "success" for r in results)

        # Verify all reminders were persisted
        with _reminders_lock:
            reminders = _load_reminders(test_config)
        assert len(reminders) == 10


class TestRuleEdgeCases:
    """Additional rule edge cases."""

    def test_rule_empty_action(self, test_config):
        """Rule with empty action string - should be rejected."""
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
                action="",  # Empty action
                schedule="0 8 * * *",
            )

            # Fixed: Now rejects empty actions
            assert result["status"] == "error"
            assert "Action cannot be empty" in result["message"]

    def test_rule_unknown_action(self, test_config):
        """Rule with unknown action type - should be rejected."""
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
                action="nonexistent_action",  # Unknown action
                schedule="0 8 * * *",
            )

            # Fixed: Now rejects unknown actions
            assert result["status"] == "error"
            assert "Unknown action" in result["message"]

    def test_rule_very_long_description(self, test_config):
        """Event rule with extremely long description."""
        long_description = "appointment " * 1000  # ~11KB

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
                description=long_description,
                days_before=1,
            )

            # Accepts very long descriptions (may cause issues with AI matching)
            assert result["status"] == "success"

    def test_delete_nonexistent_user_rules(self, test_config):
        """Delete rule for user that has no rules at all."""
        with patch(
            "src.agents.tools.automation_tools.get_user_email", return_value="nobody@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_reply_to", return_value="nobody@example.com"
        ), patch(
            "src.agents.tools.automation_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.automation_tools import delete_user_rule

            result = delete_user_rule(rule_id="any-id")

            # Fixed: Consistent error status (was "not_found", now "error")
            assert result["status"] == "error"
            assert "not found" in result["message"]

    def test_get_rules_for_user_with_corrupted_rule(self, test_config):
        """Get rules when rules file has corrupted data - gracefully skips corrupted rules."""
        # Write corrupted rule data mixed with valid rule
        rules_data = {
            "test@example.com": [
                {"id": "good-rule", "user_email": "test@example.com", "type": "time",
                 "action": "send_reminder", "schedule": "0 8 * * *"},
                {"broken": "data"},  # Missing required fields - will be skipped
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

            # Graceful degradation: corrupted rules are skipped, valid rules are returned
            result = get_rules()
            assert result["status"] == "success"
            # Should return only the valid rule, corrupted one is skipped
            assert len(result["rules"]) == 1
            assert result["rules"][0]["id"] == "good-rule"
