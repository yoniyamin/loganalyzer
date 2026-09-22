# LLM prompt pipeline (reports & context)

This document describes the **Prompt Quality Pipeline** architecture: a deterministic evidence compiler followed by an LLM interpretation layer.

## Architectural principle

| Layer | Responsibility |
|-------|----------------|
| **Python** | Extraction, aggregation, calculation, ranking, budgeting, validation |
| **LLM** | Interpretation, explanation, prioritization only |

The model must **never** compute counts, percentages, deltas, or rankings. Numeric facts are pre-computed in Python and marked authoritative in the user payload.

## Where it runs

- **Orchestration:** `backend/llm/report_generator.py` (`ReportGenerator.generate_report`, `build_report_messages`)
- **Prompt contract:** `backend/llm/prompts.py` — unified 6-section output schema in the system prompt; user message is evidence only (no "Analysis Request" section)
- **Evidence compiler:** `backend/llm/evidence_compiler.py` — aggregates, authoritative facts, focus plans, hard budgets
- **Payload formats:** `backend/llm/payload_formats.py` — `markdown`, `json_markdown`, `xml` (Prompt Lab A/B/C)
- **Graph enrichment (gated):** `backend/llm/graph_enrichment.py` — SQLite adjacency graph via structural facts; opt-in via `include_graph`
- **Embedding fallback (gated):** `backend/llm/evidence_insufficiency.py` — log Chroma only when deterministic evidence is insufficient
- **Post-LLM:** `backend/llm/report_validator.py` (section/param checks + optional correction retry), `backend/llm/report_formatter.py` (markdown normalization)

## Pipeline flow

```
SQLite + parsers
  → evidence_compiler (facts, budgets, focus plan)
  → optional graph_enrichment (include_graph=true)
  → optional embedding fallback (insufficiency only)
  → payload_formats → build_report_messages
  → LLM
  → report_validator → report_formatter → save / display
```

## Provider behavior

| Aspect | Gemini / OpenRouter (cloud) | LM Studio / openai_api (local FLM) |
|--------|-----------------------------|-------------------------------------|
| System prompt | `AUDIT_REPORT_STRUCTURE` + evidence preamble; optional web-search variant | Same contract; `compact=True` tightens excerpt/KB caps |
| User message | Evidence package only — inventory, authoritative facts, excerpts, KB/RN when fetched | Same shape, smaller caps |
| Embeddings | **Not** run by default; only when `assess_evidence_insufficiency()` triggers fallback | Same |
| KB Chroma / Tavily | Retrieved when `fetch_external=true` (default on generate; off on prompt-preview) | Same |
| Graph | Injected only when `include_graph=true` and confidence match | Same |
| FLM reliability | N/A | `openai_api_client.py`: session warmup, 3 retries on empty choices; metrics in `flm_metrics.py` |

## Report message shape

1. **System message** — output contract (six `##` sections), focus addenda, rules (cite LINE refs, no invented numerics).

2. **User message** — built by `build_analysis_prompt` / evidence compiler, in order:
   - **Data Available** inventory
   - **Authoritative facts** (pre-computed counts, deltas, health signals)
   - **Performance & diagnostics** (when telemetry exists)
   - **Errors & warnings** (SQLite excerpts within merge cap; warnings from `severity=W` lines)
   - **Anomalies**, **release notes**, **KB** (when retrieved)
   - Optional **graph context** block when gated enrichment fires

There is **no** trailing "Analysis request" checklist — the system prompt defines the task.

Quick mode uses `build_quick_summary_prompt` (metrics JSON) instead of the full evidence package.

## Evidence insufficiency (Phase 7)

Embedding / log Chroma runs only when:

- Not quick mode, and
- Indexed error count exceeds deterministic excerpt budget, or
- Errors focus on a sparse log (zero indexed errors), etc.

`context_stats` exposes `embedding_fallback` and `insufficiency_reasons`. KB Chroma remains independent of this gate.

## Validation & formatting

- **`validate_and_correct()`** — checks required sections, banned claims, numeric consistency; optional single LLM correction pass
- **`normalize_report_markdown()`** — promotes numbered section lists to `##` headers, strips `///` truncation artifacts
- Applied on generate/compare; **`display_report_content()`** also normalizes cached reports on GET

## Evaluation (Phase 0)

- **`report_grader.py`** — deterministic checks (`markdown_h2_sections`, section presence, etc.)
- **`tests/fixtures/prompt_regression/corpus.json`** — golden cases (some still `pending` for Lab/large-log fixtures)
- Prompt Lab compare runs `_grade_compare_result()` and can export samples with grades
- **`GET /api/llm/prompt-lab/status`** — returns `flm_metrics` (`flm_empty_response_rate`, etc.)

## Unified prompt builder

```
ReportGenerator.build_report_messages(
    file_id, *, quick=False, web_search, focus_mode, model,
    include_chart, fetch_external, include_graph,
    payload_format="markdown", cancel_check=True
) -> ReportPromptBundle
```

`ReportPromptBundle`: `messages`, `est_tokens`, `context_stats`, `prompt_text`, provider flags, optional chart image, KB/RN context.

Used by: `generate_report`, `estimate_cost`, `prompt-preview`, `compare`.

## Execution timing

| Field | Scope |
|-------|-------|
| `llm_duration_seconds` | `_call_llm()` only |
| `generation_duration_seconds` | Full pipeline including context, optional embed/graph, prompt, LLM, validator, formatter |

Both stored on `LLMReport` and returned in API responses.

## Prompt Lab endpoints

- **`POST /report/{file_id}/prompt-preview`** — full prompt + token estimate + `context_stats`; defaults: `quick=false`, `include_chart=false`, `fetch_external=false`
- **`POST /report/{file_id}/compare`** — gated by `LOG_ANALYZER_PROMPT_LAB=1`; baseline + variants; toggles for chart, external fetch, graph; optional `save_sample`
- **`GET /prompt-lab/status`** — `compare_enabled`, `flm_metrics`

## Deferred: Phase 8 streaming

Full-stack streaming (LLM → client → ReportGenerator → SSE → UI) is **UX-only** and intentionally deferred until quality phases 0–7 are validated in production. Current API returns complete reports.

## Related files

- `backend/llm/endpoints.py` — `/config`, `/report/{id}`, prompt-preview, compare, prompt-lab status
- `backend/llm/openai_api_client.py` — FLM session + retries
- `backend/llm/flm_metrics.py` — in-process empty-response rate
- `backend/llm/sanitizer.py` — Presidio-backed redaction for cloud
- `backend/database.py` — `LLMReport` model
- `static/ai-report.js`, `static/prompt-lab-modal.js` — UI
