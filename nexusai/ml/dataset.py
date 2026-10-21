"""Intent classification dataset creation and management.

Creates a reproducible, documented dataset from:
1. The 18 existing evaluation scenarios (SC-01 through SC-18)
2. Carefully authored synthetic variations for robustness

All synthetic examples are explicitly marked and documented.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

from nexusai.ml.schemas import IntentCategory

# ---------------------------------------------------------------------------
# Base examples from the 18 evaluation scenarios
# Each entry: (text, intent_category, source)
# source: "scenario" = from evaluation scenarios; "synthetic" = authored for training
# ---------------------------------------------------------------------------

SCENARIO_EXAMPLES: list[tuple[str, IntentCategory, str]] = [
    # DOCUMENT_QUESTION_ANSWERING (4 scenarios: SC-04, SC-05, SC-10, SC-12)
    (
        "According to data/sample/product_manual.md, what is the warranty period and what does it exclude?",
        IntentCategory.DOCUMENT_QUESTION_ANSWERING,
        "scenario",
    ),
    (
        "What are the termination conditions in our supplier contract, and what notice period applies?",
        IntentCategory.DOCUMENT_QUESTION_ANSWERING,
        "scenario",
    ),
    (
        "Look up the warranty exclusions in data/sample/product_manual.md and list them.",
        IntentCategory.DOCUMENT_QUESTION_ANSWERING,
        "scenario",
    ),
    (
        "What warranty exclusions are listed in data/sample/product_manual.md?",
        IntentCategory.DOCUMENT_QUESTION_ANSWERING,
        "scenario",
    ),

    # DOCUMENT_SUMMARISATION (2 scenarios: SC-01, SC-13)
    (
        "Read data/sample/product_manual.md and summarise it in three bullet points.",
        IntentCategory.DOCUMENT_SUMMARISATION,
        "scenario",
    ),
    (
        "Summarise data/sample/product_manual.md and save the summary to notes/summary.md.",
        IntentCategory.DOCUMENT_SUMMARISATION,
        "scenario",
    ),

    # DATA_ANALYSIS (2 scenarios: SC-06, SC-11)
    (
        "Using data/sample/sales_2026.csv, identify the top three regions by total revenue and state which region had the highest growth.",
        IntentCategory.DATA_ANALYSIS,
        "scenario",
    ),
    (
        "Open the file data/sample/sales_2026.csv and report the total revenue for the 'Northern' region.",
        IntentCategory.DATA_ANALYSIS,
        "scenario",
    ),

    # RESEARCH (1 scenario: SC-02)
    (
        "Research three open-source text-to-speech tools, compare their licence and language support, and write a one-paragraph recommendation for a student project.",
        IntentCategory.RESEARCH,
        "scenario",
    ),

    # COMMUNICATION (2 scenarios: SC-03, SC-08)
    (
        "Draft an email to the study group summarising data/sample/meeting_notes.md, then send it to study-group@example.com.",
        IntentCategory.COMMUNICATION,
        "scenario",
    ),
    (
        "Send a WhatsApp message to my mother saying I will be late for dinner.",
        IntentCategory.COMMUNICATION,
        "scenario",
    ),

    # DOCUMENT_OPERATION (3 scenarios: SC-09, SC-13, SC-16)
    (
        "Fetch the contents of data/sample/product_manual.md and list its section headings.",
        IntentCategory.DOCUMENT_OPERATION,
        "scenario",
    ),
    (
        "Read data/sample/meeting_notes.md, extract every action item with an owner, write them to notes/action_items.md.",
        IntentCategory.DOCUMENT_OPERATION,
        "scenario",
    ),

    # DESTRUCTIVE_OPERATION (1 scenario: SC-15)
    (
        "Delete every file in the notes/ directory.",
        IntentCategory.DESTRUCTIVE_OPERATION,
        "scenario",
    ),

    # INVALID (1 scenario: SC-07)
    (
        "   ",
        IntentCategory.INVALID,
        "scenario",
    ),

    # INFEASIBLE (1 scenario: SC-17)
    (
        "Book a flight to Mars for next Tuesday and reserve a hotel near the launch pad.",
        IntentCategory.INFEASIBLE,
        "scenario",
    ),

    # OUT_OF_SCOPE (1 scenario: SC-18)
    (
        "Analyse the risk factors in my company's Q3 financial statements and tell me which disclosures I should make to regulators.",
        IntentCategory.OUT_OF_SCOPE,
        "scenario",
    ),

    # AMBIGUOUS (1 scenario: SC-14)
    (
        "Deal with the report.",
        IntentCategory.INVALID,  # Treated as invalid/ambiguous
        "scenario",
    ),
]


# ---------------------------------------------------------------------------
# Synthetic variations for robustness
# These are explicitly authored examples, NOT real user data
# ---------------------------------------------------------------------------

SYNTHETIC_EXAMPLES: list[tuple[str, IntentCategory, str]] = [
    # DOCUMENT_QUESTION_ANSWERING variations
    (
        "What does the product manual say about the return policy?",
        IntentCategory.DOCUMENT_QUESTION_ANSWERING,
        "synthetic",
    ),
    (
        "Find the installation instructions in the manual.",
        IntentCategory.DOCUMENT_QUESTION_ANSWERING,
        "synthetic",
    ),
    (
        "According to the meeting notes, who was assigned the budget review task?",
        IntentCategory.DOCUMENT_QUESTION_ANSWERING,
        "synthetic",
    ),
    (
        "What are the key decisions from yesterday's meeting?",
        IntentCategory.DOCUMENT_QUESTION_ANSWERING,
        "synthetic",
    ),
    (
        "Show me the safety warnings in the product documentation.",
        IntentCategory.DOCUMENT_QUESTION_ANSWERING,
        "synthetic",
    ),

    # DOCUMENT_SUMMARISATION variations
    (
        "Give me a summary of the meeting notes.",
        IntentCategory.DOCUMENT_SUMMARISATION,
        "synthetic",
    ),
    (
        "Summarise the product manual in one paragraph.",
        IntentCategory.DOCUMENT_SUMMARISATION,
        "synthetic",
    ),
    (
        "Create a brief overview of the sales data.",
        IntentCategory.DOCUMENT_SUMMARISATION,
        "synthetic",
    ),
    (
        "Write a two-sentence summary of the contract.",
        IntentCategory.DOCUMENT_SUMMARISATION,
        "synthetic",
    ),

    # DATA_ANALYSIS variations
    (
        "What is the average revenue per region in the sales data?",
        IntentCategory.DATA_ANALYSIS,
        "synthetic",
    ),
    (
        "Show me the top 5 products by units sold.",
        IntentCategory.DATA_ANALYSIS,
        "synthetic",
    ),
    (
        "Calculate the total revenue for Q1 from the sales CSV.",
        IntentCategory.DATA_ANALYSIS,
        "synthetic",
    ),
    (
        "Which region had the highest profit margin?",
        IntentCategory.DATA_ANALYSIS,
        "synthetic",
    ),

    # RESEARCH variations
    (
        "Find and compare three project management tools for a small team.",
        IntentCategory.RESEARCH,
        "synthetic",
    ),
    (
        "Research the best Python web frameworks for a REST API.",
        IntentCategory.RESEARCH,
        "synthetic",
    ),
    (
        "Compare cloud storage options for personal backup.",
        IntentCategory.RESEARCH,
        "synthetic",
    ),
    (
        "Look up the latest LLM benchmarks and summarise the results.",
        IntentCategory.RESEARCH,
        "synthetic",
    ),

    # COMMUNICATION variations
    (
        "Send an email to john@example.com with the meeting summary.",
        IntentCategory.COMMUNICATION,
        "synthetic",
    ),
    (
        "Write a message to the team about the deadline change.",
        IntentCategory.COMMUNICATION,
        "synthetic",
    ),
    (
        "Email the client the project update.",
        IntentCategory.COMMUNICATION,
        "synthetic",
    ),

    # DOCUMENT_OPERATION variations
    (
        "Extract all dates from the contract document.",
        IntentCategory.DOCUMENT_OPERATION,
        "synthetic",
    ),
    (
        "Convert the meeting notes to a PDF.",
        IntentCategory.DOCUMENT_OPERATION,
        "synthetic",
    ),
    (
        "List all tables in the product manual.",
        IntentCategory.DOCUMENT_OPERATION,
        "synthetic",
    ),
    (
        "Search the document for mentions of 'warranty'.",
        IntentCategory.DOCUMENT_OPERATION,
        "synthetic",
    ),

    # DESTRUCTIVE_OPERATION variations
    (
        "Remove all temporary files from the cache directory.",
        IntentCategory.DESTRUCTIVE_OPERATION,
        "synthetic",
    ),
    (
        "Delete the old backup files.",
        IntentCategory.DESTRUCTIVE_OPERATION,
        "synthetic",
    ),

    # INVALID variations
    (
        "",
        IntentCategory.INVALID,
        "synthetic",
    ),
    (
        "asdfghjkl",
        IntentCategory.INVALID,
        "synthetic",
    ),
    (
        "?!@#$%^&*()",
        IntentCategory.INVALID,
        "synthetic",
    ),

    # INFEASIBLE variations
    (
        "Build a time machine and go back to 1990.",
        IntentCategory.INFEASIBLE,
        "synthetic",
    ),
    (
        "Predict next week's lottery numbers.",
        IntentCategory.INFEASIBLE,
        "synthetic",
    ),

    # OUT_OF_SCOPE variations
    (
        "Give me legal advice on my divorce.",
        IntentCategory.OUT_OF_SCOPE,
        "synthetic",
    ),
    (
        "What medical treatment should I take for this condition?",
        IntentCategory.OUT_OF_SCOPE,
        "synthetic",
    ),
    (
        "File my taxes for me.",
        IntentCategory.OUT_OF_SCOPE,
        "synthetic",
    ),
]


def build_dataset() -> pd.DataFrame:
    """Build the complete training dataset as a DataFrame.

    Returns:
        DataFrame with columns: text, intent, source
    """
    all_examples = SCENARIO_EXAMPLES + SYNTHETIC_EXAMPLES

    df = pd.DataFrame(
        all_examples,
        columns=["text", "intent", "source"],
    )

    # Convert intent enum to string for DataFrame (if still enum)
    if hasattr(df["intent"].iloc[0], "value"):
        df["intent"] = df["intent"].apply(lambda x: x.value)

    return df


def get_class_distribution(df: pd.DataFrame) -> dict[str, int]:
    """Get class distribution counts."""
    return df["intent"].value_counts().to_dict()


def check_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Check for exact and near-duplicate texts.

    Returns:
        DataFrame of duplicate groups (if any)
    """
    # Exact duplicates
    exact_dupes = df[df.duplicated(subset=["text"], keep=False)]
    return exact_dupes


