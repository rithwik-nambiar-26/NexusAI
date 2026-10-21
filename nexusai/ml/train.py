#!/usr/bin/env python
"""Train the intent classifier and save model artifacts.

This script:
1. Builds the dataset from scenarios + synthetic examples
2. Splits into train/test
3. Trains the TF-IDF + Logistic Regression classifier
4. Evaluates on test set with cross-validation on train
5. Saves model artifacts to nexusai/ml/models/
6. Saves evaluation results to experiments/results/intent_classification/
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure project root is in path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# ruff: noqa: E402
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split

from nexusai.ml.classifier import IntentClassifier
from nexusai.ml.dataset import build_dataset


def main() -> int:
    print("=" * 60)
    print("NexusAI Intent Classifier Training")
    print("=" * 60)

    # Build dataset
    print("\n1. Building dataset...")
    df = build_dataset()
    print(f"   Total examples: {len(df)}")
    print("   Class distribution:")
    for intent, count in sorted(df["intent"].value_counts().items()):
        print(f"     {intent}: {count}")

    # Check for duplicates
    dupes = df[df.duplicated(subset=["text"], keep=False)]
    if len(dupes) > 0:
        print(f"   WARNING: {len(dupes)} duplicate texts found!")
        return 1
    else:
        print("   No exact duplicates found.")

    # Split dataset (train/test only for small dataset)
    print("\n2. Splitting dataset (train/test)...")

    train, test = train_test_split(
        df,
        test_size=0.25,
        stratify=df["intent"],
        random_state=42,
    )
    print(f"   Train: {len(train)}, Test: {len(test)}")

    # Save splits
    print("\n3. Saving dataset splits...")
    dataset_dir = ROOT / "experiments" / "datasets" / "intent_classification"
    dataset_dir.mkdir(parents=True, exist_ok=True)

    train.to_json(dataset_dir / "train.json", orient="records", indent=2)
    test.to_json(dataset_dir / "test.json", orient="records", indent=2)
    df.to_json(dataset_dir / "full.json", orient="records", indent=2)
    print(f"   Saved to {dataset_dir}")

    # Train classifier
    print("\n4. Training classifier...")
    classifier = IntentClassifier()

    train_texts = train["text"].tolist()
    train_labels = train["intent"].tolist()
    test_texts = test["text"].tolist()
    test_labels = test["intent"].tolist()

    metadata = classifier.train(train_texts, train_labels)
    print(f"   Classes: {metadata['n_classes']}")
    print(f"   Train samples: {metadata['n_train_samples']}")

    # Cross-validation on training set
    print("\n5. Cross-validation on training set...")
    # Rebuild pipeline for CV
    cv_pipeline = classifier._create_pipeline()
    cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
    cv_scores = cross_val_score(cv_pipeline, train_texts, train_labels, cv=cv, scoring="f1_macro")
    print(f"   3-fold CV macro F1: {cv_scores.mean():.4f} (+/- {cv_scores.std():.4f})")

    # Evaluate on test set
    print("\n6. Evaluating on held-out test set...")
    test_metrics = classifier._evaluate(test_texts, test_labels)

    print(f"   Test accuracy: {test_metrics['accuracy']:.4f}")
    print(f"   Test macro precision: {test_metrics['macro_precision']:.4f}")
    print(f"   Test macro recall: {test_metrics['macro_recall']:.4f}")
    print(f"   Test macro F1: {test_metrics['macro_f1']:.4f}")

    print("\n   Per-class metrics:")
    for cls, metrics in test_metrics["per_class"].items():
        print(f"     {cls}: P={metrics['precision']:.3f} R={metrics['recall']:.3f} F1={metrics['f1']:.3f} (support={metrics['support']})")

    print("\n   Confusion matrix:")
    print(f"     Labels: {test_metrics['confusion_matrix_labels']}")
    for i, row in enumerate(test_metrics["confusion_matrix"]):
        print(f"     {test_metrics['confusion_matrix_labels'][i]}: {row}")

    # Save model
    print("\n7. Saving model artifacts...")
    classifier.save()
    print("   Model saved to nexusai/ml/models/")

    # Save evaluation results
    print("\n8. Saving evaluation results...")
    results_dir = ROOT / "experiments" / "results" / "intent_classification"
    results_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "model_metadata": metadata,
        "cross_validation": {
            "cv_macro_f1_mean": float(cv_scores.mean()),
            "cv_macro_f1_std": float(cv_scores.std()),
            "cv_scores": [float(s) for s in cv_scores],
        },
        "test_metrics": test_metrics,
        "thresholds": {
            "confidence_threshold": classifier.confidence_threshold,
            "clarification_threshold": classifier.clarification_threshold,
        },
        "dataset_info": {
            "total_examples": len(df),
            "train_size": len(train),
            "test_size": len(test),
            "class_distribution": df["intent"].value_counts().to_dict(),
        },
    }

    (results_dir / "evaluation.json").write_text(json.dumps(results, indent=2))
    print(f"   Results saved to {results_dir}/evaluation.json")

    print("\n" + "=" * 60)
    print("Training complete!")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
