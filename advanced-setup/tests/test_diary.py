"""Tests for src/diary.py"""

from datetime import datetime

import pytest

from src.diary import (
    DiaryEntry,
    get_week_id,
    get_week_bounds,
    save_diary_entry,
    get_user_diary_entries,
    get_diary_entry,
)


class TestGetWeekId:
    """Tests for get_week_id function."""

    def test_normal_date(self):
        """Should return correct week ID for a normal date."""
        date = datetime(2026, 1, 15)  # Thursday of week 3
        assert get_week_id(date) == "2026-W03"

    def test_year_boundary_dec_to_next_year(self):
        """Dec 29-31 might be ISO week 1 of next year."""
        # Dec 29, 2025 is actually ISO week 1 of 2026 (Monday)
        date = datetime(2025, 12, 29)
        week_id = get_week_id(date)
        # Should use ISO year (2026), not calendar year (2025)
        assert week_id == "2026-W01", f"Dec 29, 2025 should be 2026-W01, got {week_id}"

    def test_year_boundary_jan_to_prev_year(self):
        """Jan 1-3 might be ISO week 52/53 of previous year."""
        # Jan 1, 2027 is a Friday, which is ISO week 53 of 2026
        date = datetime(2027, 1, 1)
        week_id = get_week_id(date)
        # Should use ISO year (2026), not calendar year (2027)
        assert week_id == "2026-W53", f"Jan 1, 2027 should be 2026-W53, got {week_id}"

    def test_uses_current_time_when_none(self):
        """Should use current datetime when date is None."""
        result = get_week_id(None)
        # Just check format is valid
        assert result.startswith("20")  # Year starts with 20
        assert "-W" in result
        week_num = int(result.split("-W")[1])
        assert 1 <= week_num <= 53


class TestGetWeekBounds:
    """Tests for get_week_bounds function."""

    def test_returns_monday_to_sunday(self):
        """Should return Monday 00:00 to Sunday 23:59:59."""
        # Wednesday Jan 15, 2026
        date = datetime(2026, 1, 15, 14, 30)
        monday, sunday = get_week_bounds(date)

        assert monday.weekday() == 0  # Monday
        assert monday.day == 12  # Jan 12
        assert monday.hour == 0
        assert monday.minute == 0

        assert sunday.weekday() == 6  # Sunday
        assert sunday.day == 18  # Jan 18
        assert sunday.hour == 23
        assert sunday.minute == 59

    def test_date_on_monday(self):
        """Should return same week if date is Monday."""
        monday_date = datetime(2026, 1, 12)  # Monday
        monday, sunday = get_week_bounds(monday_date)
        assert monday.day == 12
        assert sunday.day == 18

    def test_date_on_sunday(self):
        """Should return same week if date is Sunday."""
        sunday_date = datetime(2026, 1, 18)  # Sunday
        monday, sunday = get_week_bounds(sunday_date)
        assert monday.day == 12
        assert sunday.day == 18


class TestDiaryEntry:
    """Tests for DiaryEntry dataclass."""

    def test_to_dict_roundtrip(self):
        """Should serialize and deserialize correctly."""
        entry = DiaryEntry(
            id="2026-W03",
            user_email="test@example.com",
            week_start="2026-01-12",
            week_end="2026-01-18",
            content="Test content",
            sources={"todos_completed": ["Task 1"]},
            created_at="2026-01-19T10:00:00",
        )
        data = entry.to_dict()
        restored = DiaryEntry.from_dict(data)

        assert restored.id == entry.id
        assert restored.user_email == entry.user_email
        assert restored.content == entry.content
        assert restored.sources == entry.sources


class TestDiaryPersistence:
    """Tests for diary save/load functions."""

    def test_save_and_retrieve_entry(self, test_config):
        """Should save and retrieve diary entry."""
        entry = DiaryEntry(
            id="2026-W03",
            user_email="test@example.com",
            week_start="2026-01-12",
            week_end="2026-01-18",
            content="Test diary content",
            sources={},
        )
        save_diary_entry(entry, test_config)

        retrieved = get_diary_entry("test@example.com", "2026-W03", test_config)
        assert retrieved is not None
        assert retrieved.content == "Test diary content"

    def test_get_user_entries_sorted(self, test_config):
        """Should return entries sorted by week_start descending."""
        entries = [
            DiaryEntry(
                id="2026-W01",
                user_email="test@example.com",
                week_start="2026-01-05",
                week_end="2026-01-11",
                content="Week 1",
                sources={},
            ),
            DiaryEntry(
                id="2026-W03",
                user_email="test@example.com",
                week_start="2026-01-19",
                week_end="2026-01-25",
                content="Week 3",
                sources={},
            ),
            DiaryEntry(
                id="2026-W02",
                user_email="test@example.com",
                week_start="2026-01-12",
                week_end="2026-01-18",
                content="Week 2",
                sources={},
            ),
        ]
        for entry in entries:
            save_diary_entry(entry, test_config)

        retrieved = get_user_diary_entries("test@example.com", test_config)
        assert len(retrieved) == 3
        assert retrieved[0].id == "2026-W03"  # Most recent first
        assert retrieved[1].id == "2026-W02"
        assert retrieved[2].id == "2026-W01"

    def test_entry_not_found(self, test_config):
        """Should return None for non-existent entry."""
        result = get_diary_entry("nonexistent@example.com", "2026-W99", test_config)
        assert result is None
