"""Stress tests for src/rules.py - Testing edge cases and potential bugs.

Tests for:
1. Invalid cron expressions
2. Overlapping event rules
3. Rules with missing fields
4. Very long rule descriptions
"""

import json
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

import pytest
from croniter import croniter

from src.rules import (
    Rule,
    add_rule,
    delete_rule,
    get_user_rules,
    load_rules,
    save_rules,
    update_rule_last_fired,
)


class TestInvalidCronExpressions:
    """Test handling of invalid cron expressions.

    These tests verify that invalid cron expressions are rejected at rule
    creation time, rather than failing later when the scheduler tries to use them.
    """

    def test_invalid_cron_format_too_few_fields(self, test_config):
        """Test cron expression with too few fields (should have 5)."""
        # Invalid cron expressions should be rejected at creation time
        with pytest.raises(ValueError, match="Invalid cron schedule"):
            Rule.create_time_rule(
                user_email="user@example.com",
                schedule="0 9 * *",  # Only 4 fields, needs 5
                action="send_reminder",
            )

    def test_invalid_cron_format_too_many_fields(self, test_config):
        """Test cron expression with too many fields."""
        rule = Rule.create_time_rule(
            user_email="user@example.com",
            schedule="0 9 * * * * *",  # 7 fields, should be 5
            action="send_reminder",
        )
        add_rule(rule, test_config)

        # Rule is saved - no validation
        rules = get_user_rules("user@example.com", test_config)
        assert len(rules) == 1

        # croniter accepts 5-7 fields, so this might work depending on version
        # but with 7 fields, the behavior is undefined
        try:
            cron = croniter("0 9 * * * * *")
            # If it doesn't throw, the behavior is unpredictable
        except Exception:
            pass  # Expected

    def test_invalid_cron_out_of_range_minute(self, test_config):
        """Test cron expression with minute out of range (0-59)."""
        with pytest.raises(ValueError, match="Invalid cron schedule"):
            Rule.create_time_rule(
                user_email="user@example.com",
                schedule="60 9 * * *",  # 60 is out of range (0-59)
                action="send_reminder",
            )

    def test_invalid_cron_out_of_range_hour(self, test_config):
        """Test cron expression with hour out of range (0-23)."""
        with pytest.raises(ValueError, match="Invalid cron schedule"):
            Rule.create_time_rule(
                user_email="user@example.com",
                schedule="0 25 * * *",  # 25 is out of range (0-23)
                action="send_reminder",
            )

    def test_invalid_cron_out_of_range_day_of_week(self, test_config):
        """Test cron expression with day of week out of range (0-6)."""
        with pytest.raises(ValueError, match="Invalid cron schedule"):
            Rule.create_time_rule(
                user_email="user@example.com",
                schedule="0 9 * * 8",  # 8 is out of range (0-6 or 0-7)
                action="send_reminder",
            )

    def test_invalid_cron_non_numeric(self, test_config):
        """Test cron expression with non-numeric values."""
        with pytest.raises(ValueError, match="Invalid cron schedule"):
            Rule.create_time_rule(
                user_email="user@example.com",
                schedule="abc def * * *",  # Invalid non-numeric
                action="send_reminder",
            )

    def test_invalid_cron_empty_string(self, test_config):
        """Test cron expression as empty string."""
        with pytest.raises(ValueError, match="Invalid cron schedule"):
            Rule.create_time_rule(
                user_email="user@example.com",
                schedule="",  # Empty
                action="send_reminder",
            )

    def test_invalid_cron_special_characters(self, test_config):
        """Test cron expression with invalid special characters."""
        with pytest.raises(ValueError, match="Invalid cron schedule"):
            Rule.create_time_rule(
                user_email="user@example.com",
                schedule="0 9 # @ !",  # Invalid special chars
                action="send_reminder",
            )

    def test_invalid_cron_null_none(self, test_config):
        """Test time rule without schedule (None)."""
        # Factory method creates rule even with None schedule
        rule = Rule(
            id="test-rule",
            user_email="user@example.com",
            type="time",
            action="send_reminder",
            schedule=None,  # None schedule for time rule
        )
        add_rule(rule, test_config)

        rules = get_user_rules("user@example.com", test_config)
        assert len(rules) == 1
        assert rules[0].schedule is None

        # Scheduler will skip this rule (checks `if not rule.schedule`)
        # But this is a silent failure - no warning or error


