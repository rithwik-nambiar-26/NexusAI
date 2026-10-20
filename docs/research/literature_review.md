# Literature Review

**Project:** NexusAI  
**Document status:** Draft v0.1 — Phase 0 research foundation  
**Date:** 2026-10-20

## 0. Verification status — read before citing

This review is a **structured candidate reading list with a synthesis framework**, not a completed, verified citation set.

- Every entry in `literature_matrix.md` carries the status `REQUIRES EXTERNAL VERIFICATION`.
- Bibliographic fields (authors, year, venue, DOI/URL) and the "Findings" summaries below are **provisional working characterisations** based on general knowledge of the work. They must be confirmed against the primary source before being used in the final submitted report.
- **No quantitative result, dataset statistic, or citation is asserted here as fact.** Where a finding is described, it is described qualitatively and without invented numbers.
- The purpose of listing a work here is to define the theoretical backdrop NexusAI is positioned against, and to identify the research gap. Final submission requires verified references with confirmed DOIs.

**Verification protocol (Phase 1):** for each candidate work, record the confirmed title, author list, year, venue, DOI, and the exact quoted finding with page/section reference, in the final matrix. Any entry that cannot be verified within Phase 1 is removed rather than retained with uncertainty.

## 1. Scope of the review

The review covers five intersecting bodies of work that constitute the theoretical background of NexusAI:

1. **Retrieval-augmented generation and knowledge grounding** — supplying factual, corpus-specific information to a generative model.
2. **LLM-based agents and tool use** — the modern paradigm for LLM planning, acting, and iterative task execution.
3. **Classical planning and hierarchical task networks** — the structured decomposition discipline that predates LLMs and underpins rigorous plan representations.
4. **Natural language understanding for intent classification** — the ML component used for stable, low-latency intent routing.
5. **Evaluation methodology for LLM systems and agentic reliability** — how capability and reliability should be measured, including known pitfalls of LLM-as-judge and of unreproducible agent benchmarks.

## 2. Retrieval-augmented generation (RAG)

**Established knowledge.** Retrieval-augmented generation introduced the pattern of conditioning a parametric language model on non-parametric evidence retrieved at inference time. Lewis et al. (2020) frame this as combining parametric and non-parametric memory, and report improvements over parametric-only models on knowledge-intensive NLP tasks including open-domain question answering. The architectural pattern — index a corpus, retrieve candidate passages for a query, condition generation on the retrieved passages — is now the dominant approach to grounding generative output in a private or domain-specific corpus.

Subsequent work has addressed key sub-problems: chunking and passage granularity, dense versus sparse retrieval encoders, the "lost in the middle" positional effect whereby relevant information placed at the beginning or end of a long context is used more reliably than in the middle, and the phenomenon of retrieval-robustness degradation where model behaviour changes materially with small perturbations in retrieved context. Survey work (Gao et al., 2023) documents the breadth of the RAG design space across retrieval, augmentation, and generation stages.

**Relevance to NexusAI.** RAG is the mechanism by which NexusAI grounds plan steps in the user's own documents (Objective O3). Because NexusAI's evaluation includes an *evidence accuracy* metric, the RAG component must produce traceable passages whose content supports the step's claim — this connects RAG quality directly to a measured outcome rather than to a qualitative impression.

**Limitation recognised in the literature.** RAG improves factuality of *grounded* claims but does not by itself guarantee that a multi-step plan is coherent, that a retrieved passage is relevant to the step's *intent* rather than keyword-overlap, or that a tool invocation is safe. NexusAI therefore treats RAG as one component in a wider hybrid architecture.

## 3. LLM-based agents, planning, and tool use

**Established knowledge.** The LLM agent literature has converged on a common loop: observe, reason/plan, act, observe the result, repeat. Yao et al. (2022) formalise this as interleaving reasoning traces with task actions so that reasoning informs action selection and action results update reasoning. Shinn et al. (2023, ReWOO) show that decoupling reasoning from observation by planning all steps up front improves token efficiency for modular tasks. Shinn et al. (2022, Reflexion) introduce verbal self-reflection as a learning signal in which an agent critiques its own output and uses the critique on a subsequent attempt, forming a bounded-retry mechanism without weight updates. Karpas et al. (2022, MRKL) and Ahn et al. (2022, PAL) demonstrate complementary modular decompositions: the former routes between a language model and specialised modules (tools, search), the latter offloads computation to a program that the language model writes and an interpreter executes.

