# NexusAI

**Working title:** NexusAI: AI-Powered Personal Task Automation  
**Status:** Phase 0 — research foundation (no application code yet)  
**MSc Data Science project**  
**Second Review:** 23–25 October 2026

## What NexusAI is

NexusAI is an AI-powered personal task automation platform that transforms natural-language goals into structured, executable, verifiable, and adaptive workflows. It interprets user intentions, decomposes complex goals into smaller tasks, identifies suitable tools, executes approved operations, verifies outcomes, recovers from failures, and produces a transparent execution report.

## Research question

> "Can an AI-driven workflow engine autonomously decompose, execute, verify and adapt multi-step everyday tasks using heterogeneous real-time information?"

This is treated as a hypothesis to investigate, not a conclusion to assume.

## Research objectives

| ID | Objective |
|----|-----------|
| O1 | Interpret natural-language user goals and classify task intent. |
| O2 | Decompose goals into executable, dependency-aware steps. |
| O3 | Integrate RAG over user-provided documents. |
| O4 | Secure tool execution with registered tools and validated inputs. |
| O5 | Execution verification, bounded retries, failure handling, adaptive replanning. |
| O6 | Evaluate with measurable metrics (completion, planning quality, tool-selection accuracy, verification accuracy, recovery effectiveness, evidence accuracy, execution time). |

## Technical constraints (non-negotiable)

- Python-only application implementation (Python 3.11+).
- No Java, JavaScript, TypeScript, React, or Node.js.
- Open-source and local-first architecture.
- No mandatory paid API, paid database, or AWS dependency.
- Development via Claude Code through the existing FCC configuration.
- FCC configuration, provider routing, model aliases, and credentials are not modified.
- Optional local LLM integration is hardware-aware.
- No fabricated literature, citations, experimental results, or evaluation metrics.

## Repository structure

```
docs/
  research/          problem statement, questions, hypothesis, literature review,
                     literature matrix, research gap, methodology, experimental design,
                     evaluation metrics, data collection plan
  architecture/      system overview, architecture decisions
  project_management/
    seven_day_implementation_plan.md
    objective_traceability_matrix.md
    daily_checkpoints/   per-day checkpoint reports
experiments/         (gitignored) scenarios, corpus, traces, labels, results
src/                 (planned) application source
README.md
CLAUDE.md
.gitignore
```

## Current state

Phase 0 documentation is complete. No application code has been written. The next step is review of this research foundation, then Phase 1 implementation per `docs/project_management/seven_day_implementation_plan.md`.

## License

To be determined (open-source, per project constraints).

---

*Academic project — accuracy, research quality, and technical consistency are prioritised over volume of output.*