class TestOverlappingEventRules:
    """Test handling of overlapping/duplicate event rules."""

    def test_duplicate_event_rules_same_description(self, test_config):
        """Test creating multiple event rules with same description."""
        rule1 = Rule.create_event_rule(
            user_email="user@example.com",
            description="vet appointment",
            trigger={"days_before": 3},
            action="send_reminder",
        )

        # Wait a bit to ensure different ID
        time.sleep(0.002)

        rule2 = Rule.create_event_rule(
            user_email="user@example.com",
            description="vet appointment",  # Same description
            trigger={"days_before": 3},      # Same trigger
            action="send_reminder",          # Same action
        )

        add_rule(rule1, test_config)
        add_rule(rule2, test_config)

        # BUG: Both duplicate rules are saved
        rules = get_user_rules("user@example.com", test_config)
        assert len(rules) == 2
        # Both rules will fire for the same event!

    def test_overlapping_event_rules_different_days_before(self, test_config):
        """Test event rules with same description but different trigger times."""
        rule1 = Rule.create_event_rule(
            user_email="user@example.com",
            description="vet appointment",
            trigger={"days_before": 7},
            action="send_reminder",
            params={"message_template": "1 week warning"},
        )

        time.sleep(0.002)

        rule2 = Rule.create_event_rule(
            user_email="user@example.com",
            description="vet appointment",
            trigger={"days_before": 1},
            action="send_reminder",
            params={"message_template": "Tomorrow!"},
        )

        add_rule(rule1, test_config)
        add_rule(rule2, test_config)

        # This is valid - different trigger windows
        rules = get_user_rules("user@example.com", test_config)
        assert len(rules) == 2

    def test_overlapping_time_rules_same_schedule(self, test_config):
        """Test multiple time rules with exact same schedule."""
        rule1 = Rule.create_time_rule(
            user_email="user@example.com",
            schedule="0 9 * * 1",  # Monday 9am
            action="weekly_schedule_summary",
        )

        time.sleep(0.002)

        rule2 = Rule.create_time_rule(
            user_email="user@example.com",
            schedule="0 9 * * 1",  # Same schedule
            action="weekly_schedule_summary",  # Same action
        )

        add_rule(rule1, test_config)
        add_rule(rule2, test_config)

        # BUG: Both rules saved - will fire twice at same time
        rules = get_user_rules("user@example.com", test_config)
        assert len(rules) == 2

    def test_similar_event_descriptions_ai_matching(self, test_config):
        """Test event rules with similar descriptions that AI might match together."""
        rule1 = Rule.create_event_rule(
            user_email="user@example.com",
            description="vet appointment",
            trigger={"days_before": 2},
            action="send_reminder",
        )

        time.sleep(0.002)

        rule2 = Rule.create_event_rule(
            user_email="user@example.com",
            description="veterinary visit",  # Similar but not identical
            trigger={"days_before": 2},
            action="send_reminder",
        )

        add_rule(rule1, test_config)
        add_rule(rule2, test_config)

        # Both rules saved - AI might match both to same calendar event
        rules = get_user_rules("user@example.com", test_config)
        assert len(rules) == 2
        # Potential issue: AI matching could fire both rules for one event


