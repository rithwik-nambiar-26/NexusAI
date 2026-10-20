# Research Gap

**Project:** NexusAI  
**Document status:** Draft v0.1 — Phase 0 research foundation  
**Date:** 2026-10-20

## 1. Purpose

This document synthesises the preceding review into a precise statement of the gap NexusAI addresses, and then translates that gap into a set of testable contributions. It follows directly from `literature_review.md` and `literature_matrix.md`, which remain provisional until verified against primary sources.

## 2. Gap statement

Existing personal productivity automation falls into two imperfect classes:

1. **Rule-based / symbolic workflow engines** (trigger→action, often partial-order): reliable, verifiable, and auditable within a narrow, pre-programmed scope, but unable to interpret open-ended natural-language goals, to decompose novel tasks, or to adapt when an intermediate outcome differs from expectation.

2. **Large-language-model (LLM) agents**: able to interpret natural language and to plan and act flexibly, but documented to fail in ways that matter for reliability: unvalidated tool invocation, self-reported success that is not independently verified, opaque execution traces, unbounded retry loops, and no clear boundary between feasible and infeasible tasks.

Classical planning (HTN, partial-order task networks) supplies rigorous decomposition formalisms but requires a complete, correct symbolic domain model, which does not exist for open-ended personal tasks. RAG supplies grounded, corpus-specific knowledge but does not by itself guarantee coherent multi-step plans or safe tool use. Intent classification supplies fast routing but is not task success. None of the surveyed works combines, in one auditable, local-first system:

- a **structured, typed plan schema** with declared dependencies and expected outcomes,
- **independent, criterion-based verification** separate from the planner,
- **bounded retries with adaptive replanning** and a finite budget,
- **schema-validated tool execution** with user approval gates, and
- **RAG-grounded step evidence** with traceable citations.

The gap is therefore architectural and methodological: a hybrid system that unifies symbolic planning discipline with LLM flexibility, where *verification is independent* and *failure recovery is bounded and adaptive*. NexusAI addresses this gap for personal, everyday multi-step tasks.

## 3. Contributions mapped to research objectives

Each contribution below maps to an objective (O1–O6), an application component, and an experiment. This is elaborated in `objective_traceability_matrix.md`.

| ID | Contribution | Objective | How it addresses the gap |
|----|--------------|-----------|--------------------------|
| C1 | Structured, typed plan schema with declared dependencies, preconditions, and expected outcomes per step | O2 | Replaces free-form chain-of-thought plans with an inspectable, dependency-aware representation |
| C2 | Independent criterion-based verification module, separate from the planner | O5 | Removes circular self-reported success; each step's actual outcome is checked against its declared expected outcome |
| C3 | Bounded retries with adaptive replanning and an explicit retry budget | O5 | Replaces unbounded retry loops with a finite, observable recovery budget |
| C4 | Registered tool set with input-schema validation and user approval gates | O4 | Prevents invalid or unsafe tool invocations before execution |
| C5 | RAG over a user-provided local corpus with cited evidence per step | O3 | Grounds step content in the user's own documents, with traceable passages |
| C6 | Hybrid intent routing: fast ML classifier plus LLM generalisation | O1 | Combines stable intent routing with LLM generalisation beyond a closed taxonomy |
| C7 | Controlled experiment comparing rule-based, LLM-only, and hybrid baselines under shared conditions | O6 | Provides measurable evidence for or against H₁ rather than assuming superiority |

## 4. Why this gap matters for the research question

The primary research question — *"Can an AI-driven workflow engine autonomously decompose, execute, verify and adapt multi-step everyday tasks using heterogeneous real-time information?"* — cannot be answered affirmatively merely by demonstrating that an LLM can generate plans. It requires evidence that the *verify* and *adapt* components materially affect reliability. The gap is precisely that this combination has not been measured under controlled conditions for the personal-task domain.

## 5. Limitations recognised

- NexusAI is a single MSc-scale implementation; it cannot establish general reliability across all task domains.
- The evaluation is bounded to the implemented toolset, document corpus, and chosen LLM(s); results do not generalise beyond those conditions.
- Verification is criterion-based and heuristic; it provides evidence, not formal proof.
- Contributions C1–C7 are claims about *design*, not results. Their evidentiary status is established only by the experiments in `experimental_design.md`, evaluated against `evaluation_metrics.md`.

---

**Traceability:** Gap contributions map to objectives O1–O6, to experimental conditions A/B/C in `experimental_design.md`, and to metrics in `evaluation_metrics.md`.