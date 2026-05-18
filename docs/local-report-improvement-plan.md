# Local vs cloud AI report — improvement plan

This document closes the quality gap between **local** reports (e.g. LM Studio + Gemma-class models) and **cloud** reports (e.g. Gemini 2.5 Flash). It maps to this codebase: `backend/llm/prompts.py` (`SYSTEM_PROMPT_LOCAL`, `build_analysis_prompt`), and DOCX export in `backend/llm/endpoints.py` (Markdown → Word).

---

## Goal

Improve **local** report quality **without requiring a cloud model**, by addressing:

1. **Grounding and counts** — cloud outputs cited occurrence totals and verbatim log lines more reliably.
2. **Report schema** — cloud used structured **Evidence → Interpretation → Recommendations** and richer sections.
3. **Domain knobs** — cloud named concrete settings (e.g. ODBC/Replicate timeouts).
4. **Word fidelity** — pipe-style Markdown tables became plain paragraphs in DOCX because export did not parse tables.

---

## Phase 1 — Deterministic evidence layer (highest ROI)

**Problem:** Larger / cloud models looked “smarter” partly because prompts contained **stronger structured facts**. Small local models amplify weak context.

**Actions:**

1. **Log aggregates block** — Inject early in the user prompt (inside `build_analysis_prompt` in `prompts.py`):
   - Per-pattern counts for top *N* error/warning strings (exact or normalized).
   - First and last **line number + timestamp** per pattern.
   - Distinct Qlik internal codes (e.g. `[1022502]`) with counts.
   - Optional: component histogram (`SOURCE_UNLOAD`, `TASK_MANAGER`, etc.).

2. **Representative verbatim lines** — For each top pattern, include **full** log lines (component tags, messages), not overly truncated excerpts.

3. **Invariant text** — State explicitly that occurrence counts are **computed from the full log** and the model **must not contradict** them.

**Success metric:** Local reports include **numbers** that match `grep` or your indexer; fewer vague phrases (“several”, “multiple”) without counts.

---

## Phase 2 — Align local report schema with cloud

**Problem:** `SYSTEM_PROMPT_LOCAL` currently ends with Issues & Recommendations and a categorical Health Score. Cloud-style reports added **Error Code Reference**, **structured issues**, and **numeric health**.

**Actions:**

1. Extend **`SYSTEM_PROMPT_LOCAL`** (keep it compact — bullets, not long prose):
   - **Key Findings:** bullets must **lead with counts** copied from the aggregates block where provided.
   - **Issues & Recommendations:** per major issue use **Evidence**, **Interpretation**, **Recommendations** subsections.
   - **Error Code Reference:** short bullets for codes present in aggregates/excerpts.
   - **Health Score:** **X/5** plus **one sentence justification**.

2. Optional: instruct the model to **quote at least one `LINE …` log line per major finding**.

**Success metric:** Side-by-side outline similarity to cloud reports ≥80% (same major sections and structure).

---

## Phase 3 — Product-specific tuning hints (KB-light)

**Problem:** Concrete parameter names (e.g. `executeTimeout`, `cdcTimeout`) come from **domain context**, not model size.

**Actions:**

1. Add a short **static “Replicate tuning cheat sheet”** (roughly 100–300 tokens), appended when prompts indicate ODBC / `SOURCE_UNLOAD` / timeouts / SAP ASE — or when relevant codes appear via `extract_error_codes_for_prompt`.

2. Longer-term: surface **one** KB paragraph per top error family using existing KB / vector-store flows.

**Success metric:** Local recommendations name **specific settings** where cloud does, without inventing values outside the cheat sheet / KB.

---

## Phase 4 — DOCX export quality

**Problem:** Export walks lines line-by-line; Markdown **tables** (`| col |`) become plain paragraphs, so reports look worse than the Markdown UI.

**Actions:**

1. Detect GitHub-style tables (header row + delimiter row); render **`python-docx` `Table`** with a bold header row.

2. Fix **numbered lists**: avoid only recognizing lines starting with `1.`–`3.`; support arbitrary `N.`.

3. Optional: render fenced code blocks as monospace paragraphs instead of skipping only fence lines.

**Success metric:** Exported DOCX tables are readable; lists numbered past `3.` render correctly.

---

## Phase 5 — Context budget and retrieval (large logs)

**Problem:** If excerpts are capped, local models miss events unless retrieval prioritizes the right passages.

**Actions:**

1. Ensure chunking / retrieval includes **top errors by count** and **recent tail** events.

2. **Advanced:** Two-pass flow — Pass 1 extracts structured facts (JSON); Pass 2 writes prose from facts + short excerpts (reduces hallucination).

**Success metric:** Rare but critical lines appear in Evidence sections at rates comparable to cloud on large files.

---

## Phase 6 — Model and infra (optional)

- Evaluate a **larger local instruct** model with the same pipeline.
- When trimming prompts for token limits, **do not drop** the Phase 1 aggregates block unless unavoidable.

---

## Recommended implementation order

| Order | Phase | Typical effort | Expected impact |
|-------|--------|----------------|-----------------|
| 1 | Phase 1 — aggregates + verbatim lines | Medium | Very high |
| 2 | Phase 2 — local prompt schema | Low | High |
| 3 | Phase 4 — DOCX tables / lists | Medium | High (perceived quality) |
| 4 | Phase 3 — tuning cheat sheet | Low | Medium–high |
| 5 | Phase 5 — retrieval / two-pass | Higher | Large logs |

---

## Definition of done (“half as good as cloud”)

Use a short checklist per report:

- [ ] At least one primary error pattern shows a **count** that matches tooling.
- [ ] **Two or more** full log lines quoted with **LINE** numbers under Issues/Evidence.
- [ ] At least one **named** configuration knob from cheat sheet/KB where applicable.
- [ ] **Health Score** is **numeric (X/5)** with a **one-sentence** justification.
- [ ] DOCX export shows **proper tables** where the Markdown used tables.

---

## Related files

- `backend/llm/prompts.py` — system prompts, `build_analysis_prompt`
- `backend/llm/endpoints.py` — `export_report_docx` / Markdown → DOCX
- `docs/LLM_PROMPT_PIPELINE.md` — broader prompt pipeline reference
