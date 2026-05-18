# LLM prompt pipeline (reports & context)

This summarizes how **Insights** report prompts are assembled and what gets sent to the model after recent changes.

## Where it runs

- **Orchestration:** `backend/llm/report_generator.py` (`ReportGenerator.generate_report`)
- **Prompt text & message list:** `backend/llm/prompts.py` (`get_messages_for_analysis`, `build_analysis_prompt`, `build_quick_summary_prompt`)
- **Structured log summary:** `PerformanceCockpit` output from SQLite (performance, batches, errors merged with RAG excerpts, Oracle redo metrics, etc.)

## Provider behavior

| Aspect | Gemini / OpenRouter (cloud) | LM Studio (local) |
|--------|-----------------------------|-------------------|
| System prompt | Full `SYSTEM_PROMPT` (component reference table, verbose guidelines) or `SYSTEM_PROMPT_WITH_WEB_SEARCH` | **`SYSTEM_PROMPT_LOCAL`** — condensed (~40% of cloud size); component reference is omitted from the system message and instead injected inline when relevant components appear in error excerpts |
| Prompt mode | `compact=False` — up to 22 error excerpts (2 600 chars each), 4 anomalies, 5 KB, 6 release notes | **`compact=True`** — up to 14 error excerpts (2 200 chars), 3 anomalies, 4 KB, 5 release notes |
| Context inventory | Included at the top of the user message | Same — model sees an explicit "Data Available" summary before any sections |
| Log payload PII redaction | On by default; optional **"Sanitize log data before sending to cloud models"** in AI Configuration | **Always off** for the report prompt (full log-derived text in the user message) |
| Web search in app | Optional via **Enable Web Search** (separate system prompt branch) | Handled inside LM Studio/MCP if configured; the app does not inject Tavily into that path |
| Embeddings / Chroma | Chunks are still sanitized at embed time (`vectorstore`) for stored indices | Same (unchanged) |

## Report message shape

1. **System message**  
   - Cloud: `SYSTEM_PROMPT` (or `SYSTEM_PROMPT_WITH_WEB_SEARCH` when web search is on).
   - Local (LM Studio): `SYSTEM_PROMPT_LOCAL` — shorter, focused on rules that matter for smaller models.

2. **User message** (`build_analysis_prompt`) — built from these sections, in order:

   - **Data Available inventory** (`_build_context_inventory`) — a short bullet list telling the model exactly which data sections are populated vs absent (performance telemetry, error excerpts, CDC health, Oracle redo, anomalies, KB articles, release notes). This prevents the model from hallucinating data it doesn't have.
   - **Critical issues** — high error counts, critical CDC health, high pain tables, Oracle redo variance flags when present.
   - **Log overview** — filename (basename), size, line count.
   - **Performance & diagnostics** — if structured telemetry exists: latency profile, bottleneck call-out, spikes/plateaus, Oracle archived-redo and redo-session narratives, batch/pain-table hints; if not, an explicit "telemetry not captured" section so the model avoids over-calling performance RCA.
   - **Errors & warnings** — merged SQLite errors plus RAG/error contexts, with line-aware excerpts. In compact mode, relevant component annotations are added inline (e.g. "TARGET_APPLY — CDC apply to target") since the full reference table is omitted from the system prompt.
   - **Anomalies** — retrieved anomaly passages.
   - **Release notes correlation** (when retrieved) — EOS/support context and fix IDs when available.
   - **KB context** (when retrieved) — titles/snippets; **KB text is not run through the log sanitizer**.
   - **Analysis request** — checklist of what to cover; focus line adapts to whether performance telemetry is present.

   All section caps (excerpt count, character limits, KB/release-note count) are controlled by the `compact` flag so local models stay within effective attention range.

Quick mode uses a short metrics JSON user prompt (`build_quick_summary_prompt`) instead of the full outline.

## Vision / chart add-on

For models that support vision (Gemini / selected OpenRouter routes), a latency chart image may be prepended to the user message when Plotly/Kaleido are available. LM Studio skips this path today (per-model vision not detected).

## Diagnostic logging

`ReportGenerator.generate_report` now logs a structured summary after building the prompt:

```
Prompt composition: provider=lmstudio compact=True | errors=5 anomalies=2 kb=3 release_notes=4 | est_prompt_tokens=3200
```

This makes it easy to verify that log context is actually reaching the model and to spot empty-context situations.

## Sanitization controls (API / DB)

- **`sanitize_log_for_cloud_llm`** on `llm_config`: persisted preference for cloud providers; **ignored** when the active provider is LM Studio (local prompts are never redacted by this flag).
- **`/api/llm/prompt-preview`** mirrors the same rule: for LM Studio, `sanitized_prompt` matches the raw prompt and Presidio preview is marked skipped.

## Related files

- `backend/llm/sanitizer.py` — Presidio-backed redaction helpers
- `backend/llm/endpoints.py` — `/config`, `/report/{id}`, `/prompt-preview`
- `static/ai-report.js` — provider-aware "generating" toast (syncs provider from `/api/llm/config` before showing)
- `static/ai-config-modal.js` — cloud-only web search / Tavily / sanitize checkbox; hidden on LM Studio tab
