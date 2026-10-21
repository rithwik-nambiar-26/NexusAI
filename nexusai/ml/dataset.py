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
        IntentCategory.CHANNEL_UNAVAILABLE,
        "scenario",
    ),

    # DOCUMENT_EXTRACTION (1 scenario: SC-09)
    (
        "Fetch the contents of data/sample/product_manual.md and list its section headings.",
        IntentCategory.DOCUMENT_EXTRACTION,
        "scenario",
    ),

    # DOCUMENT_TRANSFORMATION (1 scenario: SC-13, SC-16)
    (
        "Read data/sample/meeting_notes.md, extract every action item with an owner, write them to notes/action_items.md.",
        IntentCategory.DOCUMENT_TRANSFORMATION,
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

    # INVALID (1 scenario: SC-14)
    (
        "Deal with the report.",
        IntentCategory.INVALID,
        "scenario",
    ),

    # DOCUMENT_TRANSFORMATION (1 scenario: SC-16)
    (
        "Read data/sample/meeting_notes.md, extract every action item with an owner, write them to notes/action_items.md, and then summarise that list into a single sentence.",
        IntentCategory.DOCUMENT_TRANSFORMATION,
        "scenario",
    ),
]


# ---------------------------------------------------------------------------
# Synthetic variations for robustness
# These are explicitly authored examples, NOT real user data
# ---------------------------------------------------------------------------

