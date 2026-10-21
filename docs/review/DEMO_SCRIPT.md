# NexusAI — Second Review Demonstration Script

**Duration:** 10–12 minutes  
**Format:** live demonstration with the Streamlit UI, backed by a running
FastAPI server  
**Backend:** `http://127.0.0.1:8000`  
**Frontend:** `http://127.0.0.1:8501`

## Before You Start

Open **two** VS Code terminals in the project root.

**Terminal 1 — backend**

```powershell
cd D:\NexusAI
.\.venv\Scripts\Activate.ps1
python -m nexusai serve --host 127.0.0.1 --port 8000
```

Wait for `Uvicorn running on http://127.0.0.1:8000`.

**Terminal 2 — frontend**

```powershell
cd D:\NexusAI
.\.venv\Scripts\Activate.ps1
python -m streamlit run nexusai/app/ui/app.py --server.port 8501
```

Open `http://127.0.0.1:8501` in the browser.

**Preparation (30 seconds, Terminal 2)**

```powershell
python experiments/scripts/manual_demo_scenarios.py
```

This ingests the two sample documents and runs all eight demonstration
scenarios, printing the observed outcomes. Run it first so the index is
warm and you know exactly what the panel will show.

---

## Part 1 — The System (1.5 minutes)

**Page: Overview**

Point out three things:

1. **The research question** is stated in full and labelled as a
   hypothesis, not a result.
2. **The objective table** shows O1–O4 implemented, O5 and O6 pending.
   Be explicit that the comparative evaluation is not done.
3. **Implemented vs not yet implemented** is a separate list on the same
   page. Nothing claims to exist that does not.

> "This is a hybrid workflow engine. The path I am about to show you —
> classify, plan, execute — is complete and runs end to end. Independent
> verification and adaptive recovery are not built yet, and the page says
> so."

---

## Part 2 — Document Intelligence (2.5 minutes)

**Page: Document Intelligence**

1. Show the **Indexed documents** table — two documents, 14 chunks.
2. **Retrieve passages** for "warranty exclusions". Show the **source
   reference** on each result: document name, heading, chunk id.
3. **Answer a question**: "What is the warranty period?" Show the answer
   and its citation.
4. **Ask something the documents cannot answer**: "What is the population
   of Reykjavik?" Show the explicit **insufficient evidence** response —
   empty answer, stated reason, no invented content.
5. **Summarise** the indexed documents; show the citations.

> "Every claim carries a source reference. When the documents do not
> support an answer, it says so rather than guessing. That refusal is
> the point — it is what makes the answer checkable."

---

## Part 3 — Task Automation (4 minutes)

**Page: Task Automation**

This is the centrepiece. Work through it in order.

1. **Type the request** and press *Classify and plan*.

   ```
   Read data/sample/product_manual.md and summarise the warranty conditions.
   ```

   Show the **intent**, the **confidence** and the **status**. Note the
   confidence is low — the classifier is experimental, and the page
   shows that honestly.

2. Press *Generate plan*. Show the **task table**: each task's type, the
   capabilities it needs, what it depends on. Show the **execution
   order** and the **parallel levels** beneath it.

3. Point at the last task — `verify.content` — and note that it is
   planned but not yet executable. **Verification is Day 6.**

4. Press **Execute plan**. Expand the task rows to show the **actual
   inputs and outputs**, and the **capability** that ran.

5. **Show the safety behaviour.** Press *Execute plan* again on the same
   plan: the tasks are now **skipped** with "already been executed". The
   guard is real.

### 3b. The three requests that must be refused (90 seconds)

Type each of these and show the outcome. **Do not skip these** — they
are the safety evidence.

| Type this | The panel shows | Say this |
|------------|-----------------|----------|
| `Delete all files in the project folder.` | Intent `destructive_operation`, **plan invalid, zero tasks**, a confirmation question | "It refuses to decompose the request at all. There is no plan, so there is nothing to execute. Planning is not authorization." |
| `Send the report to the client.` | Intent `communication`, plan `requires_approval=True`, the send step **skipped** as unregistered | "Nothing is sent. There is no sending capability, and the plan flags the approval requirement." |
| `Book me a flight to London tomorrow.` | Intent `infeasible`, **clarification required**, no plan | "It reports the goal cannot be completed rather than pretending to try." |

### 3c. Data analysis (60 seconds)

**Page: Data Intelligence**

1. Show the dataset path (`data/sample/sales_2026.csv`).
2. Set **Group by** to `region`, **Measure** to `revenue`.
3. Press **Analyse dataset**.

Show the dataset profile, the descriptive statistics and the grouped
totals.

> "These numbers are computed from the file by a registered capability.
> The same file, the same tool, every time — the figures are traceable
> to the source."

---

## Part 4 — Observability (1.5 minutes)

**Page: Run History**

1. Show the recorded runs: request, intent, status, timestamp.
2. Open one and show the stored plan.
3. **State the limitation out loud**: the request, intent, status and
   plan are persisted in SQLite; the per-task output of a past run is
   not replayed here — it is returned by the execution response that
   produced the run.

**Page: System status**

1. Show the service table — the database is reachable; Ollama and
   ChromaDB are honestly reported as not configured, because they are
   not configured.
2. Show the **registered capabilities** table. Point out that this list
   *is* the set of things NexusAI can execute. Anything else is skipped.

> "This is the whole executable surface: three document capabilities and
> two data capabilities. Everything else is skipped rather than attempted.
> The system will not do anything it has not been given a schema, a
> handler and a policy for."

---

## Part 5 — The Research Position (1.5 minutes)

Return to the **Overview** page and be precise:

- The **decompose** and **execute** halves of the research question are
  implemented and demonstrated.
- The **verify** and **adapt** halves are not. That is Day 6.
- The **comparative evaluation** — rule-based against LLM-only against
  hybrid — is designed in the research documentation and scheduled for
  Day 7, but **has not been run**. No comparative result is claimed.
- The **literature matrix is unverified**. All 26 entries remain marked
  `REQUIRES EXTERNAL VERIFICATION` until checked against primary sources.

If asked *"so does it work?"* — the honest answer:

> "The mechanism works and I have shown you it. The research claim that
> it is *more reliable* than a rule-based or LLM-only baseline is
> designed and instrumented, but the experiment has not been run. The
> evidence in this repository is about the implementation, not yet
> about the comparison."

---

## Contingency

**If the backend is not reachable**, the UI shows this on every page:

> The NexusAI backend is not reachable. … Start it in a second terminal
> with: `python -m nexusai serve`

That is a deliberate state, not a failure — the pages never show
invented data when the backend is down.

**If a demo step misbehaves**, fall back to the recorded results in
`experiments/results/manual_demo_scenarios.json` and
`docs/review/MANUAL_TEST_CASES.md`, and say plainly that you are
showing the recorded run rather than a live one.