class TestRulesMissingFields:
    """Test rules with missing required fields."""

    def test_rule_from_dict_missing_id(self, test_config):
        """Test loading rule from dict missing required 'id' field."""
        data = {
            # "id" is missing
            "user_email": "user@example.com",
            "type": "time",
            "action": "send_reminder",
        }

        with pytest.raises(KeyError):
            Rule.from_dict(data)

    def test_rule_from_dict_missing_user_email(self, test_config):
        """Test loading rule from dict missing required 'user_email' field."""
        data = {
            "id": "rule-1",
            # "user_email" is missing
            "type": "time",
            "action": "send_reminder",
        }

        with pytest.raises(KeyError):
            Rule.from_dict(data)

    def test_rule_from_dict_missing_type(self, test_config):
        """Test loading rule from dict missing required 'type' field."""
        data = {
            "id": "rule-1",
            "user_email": "user@example.com",
            # "type" is missing
            "action": "send_reminder",
        }

        with pytest.raises(KeyError):
            Rule.from_dict(data)

    def test_rule_from_dict_missing_action(self, test_config):
        """Test loading rule from dict missing required 'action' field."""
        data = {
            "id": "rule-1",
            "user_email": "user@example.com",
            "type": "time",
            # "action" is missing
        }

        with pytest.raises(KeyError):
            Rule.from_dict(data)

    def test_corrupted_rules_file_missing_fields(self, test_config):
        """Test loading corrupted rules file with incomplete rule data.

        FIX: Rules with missing required fields are now filtered out instead
        of crashing. This allows the system to continue operating with valid
        rules even if some are corrupted.
        """
        # Simulate corrupted file with missing fields
        corrupted_data = {
            "user@example.com": [
                {
                    "id": "rule-1",
                    # Missing other required fields
                }
            ]
        }
        test_config.rules_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.rules_file.write_text(json.dumps(corrupted_data))

        # FIXED: Corrupted rules are filtered out instead of crashing
        rules = get_user_rules("user@example.com", test_config)
        assert len(rules) == 0  # Corrupted rule was filtered out

    def test_event_rule_missing_description(self, test_config):
        """Test event rule without description (should be required)."""
        # Factory method allows None description
        rule = Rule.create_event_rule(
            user_email="user@example.com",
            description="",  # Empty description
            trigger={"days_before": 2},
            action="send_reminder",
        )
        add_rule(rule, test_config)

        rules = get_user_rules("user@example.com", test_config)
        assert len(rules) == 1
        assert rules[0].description == ""
        # Empty description will fail AI matching

    def test_event_rule_missing_trigger(self, test_config):
        """Test event rule without trigger (empty dict)."""
        rule = Rule.create_event_rule(
            user_email="user@example.com",
            description="vet appointment",
            trigger={},  # Empty trigger
            action="send_reminder",
        )
        add_rule(rule, test_config)

        rules = get_user_rules("user@example.com", test_config)
        assert len(rules) == 1
        assert rules[0].trigger == {}
        # days_before defaults to 0 in scheduler

    def test_rule_with_invalid_type(self, test_config):
        """Test rule with invalid type (not 'time' or 'event')."""
        rule = Rule(
            id="rule-invalid-type",
            user_email="user@example.com",
            type="invalid_type",  # Invalid
            action="send_reminder",
        )
        add_rule(rule, test_config)

        rules = get_user_rules("user@example.com", test_config)
        assert len(rules) == 1
        # Scheduler will skip this rule silently

    def test_rule_with_invalid_action(self, test_config):
        """Test rule with invalid action."""
        rule = Rule.create_time_rule(
            user_email="user@example.com",
            schedule="0 9 * * *",
            action="nonexistent_action",  # Invalid action
        )
        add_rule(rule, test_config)

        rules = get_user_rules("user@example.com", test_config)
        assert len(rules) == 1
        # Scheduler will print "Unknown action" and do nothing