SYNTHETIC_EXAMPLES: list[tuple[str, IntentCategory, str]] = [
    # DOCUMENT_QUESTION_ANSWERING variations (9 total: 4 scenario + 5 synthetic)
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
    (
        "What is the maintenance schedule in the equipment manual?",
        IntentCategory.DOCUMENT_QUESTION_ANSWERING,
        "synthetic",
    ),
    (
        "Find the troubleshooting section for error code E-42 in the manual.",
        IntentCategory.DOCUMENT_QUESTION_ANSWERING,
        "synthetic",
    ),
    (
        "What are the system requirements listed in the documentation?",
        IntentCategory.DOCUMENT_QUESTION_ANSWERING,
        "synthetic",
    ),

    # DOCUMENT_SUMMARISATION variations (6 total: 2 scenario + 4 synthetic)
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
    (
        "Summarise the key findings from the quarterly report.",
        IntentCategory.DOCUMENT_SUMMARISATION,
        "synthetic",
    ),
    (
        "Provide a three-bullet summary of the project proposal.",
        IntentCategory.DOCUMENT_SUMMARISATION,
        "synthetic",
    ),

    # DATA_ANALYSIS variations (6 total: 2 scenario + 4 synthetic)
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
    (
        "Compare monthly sales trends across all regions.",
        IntentCategory.DATA_ANALYSIS,
        "synthetic",
    ),
    (
        "Find the month with the highest sales growth rate.",
        IntentCategory.DATA_ANALYSIS,
        "synthetic",
    ),

    # RESEARCH variations (5 total: 1 scenario + 4 synthetic)
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
    (
        "Find and compare password managers for team use.",
        IntentCategory.RESEARCH,
        "synthetic",
    ),
    (
        "Research open-source alternatives to Adobe Creative Suite.",
        IntentCategory.RESEARCH,
        "synthetic",
    ),

    # COMMUNICATION variations (5 total: 1 scenario + 1 channel_unavailable + 3 synthetic)
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
    (
        "Send a Slack message to the dev channel with the deployment status.",
        IntentCategory.COMMUNICATION,
        "synthetic",
    ),
    (
        "Draft a reply to the client's inquiry about pricing.",
        IntentCategory.COMMUNICATION,
        "synthetic",
    ),

    # DOCUMENT_EXTRACTION variations (5 total: 1 scenario + 4 synthetic)
    (
        "Extract all dates from the contract document.",
        IntentCategory.DOCUMENT_EXTRACTION,
        "synthetic",
    ),
    (
        "List all tables in the product manual.",
        IntentCategory.DOCUMENT_EXTRACTION,
        "synthetic",
    ),
    (
        "Search the document for mentions of 'warranty'.",
        IntentCategory.DOCUMENT_EXTRACTION,
        "synthetic",
    ),
    (
        "Extract all email addresses from the contact list.",
        IntentCategory.DOCUMENT_EXTRACTION,
        "synthetic",
    ),
    (
        "Find all references to the compliance section in the policy document.",
        IntentCategory.DOCUMENT_EXTRACTION,
        "synthetic",
    ),

    # DOCUMENT_TRANSFORMATION variations (3 total: 2 scenario + 1 synthetic)
    (
        "Convert the meeting notes to a PDF.",
        IntentCategory.DOCUMENT_TRANSFORMATION,
        "synthetic",
    ),
    (
        "Convert the CSV data to JSON format.",
        IntentCategory.DOCUMENT_TRANSFORMATION,
        "synthetic",
    ),
    (
        "Transform the markdown notes into a structured task list.",
        IntentCategory.DOCUMENT_TRANSFORMATION,
        "synthetic",
    ),

    # DESTRUCTIVE_OPERATION variations (3 total: 1 scenario + 2 synthetic)
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
    (
        "Purge all logs older than 30 days.",
        IntentCategory.DESTRUCTIVE_OPERATION,
        "synthetic",
    ),

    # INVALID variations (5 total: 2 scenario + 3 synthetic)
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
    (
        "xyz random gibberish",
        IntentCategory.INVALID,
        "synthetic",
    ),
    (
        "   \t\n  ",
        IntentCategory.INVALID,
        "synthetic",
    ),

    # INFEASIBLE variations (3 total: 1 scenario + 2 synthetic)
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
    (
        "Make me a millionaire overnight.",
        IntentCategory.INFEASIBLE,
        "synthetic",
    ),

    # OUT_OF_SCOPE variations (4 total: 1 scenario + 3 synthetic)
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
    (
        "Write a legally binding contract for me.",
        IntentCategory.OUT_OF_SCOPE,
        "synthetic",
    ),

    # CHANNEL_UNAVAILABLE variations (2 total: 1 scenario + 1 synthetic)
    (
        "Send a Telegram message to my boss saying I'm running late.",
        IntentCategory.CHANNEL_UNAVAILABLE,
        "synthetic",
    ),
    (
        "Post this update to our Discord announcements channel.",
        IntentCategory.CHANNEL_UNAVAILABLE,
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


def check_near_duplicates(df: pd.DataFrame, threshold: float = 0.9) -> list[tuple[int, int, float]]:
    """Check for near-duplicate texts using TF-IDF similarity.

    Returns:
        List of (idx1, idx2, similarity) for pairs above threshold
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
    tfidf_matrix = vectorizer.fit_transform(df["text"])
    similarity_matrix = cosine_similarity(tfidf_matrix)

    near_dupes = []
    n = len(df)
    for i in range(n):
        for j in range(i + 1, n):
            sim = similarity_matrix[i, j]
            if sim >= threshold:
                near_dupes.append((i, j, float(sim)))
    return near_dupes


def split_dataset(
    df: pd.DataFrame,
    test_size: float = 0.2,
    val_size: float = 0.2,
    random_state: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split dataset into train, validation, and test sets.

    Stratified by intent to maintain class distribution.
    Uses group-based splitting to prevent leakage from related examples.
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


def split_dataset_by_group(
    df: pd.DataFrame,
    group_col: str = "source",
    test_size: float = 0.2,
    val_size: float = 0.2,
    random_state: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split dataset by group to prevent leakage from related examples.

    All examples from the same source group go to the same split.
    """
    # Split groups
    from sklearn.model_selection import GroupShuffleSplit

    # First split: train+val vs test
    gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=random_state)
    train_val_idx, test_idx = next(gss.split(df, groups=df[group_col]))
    train_val = df.iloc[train_val_idx].reset_index(drop=True)
    test = df.iloc[test_idx].reset_index(drop=True)

    # Second split: train vs val
    val_relative = val_size / (1 - test_size)
    gss2 = GroupShuffleSplit(n_splits=1, test_size=val_relative, random_state=random_state)
    train_idx, val_idx = next(gss2.split(train_val, groups=train_val[group_col]))
    train = train_val.iloc[train_idx].reset_index(drop=True)
    val = train_val.iloc[val_idx].reset_index(drop=True)

    return train, val, test


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
        "train_distribution": get_class_distribution(train),
        "val_distribution": get_class_distribution(val),
        "test_distribution": get_class_distribution(test),
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

    # Check near-duplicates
    near_dupes = check_near_duplicates(df, threshold=0.85)
    if near_dupes:
        print(f"\nWARNING: {len(near_dupes)} near-duplicate pairs found (similarity >= 0.85)!")
        for i, j, sim in near_dupes[:10]:
            print(f"  {sim:.3f}: [{i}] {df.iloc[i]['text'][:60]}... | [{j}] {df.iloc[j]['text'][:60]}...")
    else:
        print("\nNo near-duplicates found (similarity >= 0.85).")

    # Split and save
    train, val, test = split_dataset(df)
    print(f"\nTrain: {len(train)}, Val: {len(val)}, Test: {len(test)}")

    output_dir = Path("experiments/datasets/intent_classification")
    save_splits(train, val, test, output_dir)
    print(f"\nSaved to {output_dir}")