Tool-learning work (Schick et al., 2023, Toolformer) explores whether a language model can learn *when and how* to call external APIs with self-supervision from the API call log. Contemporary tool-use benchmarks and agent suites (e.g. ToolBench/ToolLLM, WebShop, ALFWorld, AgentBench) provide standardised task environments for comparing agent configurations, and SWE-bench extends evaluation to realistic software-engineering tasks with hidden test-based verification.

**Surveys.** Wang et al. (2023) and Wang et al. (2024) survey LLM-based autonomous agents along memory, planning, action/tool use, and reflection dimensions — the same four dimensions that structure NexusAI's architecture.

**Relevance to NexusAI.** These works define the *capability ceiling* and the *known failure modes* of the LLM-only condition. Specifically, they motivate the hybrid additions: independent verification (rather than self-reported success), input validation before invocation, and bounded structured replanning.

**Limitations recognised in the literature.** Reported agent results are frequently non-reproducible because benchmark environments, tool implementations, prompt wording, and model versions change; prompt sensitivity is well documented; and self-reported success is not independent verification. These limitations are directly relevant to NexusAI's evaluation design (controlled conditions, repeated trials, verification separated from planning) and to the review criteria for "Analysis and Interpretation".

## 4. Classical planning and hierarchical task networks

**Established knowledge.** Classical AI planning represents a task as a set of states, actions with preconditions and effects, and a plan as an action sequence. Hierarchical task network (HTN) planning (Erol, Hendler & Nau, 1994; Nau et al., 2016, SHOP2) extends this with *methods* — domain knowledge for decomposing a compound task into ordered sub-tasks and constraints — enabling partial-order, reusable task hierarchies rather than flat state-space search. A standard HTN structure carries compound and primitive tasks, method applicability preconditions, and ordering constraints (e.g. `before`, `partially-ordered`), which maps naturally onto a dependency graph of executable steps.

**Relevance to NexusAI.** The structured planning mechanism (Objective O2) does not need to reinvent this discipline. Adopting an explicit plan schema with typed steps, declared dependencies, preconditions, and expected outcomes gives NexusAI three advantages over free-form chain-of-thought: (i) an executable, inspectable representation; (ii) an explicit basis for topological scheduling; and (iii) a natural target for a *verification* module, because each step can declare the expected outcome against which its actual outcome is checked. The literature also makes clear that decomposition quality is a distinct, measurable property from execution success — supporting the separation of "planning quality" and "task completion" as independent dependent variables.

**Limitations recognised in the literature.** Classical planners require a complete, correct domain model; they degrade when the task space is open-ended and the method repertoire is incomplete. NexusAI's position is complementary: a learned/LLM-generated plan is validated against a declared schema and against a registered tool inventory, with classical techniques applied where the problem is fully specified.

## 5. Intent classification

**Established knowledge.** Intent classification is a supervised classification problem mapping an utterance to a label from a fixed taxonomy, and it is a well-established component of task-oriented dialogue systems. It is distinct from generative intent detection, and it is typically evaluated with accuracy, precision, recall, macro-F1, and confusion matrices. Standard linear models over bag-of-words features are strong baselines when the label set is small and the domain is narrow; transformer encoders (e.g. BERT) improve accuracy on larger or noisier taxonomies. Distribution shift — where training intents do not match deployment traffic — is a recognised failure mode for classifiers that are not retrained or adapted.

**Relevance to NexusAI.** Objective O1 is satisfied by a hybrid intent-routing stage: a lightweight classifier provides a fast, deterministic, inspectable intent signal, while the LLM handles generalisation beyond the closed taxonomy. A closed-set classifier also gives a natural place to enforce a *safety gate*: intents outside the permitted set are refused or escalated to a human-approval path rather than silently executed.

**Limitations recognised in the literature.** Classifier accuracy is not task success. It is one stage of a pipeline whose end-to-end behaviour is what the research question concerns, which is why intent-classification accuracy is measured as a component metric while task completion is measured as a system metric.

## 6. Evaluation methodology and known pitfalls