class TestVeryLongRuleDescriptions:
    """Test rules with very long descriptions and field values."""

    def test_very_long_description_10k_chars(self, test_config):
        """Test event rule with 10,000 character description."""
        long_desc = "a" * 10_000
        rule = Rule.create_event_rule(
            user_email="user@example.com",
            description=long_desc,
            trigger={"days_before": 1},
            action="send_reminder",
        )
        add_rule(rule, test_config)

        rules = get_user_rules("user@example.com", test_config)
        assert len(rules) == 1
        assert len(rules[0].description) == 10_000

    def test_very_long_description_100k_chars(self, test_config):
        """Test event rule with 100,000 character description."""
        long_desc = "x" * 100_000
        rule = Rule.create_event_rule(
            user_email="user@example.com",
            description=long_desc,
            trigger={"days_before": 1},
            action="send_reminder",
        )
        add_rule(rule, test_config)

        rules = get_user_rules("user@example.com", test_config)
        assert len(rules) == 1
        assert len(rules[0].description) == 100_000
        # This will cause huge AI prompts in scheduler

    def test_very_long_message_template(self, test_config):
        """Test rule with very long message template."""
        long_template = "Message: " + "z" * 50_000
        rule = Rule.create_event_rule(
            user_email="user@example.com",
            description="vet",
            trigger={"days_before": 1},
            action="send_reminder",
            params={"message_template": long_template},
        )
        add_rule(rule, test_config)

        rules = get_user_rules("user@example.com", test_config)
        assert len(rules) == 1
        assert len(rules[0].params["message_template"]) == 50_009

    def test_very_long_email_address(self, test_config):
        """Test rule with very long email address."""
        # RFC 5321 limits email to 254 chars, but we don't validate
        long_email = "a" * 200 + "@example.com"
        rule = Rule.create_time_rule(
            user_email=long_email,
            schedule="0 9 * * *",
            action="send_reminder",
        )
        add_rule(rule, test_config)

        data = load_rules(test_config)
        assert long_email in data
        assert len(data[long_email]) == 1

    def test_many_rules_per_user(self, test_config):
        """Test user with very many rules (1000)."""
        email = "user@example.com"

        for i in range(1000):
            rule = Rule.create_time_rule(
                user_email=email,
                schedule=f"{i % 60} {i % 24} * * *",
                action="send_reminder",
            )
            add_rule(rule, test_config)

        rules = get_user_rules(email, test_config)
        assert len(rules) == 1000

    def test_deeply_nested_params(self, test_config):
        """Test rule with deeply nested params dictionary."""
        # Create deeply nested structure
        nested = {"level": 0}
        current = nested
        for i in range(100):
            current["nested"] = {"level": i + 1}
            current = current["nested"]

        rule = Rule.create_event_rule(
            user_email="user@example.com",
            description="test",
            trigger={"days_before": 1},
            action="send_reminder",
            params=nested,
        )
        add_rule(rule, test_config)

        rules = get_user_rules("user@example.com", test_config)
        assert len(rules) == 1
        assert rules[0].params["level"] == 0

    def test_large_trigger_dict(self, test_config):
        """Test rule with very large trigger dictionary."""
        large_trigger = {f"key_{i}": f"value_{i}" for i in range(10_000)}
        rule = Rule.create_event_rule(
            user_email="user@example.com",
            description="test",
            trigger=large_trigger,
            action="send_reminder",
        )
        add_rule(rule, test_config)

        rules = get_user_rules("user@example.com", test_config)
        assert len(rules) == 1
        assert len(rules[0].trigger) == 10_000


