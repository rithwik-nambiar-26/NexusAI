#!/usr/bin/env python
"""Train the intent classifier and save model artifacts.

This script:
1. Builds the dataset from scenarios + synthetic examples
2. Splits into train/validation/test
3. Trains multiple model variants (LogisticRegression, LinearSVC)
4. Evaluates on validation and test sets with cross-validation
5. Selects best model based on validation macro F1
6. Saves model artifacts to nexusai/ml/models/
7. Saves evaluation results to experiments/results/intent_classification/
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure project root is in path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# ruff: noqa: E402
import json
import sys
from pathlib import Path

from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split

from nexusai.ml.classifier import IntentClassifier, ModelType
from nexusai.ml.dataset import build_dataset


def evaluate_model(
    classifier: IntentClassifier,
    train_texts: list[str],
    train_labels: list[str],
    val_texts: list[str],
    val_labels: list[str],
    test_texts: list[str],
    test_labels: list[str],
) -> dict[str, Any]:
    """Train and evaluate a classifier with full pipeline."""
    # Train with validation data for threshold tuning
    metadata = classifier.train(train_texts, train_labels, val_texts, val_labels)

    # Cross-validation on training set
    cv_pipeline = classifier._create_pipeline()
    cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
    cv_scores = cross_val_score(cv_pipeline, train_texts, train_labels, cv=cv, scoring="f1_macro")

    # Evaluate on validation and test
    val_metrics = classifier._evaluate(val_texts, val_labels)
    test_metrics = classifier._evaluate(test_texts, test_labels)

    return {
        "model_type": classifier.model_type.value,
        "train_size": len(train_texts),
        "val_size": len(val_texts),
        "test_size": len(test_texts),
        "cv_macro_f1_mean": float(cv_scores.mean()),
        "cv_macro_f1_std": float(cv_scores.std()),
        "cv_scores": [float(s) for s in cv_scores],
        "val_metrics": val_metrics,
        "test_metrics": test_metrics,
        "thresholds": {
            "confidence_threshold": classifier.confidence_threshold,
            "clarification_threshold": classifier.clarification_threshold,
        },
        "calibrated": classifier.calibrate_probabilities,
        "calibration_method": classifier.calibration_method if classifier.calibrate_probabilities else None,
    }


def main() -> int:
    print("=" * 60)
    print("NexusAI Intent Classifier Training & Comparison")
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

    # Check near-duplicates
    from nexusai.ml.dataset import check_near_duplicates
    near_dupes = check_near_duplicates(df, threshold=0.85)
    if near_dupes:
        print(f"   WARNING: {len(near_dupes)} near-duplicate pairs found (similarity >= 0.85)!")
        for i, j, sim in near_dupes[:10]:
            print(f"  {sim:.3f}: [{i}] {df.iloc[i]['text'][:60]}... | [{j}] {df.iloc[j]['text'][:60]}...")
    else:
        print("   No near-duplicates found (similarity >= 0.85).")

    # Split dataset (train/val/test) using stratified 3-way split
    print("\n2. Splitting dataset (train/val/test)...")
    train_val, test = train_test_split(
        df,
        test_size=0.2,
        stratify=df["intent"],
        random_state=42,
    )
    train, val = train_test_split(
        train_val,
        test_size=0.25,  # 0.25 of 0.8 = 0.2
        stratify=train_val["intent"],
        random_state=42,
    )
    print(f"   Train: {len(train)}, Val: {len(val)}, Test: {len(test)}")

    # Save splits
    print("\n3. Saving dataset splits...")
    dataset_dir = ROOT / "experiments" / "datasets" / "intent_classification"
    dataset_dir.mkdir(parents=True, exist_ok=True)

    train.to_json(dataset_dir / "train.json", orient="records", indent=2)
    val.to_json(dataset_dir / "val.json", orient="records", indent=2)
    test.to_json(dataset_dir / "test.json", orient="records", indent=2)
    df.to_json(dataset_dir / "full.json", orient="records", indent=2)
    print(f"   Saved to {dataset_dir}")

    # Prepare data
    train_texts = train["text"].tolist()
    train_labels = train["intent"].tolist()
    val_texts = val["text"].tolist()
    val_labels = val["intent"].tolist()
    test_texts = test["text"].tolist()
    test_labels = test["intent"].tolist()

    # Train and compare models
    print("\n4. Training and comparing models...")
    models = [
        ("LogisticRegression (calibrated)", IntentClassifier(
            model_type=ModelType.LOGISTIC_REGRESSION,
            calibrate_probabilities=True,
            calibration_method="sigmoid",
            cv_folds=3,
        )),
        ("LinearSVC (calibrated)", IntentClassifier(
            model_type=ModelType.LINEAR_SVC,
            calibrate_probabilities=True,
            calibration_method="sigmoid",
            cv_folds=3,
        )),
        ("LogisticRegression (uncalibrated)", IntentClassifier(
            model_type=ModelType.LOGISTIC_REGRESSION,
            calibrate_probabilities=False,
        )),
    ]

    results = {}
    for name, clf in models:
        print(f"\n   Training {name}...")
        result = evaluate_model(clf, train["text"].tolist(), train["intent"].tolist(),
                                val["text"].tolist(), val["intent"].tolist(),
                                test["text"].tolist(), test["intent"].tolist())
        results[name] = result
        print(f"     Val macro F1: {result['val_metrics']['macro_f1']:.4f}")
        print(f"     Test macro F1: {result['test_metrics']['macro_f1']:.4f}")
        print(f"     CV macro F1: {result['cv_macro_f1_mean']:.4f} (+/- {result['cv_macro_f1_std']:.4f})")
        print(f"     Thresholds: conf={result['thresholds']['confidence_threshold']:.4f}, clar={result['thresholds']['clarification_threshold']:.4f}")

    # Select best model based on validation macro F1
    best_name = max(results.keys(), key=lambda k: results[k]["val_metrics"]["macro_f1"])
    best_result = results[best_name]
    best_model_type = ModelType.LOGISTIC_REGRESSION if "LogisticRegression" in best_name else ModelType.LINEAR_SVC
    is_calibrated = "calibrated" in best_name.lower()

    print(f"\n5. Best model: {best_name}")
    print(f"   Validation macro F1: {best_result['val_metrics']['macro_f1']:.4f}")
    print(f"   Test macro F1: {best_result['test_metrics']['macro_f1']:.4f}")

    # Train final best model on train+val combined
    print("\n6. Training final model on train+val combined...")
    final_classifier = IntentClassifier(
        model_type=best_model_type,
        calibrate_probabilities=is_calibrated,
        calibration_method="sigmoid",
        cv_folds=3,
    )
    train_val_texts = train["text"].tolist() + val["text"].tolist()
    train_val_labels = train["intent"].tolist() + val["intent"].tolist()
    final_metadata = final_classifier.train(train_val_texts, train_val_labels)

    # Final evaluation on test set
    test_metrics = final_classifier._evaluate(test["text"].tolist(), test["intent"].tolist())
    print(f"\n   Final test accuracy: {test_metrics['accuracy']:.4f}")
    print(f"   Final test macro F1: {test_metrics['macro_f1']:.4f}")
    print(f"   Final thresholds: conf={final_classifier.confidence_threshold:.4f}, clar={final_classifier.clarification_threshold:.4f}")

    # Print per-class test metrics
    print("\n   Per-class test metrics:")
    for cls, metrics in test_metrics["per_class"].items():
        print(f"     {cls}: P={metrics['precision']:.3f} R={metrics['recall']:.3f} F1={metrics['f1']:.3f} (support={metrics['support']})")

    print("\n   Confusion matrix:")
    print(f"     Labels: {test_metrics['confusion_matrix_labels']}")
    for i, row in enumerate(test_metrics["confusion_matrix"]):
        print(f"     {test_metrics['confusion_matrix_labels'][i]}: {row}")

    # Save final model
    print("\n8. Saving final model artifacts...")
    final_classifier.save()
    print("   Model saved to nexusai/ml/models/")

    # Save evaluation results
    print("\n9. Saving evaluation results...")
    results_dir = ROOT / "experiments" / "results" / "intent_classification"
    results_dir.mkdir(parents=True, exist_ok=True)

    final_results = {
        "model_comparison": results,
        "best_model": best_name,
        "final_model": {
            "model_type": best_model_type.value,
            "calibrated": is_calibrated,
            "calibration_method": "sigmoid",
            "train_val_size": len(train["text"].tolist()) + len(val["text"].tolist()),
            "test_metrics": test_metrics,
            "final_metadata": final_metadata,
            "thresholds": {
                "confidence_threshold": final_classifier.confidence_threshold,
                "clarification_threshold": final_classifier.clarification_threshold,
            },
        },
        "dataset_info": {
            "total_examples": len(df),
            "train_size": len(train),
            "val_size": len(val),
            "test_size": len(test),
            "class_distribution": df["intent"].value_counts().to_dict(),
        },
    }

    (results_dir / "evaluation.json").write_text(json.dumps(final_results, indent=2))
    print(f"   Results saved to {results_dir}/evaluation.json")

    print("\n" + "=" * 60)
    print("Training complete!")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path
    from sklearn.model_selection import train_test_split
    from nexusai.ml.classifier import IntentClassifier, ModelType
    from nexusai.ml.dataset import build_dataset

    sys.exit(main())