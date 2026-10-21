"""Tests for intent classification dataset."""

from __future__ import annotations

from nexusai.ml.dataset import (
    SCENARIO_EXAMPLES,
    SYNTHETIC_EXAMPLES,
    build_dataset,
    check_duplicates,
    get_class_distribution,
)
from nexusai.ml.schemas import IntentCategory


def test_scenario_examples_count():
    """Test that we have the expected number of scenario examples."""
    # 18 scenarios, some map to same intent
    assert len(SCENARIO_EXAMPLES) == 18


def test_synthetic_examples_count():
    """Test that we have synthetic examples."""
    assert len(SYNTHETIC_EXAMPLES) > 0


def test_build_dataset():
    """Test dataset building."""
    df = build_dataset()

    assert len(df) == len(SCENARIO_EXAMPLES) + len(SYNTHETIC_EXAMPLES)
    assert set(df.columns) == {"text", "intent", "source"}
    assert df["source"].isin(["scenario", "synthetic"]).all()


def test_build_dataset_class_distribution():
    """Test class distribution is reasonable."""
    df = build_dataset()
    dist = get_class_distribution(df)

    # All 10 intents should be present
    assert len(dist) == 10
    for cat in IntentCategory:
        assert cat.value in dist
        assert dist[cat.value] >= 3  # At least 3 examples per class


def test_no_duplicate_texts():
    """Test that there are no exact duplicate texts."""
    df = build_dataset()
    dupes = check_duplicates(df)
    assert len(dupes) == 0


def test_split_dataset():
    """Test dataset splitting with appropriate sizes for small dataset."""
    df = build_dataset()
    # Use train/test split only (3-way split too small for 10 classes)
    from sklearn.model_selection import train_test_split

    train, test = train_test_split(
        df,
        test_size=0.25,
        stratify=df["intent"],
        random_state=42,
    )

    assert len(train) + len(test) == len(df)
    assert len(test) >= 10  # At least one per class
    assert len(train) >= 10

    # Check stratification - all classes present in each split
    for split in [train, test]:
        assert set(split["intent"].unique()) == set(df["intent"].unique())


def test_split_dataset_reproducibility():
    """Test that splits are reproducible with same random_state."""
    df = build_dataset()
    from sklearn.model_selection import train_test_split

    train1, test1 = train_test_split(
        df, test_size=0.25, stratify=df["intent"], random_state=42
    )
    train2, test2 = train_test_split(
        df, test_size=0.25, stratify=df["intent"], random_state=42
    )

    assert train1["text"].tolist() == train2["text"].tolist()
    assert test1["text"].tolist() == test2["text"].tolist()


def test_scenario_intents_match_schema():
    """Test that scenario example intents match IntentCategory."""
    for text, intent, source in SCENARIO_EXAMPLES:
        assert isinstance(intent, IntentCategory)
        assert intent in IntentCategory


def test_synthetic_intents_match_schema():
    """Test that synthetic example intents match IntentCategory."""
    for text, intent, source in SYNTHETIC_EXAMPLES:
        assert isinstance(intent, IntentCategory)
        assert intent in IntentCategory