class TestCronScheduleEdgeCases:
    """Test edge cases in cron schedule handling in scheduler context."""

    def test_cron_every_minute(self, test_config):
        """Test cron that fires every minute."""
        rule = Rule.create_time_rule(
            user_email="user@example.com",
            schedule="* * * * *",  # Every minute
            action="send_reminder",
        )
        add_rule(rule, test_config)

        # Valid schedule
        cron = croniter("* * * * *")
        next_fire = cron.get_next(datetime)
        assert next_fire is not None

    def test_cron_feb_29_non_leap_year(self, test_config):
        """Test cron for Feb 29 in non-leap year."""
        rule = Rule.create_time_rule(
            user_email="user@example.com",
            schedule="0 9 29 2 *",  # Feb 29
            action="send_reminder",
        )
        add_rule(rule, test_config)

        # Valid but only fires on leap years
        cron = croniter("0 9 29 2 *", datetime(2025, 1, 1))
        next_fire = cron.get_next(datetime)
        # Should be Feb 29, 2028 (next leap year)
        assert next_fire.month == 2
        assert next_fire.day == 29
        assert next_fire.year >= 2028

    def test_cron_day_31_short_month(self, test_config):
        """Test cron for day 31 in months with only 30 days."""
        rule = Rule.create_time_rule(
            user_email="user@example.com",
            schedule="0 9 31 * *",  # 31st of every month
            action="send_reminder",
        )
        add_rule(rule, test_config)

        # Valid - only fires in months with 31 days
        cron = croniter("0 9 31 * *", datetime(2026, 4, 1))  # April has 30 days
        next_fire = cron.get_next(datetime)
        # Should skip to May 31
        assert next_fire.day == 31
        assert next_fire.month in [1, 3, 5, 7, 8, 10, 12]

    def test_cron_conflicting_day_and_weekday(self, test_config):
        """Test cron with both day-of-month and day-of-week specified."""
        rule = Rule.create_time_rule(
            user_email="user@example.com",
            schedule="0 9 15 * 1",  # 15th AND Monday
            action="send_reminder",
        )
        add_rule(rule, test_config)

        # croniter treats this as OR (fires on 15th OR on Monday)
        cron = croniter("0 9 15 * 1", datetime(2026, 1, 1))
        next_fire = cron.get_next(datetime)
        # Should fire on either Monday or 15th, whichever comes first
        assert next_fire is not None


class TestRuleIdCollisions:
    """Test potential rule ID collisions."""

    def test_rule_id_based_on_timestamp(self, test_config):
        """Test that rapid rule creation can create ID collisions."""
        rules_created = []

        # Create rules very rapidly
        for _ in range(10):
            rule = Rule.create_time_rule(
                user_email="user@example.com",
                schedule="0 9 * * *",
                action="send_reminder",
            )
            rules_created.append(rule)
            add_rule(rule, test_config)

        # Check for duplicate IDs
        ids = [r.id for r in rules_created]
        unique_ids = set(ids)

        # Due to millisecond resolution, some IDs might collide
        # This is a potential bug if rules are created very fast
        rules_in_file = get_user_rules("user@example.com", test_config)
        assert len(rules_in_file) == 10  # All should be saved even with same ID

    def test_manual_duplicate_ids(self, test_config):
        """Test manually creating rules with duplicate IDs."""
        rule1 = Rule(
            id="duplicate-id",
            user_email="user@example.com",
            type="time",
            action="action1",
            schedule="0 9 * * *",
        )
        rule2 = Rule(
            id="duplicate-id",  # Same ID
            user_email="user@example.com",
            type="time",
            action="action2",
            schedule="0 10 * * *",
        )

        add_rule(rule1, test_config)
        add_rule(rule2, test_config)

        # BUG: Both rules saved with same ID
        rules = get_user_rules("user@example.com", test_config)
        assert len(rules) == 2
        # Deleting by ID will only delete first match
        deleted = delete_rule("user@example.com", "duplicate-id", test_config)
        assert deleted is True

        remaining = get_user_rules("user@example.com", test_config)
        assert len(remaining) == 1  # One duplicate remains


class TestThreadSafetyStress:
    """Test thread safety under stress."""

    def test_concurrent_adds_and_deletes(self, test_config):
        """Test concurrent add and delete operations."""
        import threading

        errors = []

        def add_rules():
            try:
                for i in range(20):
                    rule = Rule.create_time_rule(
                        user_email=f"user{i % 5}@example.com",
                        schedule=f"{i % 60} 9 * * *",
                        action="send_reminder",
                    )
                    add_rule(rule, test_config)
            except Exception as e:
                errors.append(e)

        def delete_rules():
            try:
                for _ in range(10):
                    rules = get_user_rules("user0@example.com", test_config)
                    if rules:
                        delete_rule("user0@example.com", rules[0].id, test_config)
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(3):
            t1 = threading.Thread(target=add_rules)
            t2 = threading.Thread(target=delete_rules)
            threads.extend([t1, t2])

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No crashes
        assert len(errors) == 0

        # File should still be valid JSON
        data = load_rules(test_config)
        assert isinstance(data, dict)