**Established knowledge.** Evaluating LLM systems is difficult because outputs are open-ended, and the field has converged on several practices with known weaknesses. Zheng et al. (2023) introduced MT-Bench and Chatbot Arena and formalised LLM-as-a-judge: using a stronger model to score outputs against rubrics, validated by agreement with human preference. The approach is scalable and correlates with human judgement, but it inherits the judge's biases, is sensitive to rubric wording, exhibits position bias in pairwise settings, and can favour verbosity. For code, Chen et al. (2023) introduced HumanEval with executable test-based verification, establishing functional correctness as the more reliable criterion. Datasets for retrieval and multi-hop reasoning — Natural Questions (Kwiatkowski et al., 2019), HotpotQA (Yang et al., 2018), MS MARCO (Bajaj et al., 2016), and the BEIR benchmark suite (Thakur et al., 2021) — provide standardised evaluation for retrieval quality and answer support. Echoing Shinn et al. (2023), agent benchmarks are vulnerable to saturation and to task contamination.

**Relevance to NexusAI.** The central methodological commitment of NexusAI is that *verification must be independent of planning* — a checker that inspects the world state or the tool output against a declared criterion, rather than the planner's own report of success. This follows the functional-correctness lesson of test-based evaluation and avoids the circularity of self-assessment. Where subjective assessment is unavoidable (e.g. plan *quality* or narrative report quality), a hybrid rubric-based judge is used, with a human-agreement sub-study reported so that the judge itself is validated rather than assumed.

**Limititation recognised in the literature.** No single metric captures agent reliability, and each carries gaming risk. NexusAI therefore reports a *set* of complementary metrics with pre-specified aggregation and pre-registered analysis, and explicitly notes metric gaming as a threat to validity.

## 7. Applied context: AI assistants in knowledge work

**Established knowledge.** Field studies of generative AI in workplace settings report large but heterogeneous productivity effects, with the pattern of gains concentrated in lower-experience workers and in tasks inside the frontier of model capability. Brynjolfsson, Li & Raymond (2023) report empirical evidence of generative AI improving customer-support worker productivity, with the largest gains for the least-experienced workers. Dell'Acqua et al. (2023) report that a GPT-4-based assistant improved task quality and speed for within-frontier professional tasks while *reducing* performance on tasks beyond the frontier — a documented, important asymmetry that motivates explicit capability-boundary detection in agent design.

**Relevance to NexusAI.** This literature motivates the design principle that the system must *know when it is outside its competence* — hence verification, approval gates, and an explicit "infeasible" outcome distinct from "failed". It also provides a defensible applied motivation for the project beyond academic curiosity.

**Limitations recognised.** Productivity studies measure human–AI collaboration, not autonomous workflow reliability, and their findings are context-specific; they are used here as *motivation*, not as evidence for NexusAI's technical claims.

## 8. Summary of theoretical positioning

| Dimension | Classical planning | LLM agents | RAG | NexusAI's position |
|-----------|-------------------|------------|-----|---------------------|
| Goal interpretation | Symbolically specified | Natural language | — | Natural language in, with an explicit structured plan out |
| Plan representation | Formal, validated | Often free-form text | — | Typed step schema with declared dependencies and expected outcomes |
| Knowledge source | Model-encoded | Model-encoded | Retrieved corpus | Retrieved user corpus, with cited evidence per step |
| Execution | Symbolic operators | Tool calls, often unvalidated | — | Registered tools, schema-validated inputs, approval gates |
| Outcome checking | Precondition/effect checks | Self-reported success | — | Independent criterion-based verification, separate from the planner |
| Failure handling | Replanning via search | Unstructured retry loops | — | Bounded retries with adaptive replanning and a budget |
| Auditing | Trace by construction | Frequently opaque | — | Execution report as a first-class output |

## 9. Gaps identified from the review

The synthesis above points to four gaps that NexusAI addresses — developed fully in `research_gap.md`.

## 10. Limitations of this review

- The review is currently a *candidate set with a synthesis structure*, not a verified reference list; verification is a Phase 1 deliverable.
- Coverage is intentionally focused on the five bodies of work above; areas such as prompt injection defence, formal methods for tool safety, and multi-agent coordination are noted but not yet covered in depth.
- Some adjacent literatures (agentic RL, tool-learning at scale, enterprise workflow engines) are referenced at survey level only.

---

**Traceability:** This review informs `research_gap.md`, the baseline definitions in `experimental_design.md` (conditions A and B are grounded in Sections 3 and 4 respectively), and the metric design in `evaluation_metrics.md` (Sections 5 and 6).