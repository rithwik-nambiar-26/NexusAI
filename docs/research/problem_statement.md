# Problem Statement

**Project:** NexusAI  
**Working Title:** NexusAI: AI-Powered Personal Task Automation  
**Document status:** Draft v0.1 — Phase 0 research foundation  
**Date:** 2026-10-20

## 1. Problem

Everyday knowledge workers and individuals regularly pursue multi-step personal goals that span heterogeneous information sources and digital tools — for example, "plan a weekend trip within a budget," "research and compare three insurance options," or "compile a reading list on a topic and summarise the key papers." Current personal productivity tooling forces the user to manually perform each sub-step: decompose the goal, locate relevant information, choose and invoke tools, verify results, handle failures, and record outcomes. This manual decomposition and orchestration is error-prone, time-consuming, and places a high cognitive load on the user.

Existing automation approaches fall into two imperfect classes:

- **Rule-based workflow engines** (e.g. IFTTT-style triggers and actions): reliable and verifiable within a narrow, pre-programmed scope, but unable to interpret open-ended natural-language goals, decompose novel tasks, or adapt to unexpected outcomes.
- **Large-language-model (LLM)-only agents**: capable of goal interpretation and planning in natural language, but prone to hallucination, unvalidated tool invocation, unreliable failure recovery, and opaque execution traces that are difficult to audit or verify.

There is a gap for a **local-first, hybrid AI workflow engine** that can interpret natural-language goals, decompose them into structured, dependency-aware steps, retrieve relevant user-provided information, execute validated tools, independently verify outcomes, recover from bounded failures, and produce an auditable execution report — without depending on mandatory paid APIs, paid databases, or cloud infrastructure.

## 2. Problem statement (formal)

Given a natural-language user goal $G$ expressed in everyday language, and a registered toolset $T = \{t_1, \dots, t_n\}$ with validated input schemas, NexusAI must:

1. Interpret $G$ and classify its task intent.
2. Decompose $G$ into an ordered, dependency-aware set of executable steps $S = \{s_1, \dots, s_k\}$.
3. Retrieve relevant information from user-provided documents via retrieval-augmented generation (RAG).
4. Select and execute tools from $T$ with validated inputs, subject to user approval where required.
5. Verify each step outcome against an expected criterion; on failure, apply bounded retries and adaptive replanning.
6. Produce a transparent execution report evidencing each action, its inputs, outputs, and verification result.

The system must operate within an open-source, local-first architecture and must not require a mandatory paid API, paid database, or AWS dependency.

## 3. Research problem significance

Personal task automation sits at the intersection of natural language understanding, automated planning, information retrieval, and verified tool execution. Solving it reliably would reduce user cognitive load and expand the class of everyday tasks amenable to autonomous assistance. However, reliability — not merely capability — is the open research question: can a hybrid architecture demonstrably outperform simpler rule-based and LLM-only baselines on measurable task-automation metrics? NexusAI treats this as a hypothesis to investigate, not a conclusion to assume.

## 4. Scope and boundaries

### In scope

- Natural-language goal input and intent classification.
- Structured task planning and dependency-aware decomposition.
- RAG over user-provided documents (local corpus).
- Registered tool execution with input validation and user approval gates.
- Step verification, bounded retries, failure handling, and adaptive replanning.
- Auditable execution reporting.
- Local-first, open-source Python implementation; optional hardware-aware local LLM.

### Out of scope (Phase 0 / Phase 1)

- Multi-user collaboration or real-time shared workspaces.
- Mandatory cloud LLM APIs or paid SaaS dependencies (optional only, gated behind configuration).
- Mobile or web frontends beyond a minimal local interface.
- Safety-critical, medical, legal, or financial decision automation requiring regulated assurance.
- Training new foundation models from scratch.

## 5. Assumptions and limitations

**Assumptions:**

- Users can express goals in natural language and review/approve tool executions.
- Relevant documents are supplied by the user as a local corpus.
- A Python execution environment (3.11+) is available.
- Optional local LLM execution is bounded by available hardware (CPU/RAM/GPU).

**Limitations:**

- Reliability is bounded by the quality of the underlying LLM(s) and retrieval corpus.
- Verification is heuristic and criterion-based, not formal proof.
- Bounded replanning may not resolve fundamentally infeasible goals.
- The scope is achievable for an MSc Data Science project; industrial-grade reliability is not claimed.

---

**Traceability:** This problem statement underpins Research Question RQ1 (see `research_questions.md`) and Objectives O1–O6 (see `objectives_and_scope.md`).