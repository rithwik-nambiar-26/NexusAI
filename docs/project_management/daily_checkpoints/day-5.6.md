# NexusAI — Research Checkpoint: Classifier Model Selection and Training Set

**Status:** planned — not started
**Scope:** O1 (intent classification), and the model-selection defect recorded in
`docs/review/KNOWN_LIMITATIONS.md` §1.4

This checkpoint is separate from the reminder capability on purpose. The
capability is implemented and tested; what is not implemented is a classifier
that is good enough to route requests to it. The two are kept apart so that
the capability is never presented as better than the evidence supports.

---

## 1. The defect to fix

`nexusai/ml/train.py` selects the best variant on validation macro F1, then
decides whether to calibrate it with:

```python
is_calibrated = "calibrated" in best_name.lower()
```

The winning variant is `LogisticRegression (uncalibrated)`. The substring
`"calibrated"` appears in `"uncalibrated"`, so the test is true for the
*uncalibrated* winner, and the shipped model is sigmoid-calibrated even
though calibration lost on validation:

| Variant | Validation macro F1 | Test macro F1 |
|---------|--------------------:|--------------:|
| LogisticRegression (uncalibrated) | **0.6385** | 0.4417 |
| LogisticRegression (calibrated) | 0.4306 | 0.5000 |
| LinearSVC (calibrated) | 0.3788 | 0.5139 |

**Why it matters.** Sigmoid calibration over a 12-class problem compresses the
predicted probabilities towards the base rate. That is why a genuine document
request scores around 0.24–0.45 rather than higher, and why the operating
point (0.55 confident, 0.35 clarification) sits where it does. The shipped
model and the reported comparison disagree about which model is best, and the
comparison is the one with evidence behind it.

**The fix** is to decide calibration on the evidence — the same way the
variant is chosen — rather than by a substring test. Then re-measure.

**This changes the shipped model and every reported metric.** That is why it
is a research checkpoint and not a bug-fix commit: the numbers in
`docs/research/`, `KNOWN_LIMITATIONS.md` §1.3 and the Day-2 checkpoints all
describe the model that ships, and they must all be re-derived from one
recorded run.

## 2. The training set to expand

The set is 75 examples over 12 classes:

| Class | Examples | Class | Examples |
|-------|---------:|-------|---------:|
| `document_question_answering` | 12 | `document_extraction` | 6 |
| `document_summarisation` | 8 | `communication` | 6 |
| `data_analysis` | 8 | `document_transformation` | 5 |
| `research` | 7 | `out_of_scope` | 5 |
| `invalid` | 7 | `destructive_operation` | 4 |
| `channel_unavailable` | 3 | `infeasible` | 4 |

Three classes have four or fewer examples, and the per-class F1 of
`data_analysis`, `destructive_operation` and `infeasible` is 0.00 on the
held-out set. The four `document_*` classes are mutually confusable: for
"Summarise the uploaded meeting notes and identify the important decisions"
the shipped model scores `document_summarisation` 0.240,
`document_transformation` 0.160 and `document_question_answering` 0.158.

**What expansion means here.** More examples per class, more paraphrase
diversity within a class, and coverage of the `reminder` category so the
classifier can route to the capability it was built alongside. The point is
not a higher headline number. It is that the classifier should be able to
separate the four document classes, and that the *refusal* classes should be
reliably detected rather than being detected by luck.

**The rule that applies.** Examples are added to fix a specific,
identified confusion — a class the model cannot separate, or a phrasing it
misses — and each addition is recorded with the reason for it. Examples are
never added to raise the accuracy figure. If a class is not learnable from
75 examples, that is a finding to report, not a gap to paper over.

## 3. What the checkpoint must produce

1. **A corrected model-selection step**, decided on the validation
   evidence, with the comparison re-run and recorded in
   `experiments/results/intent_classification/evaluation.json`.
2. **A re-trained model** on the expanded set, with the held-out split
   re-drawn and reported.
3. **Recorded metrics** — accuracy, macro F1, per-class F1 with support
   counts, and cross-validated macro F1 — all from that one run, written
   into `KNOWN_LIMITATIONS.md` §1.3, `IMPLEMENTATION_VS_OBJECTIVES.md` and
   the Day-2 checkpoint addendum.
4. **The thresholds re-tuned** on the new validation split, and the
   operating point re-examined against the *separation* between classes
   rather than against the absolute probability alone.
5. **A statement of what did not improve.** A larger set that does not
   separate the document classes is a result, and it is reported as one.
6. **The `reminder` category covered**, so the intent can be reached by
   classification rather than only by an explicit selection.

## 4. What must not change

- The confirmation flow, the planner, the executor and the reminder
  capability are not touched by this checkpoint. They are not what is
  being studied.
- The safety policy does not depend on the classifier's confidence, and
  must not start depending on it. A better classifier changes *how often*
  a user is asked to confirm, not *whether* a destructive request is
  refused.
- The literature matrix entries stay marked `REQUIRES EXTERNAL
  VERIFICATION` until each is checked against its primary source. A better
  classifier is not a literature result.

## 5. Order of work

1. Fix the model-selection step; re-run the comparison; record it.
2. Report the metrics of the corrected selection *before* expanding
   anything, so the effect of the fix is separable from the effect of the
   larger set.
3. Expand the set, class by class, recording the reason for each addition.
4. Re-train, re-measure, re-tune the thresholds.
5. Re-derive every number in the documentation from that one run.
6. Re-test the manual scenarios, because a better classifier changes which
   requests reach the confirmation flow.
