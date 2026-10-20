# Daily Checkpoints

**Project:** NexusAI  
**Document status:** Draft v0.1 — Phase 0 research foundation  
**Date:** 2026-10-20

## Purpose

One checkpoint file per implementation day (`day-1.md` … `day-7.md`). Each file records:
- What was completed that day.
- Which objectives were advanced.
- Metric results (preliminary) with evidence (file paths, test names, values).
- Blocker(s), if any, and the resolution or next step.
- Whether the day met its definition of done.

No checkpoint file exists yet; Phase 0 foundation must be reviewed and the checkpoint verified before Day 1 begins.

## Format (template for each day-N.md)

```markdown
# Day N checkpoint — <date>

## Completed
- ...

## Objectives advanced
- O1 / O2 / ...

## Metric results (preliminary)
| Metric | Value | Evidence |
|--------|-------|----------|
| ... | ... | ... |

## Blocker(s)
- ...

## Definition of done met?
- Yes / No — reason

## Git
- Commit hash: <hash>
- Working tree clean: Yes / No
```

## Review rule

Never mark a day complete without supporting evidence (committed code, passing tests, metric values). Checkpoints are the primary evidence for the Second Review's "Research Design / Project Plan" and "Data Collection Progress" criteria.