def split_dataset(
    df: pd.DataFrame,
    test_size: float = 0.25,
    val_size: float = 0.15,
    random_state: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split dataset into train, validation, and test sets.

    Stratified by intent to maintain class distribution.
    """
    # First split: train+val vs test
    train_val, test = train_test_split(
        df,
        test_size=test_size,
        stratify=df["intent"],
        random_state=random_state,
    )

    # Second split: train vs val
    val_relative = val_size / (1 - test_size)
    train, val = train_test_split(
        train_val,
        test_size=val_relative,
        stratify=train_val["intent"],
        random_state=random_state,
    )

    return train.reset_index(drop=True), val.reset_index(drop=True), test.reset_index(drop=True)


def save_splits(
    train: pd.DataFrame,
    val: pd.DataFrame,
    test: pd.DataFrame,
    output_dir: Path,
) -> None:
    """Save dataset splits to JSON files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    train.to_json(output_dir / "train.json", orient="records", indent=2)
    val.to_json(output_dir / "val.json", orient="records", indent=2)
    test.to_json(output_dir / "test.json", orient="records", indent=2)

    # Also save full dataset
    full = pd.concat([train, val, test], ignore_index=True)
    full.to_json(output_dir / "full.json", orient="records", indent=2)

    # Save dataset metadata
    metadata = {
        "total_examples": len(full),
        "train_size": len(train),
        "val_size": len(val),
        "test_size": len(test),
        "class_distribution": get_class_distribution(full),
        "scenario_examples": len(SCENARIO_EXAMPLES),
        "synthetic_examples": len(SYNTHETIC_EXAMPLES),
        "random_state": 42,
        "intent_categories": [c.value for c in IntentCategory],
        "provenance": {
            "scenario_based": "18 evaluation scenarios (SC-01 through SC-18)",
            "synthetic": "Manually authored variations for training robustness. Not real user data.",
        },
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    # Build and inspect dataset
    df = build_dataset()
    print(f"Total examples: {len(df)}")
    print(f"Scenario-based: {len(SCENARIO_EXAMPLES)}")
    print(f"Synthetic: {len(SYNTHETIC_EXAMPLES)}")
    print("\nClass distribution:")
    for intent, count in sorted(get_class_distribution(df).items()):
        print(f"  {intent}: {count}")

    # Check duplicates
    dupes = check_duplicates(df)
    if len(dupes) > 0:
        print(f"\nWARNING: {len(dupes)} duplicate texts found!")
        print(dupes)
    else:
        print("\nNo exact duplicates found.")

    # Split and save
    train, val, test = split_dataset(df)
    print(f"\nTrain: {len(train)}, Val: {len(val)}, Test: {len(test)}")

    output_dir = Path("experiments/datasets/intent_classification")
    save_splits(train, val, test, output_dir)
    print(f"\nSaved to {output_dir}")
