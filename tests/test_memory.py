"""Tests for the memory module."""

import pytest
from pathlib import Path

from src.memory import (
    Fact,
    add_fact,
    delete_fact,
    get_all_facts,
    get_facts_by_category,
    search_facts,
    update_fact,
    _get_memory_file,
)


@pytest.fixture
def test_email():
    return "test@example.com"


@pytest.fixture
def memory_dir(test_config, test_email):
    """Ensure memory directory uses test config."""
    memory_file = _get_memory_file(test_email)
    # Clean up any existing test data
    if memory_file.exists():
        memory_file.unlink()
    yield memory_file.parent
    # Cleanup after test
    if memory_file.exists():
        memory_file.unlink()


class TestFact:
    def test_to_dict_roundtrip(self):
        fact = Fact(
            id="fact_123",
            content="Has a cat named Oliver",
            category="pets",
            created_at="2024-01-15T10:00:00",
            source_context="my cat oliver",
            keywords=["cat", "oliver", "pet"],
        )
        data = fact.to_dict()
        restored = Fact.from_dict(data)

        assert restored.id == fact.id
        assert restored.content == fact.content
        assert restored.category == fact.category
        assert restored.keywords == fact.keywords


class TestAddFact:
    def test_adds_fact_to_storage(self, test_config, test_email, memory_dir):
        fact = add_fact(
            email=test_email,
            content="Has a cat named Oliver",
            category="pets",
            keywords=["cat", "oliver"],
        )

        assert fact.id.startswith("fact_")
        assert fact.content == "Has a cat named Oliver"
        assert fact.category == "pets"

        # Verify it's persisted
        facts = get_all_facts(test_email)
        assert len(facts) == 1
        assert facts[0].content == "Has a cat named Oliver"

    def test_multiple_facts_accumulate(self, test_config, test_email, memory_dir):
        add_fact(test_email, "Has a cat named Oliver", "pets")
        add_fact(test_email, "Uses Manhattan Vet", "locations")
        add_fact(test_email, "Prefers morning meetings", "preferences")

        facts = get_all_facts(test_email)
        assert len(facts) == 3


class TestSearchFacts:
    def test_search_by_content(self, test_config, test_email, memory_dir):
        add_fact(test_email, "Has a cat named Oliver", "pets", keywords=["cat"])
        add_fact(test_email, "Has a dog named Max", "pets", keywords=["dog"])

        results = search_facts(test_email, "cat")
        assert len(results) == 1
        assert "Oliver" in results[0].content

    def test_search_by_keyword(self, test_config, test_email, memory_dir):
        add_fact(test_email, "Goes to Manhattan Vet", "locations", keywords=["vet", "veterinarian"])

        results = search_facts(test_email, "veterinarian")
        assert len(results) == 1
        assert "Manhattan Vet" in results[0].content

    def test_search_case_insensitive(self, test_config, test_email, memory_dir):
        add_fact(test_email, "Has a cat named Oliver", "pets")

        results = search_facts(test_email, "OLIVER")
        assert len(results) == 1

    def test_search_returns_empty_for_no_match(self, test_config, test_email, memory_dir):
        add_fact(test_email, "Has a cat named Oliver", "pets")

        results = search_facts(test_email, "unicorn")
        assert len(results) == 0


class TestGetFactsByCategory:
    def test_filters_by_category(self, test_config, test_email, memory_dir):
        add_fact(test_email, "Has a cat named Oliver", "pets")
        add_fact(test_email, "Has a dog named Max", "pets")
        add_fact(test_email, "Uses Manhattan Vet", "locations")

        pet_facts = get_facts_by_category(test_email, "pets")
        assert len(pet_facts) == 2

        location_facts = get_facts_by_category(test_email, "locations")
        assert len(location_facts) == 1


class TestDeleteFact:
    def test_deletes_existing_fact(self, test_config, test_email, memory_dir):
        fact = add_fact(test_email, "Has a cat named Oliver", "pets")

        result = delete_fact(test_email, fact.id)
        assert result is True

        facts = get_all_facts(test_email)
        assert len(facts) == 0

    def test_returns_false_for_missing_fact(self, test_config, test_email, memory_dir):
        result = delete_fact(test_email, "nonexistent_id")
        assert result is False


class TestUpdateFact:
    def test_updates_fact_content(self, test_config, test_email, memory_dir):
        fact = add_fact(test_email, "Has a cat named Oliver", "pets")

        result = update_fact(test_email, fact.id, "Has a cat named Ollie")
        assert result is True

        facts = get_all_facts(test_email)
        assert facts[0].content == "Has a cat named Ollie"

    def test_returns_false_for_missing_fact(self, test_config, test_email, memory_dir):
        result = update_fact(test_email, "nonexistent_id", "new content")
        assert result is False
