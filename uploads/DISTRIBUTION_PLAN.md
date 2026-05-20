# Distribution plan — Replicate Log Analyzer (pywebview)

Review and revise this document before any build automation is added to the repo.

---

## Goals

| Goal | Notes |
|------|--------|
| **pywebview only** | End users never run the app in an external browser; native window + `js_api` (file dialogs, etc.) stay required. |
| **Product-shaped UX** | One obvious launcher after install (or after unzip). No instructions like "open PowerShell and run `python desktop.py`." |
| **Hidden toolchain** | Python, pip, and virtual env are build-time concerns only—not something recipients manage. |
| **Wizard acceptable** | An installer (e.g. Inno Setup) is fine; a single monolithic `.exe` is **not** required. |
| **Practical frozen layout** | Prefer **PyInstaller `--onedir`**: one primary `.exe` plus a support folder—still feels like one app, fewer pitfalls than one-file. |
| **Ship KB knowledge** | The pre-indexed KB articles and release notes (ChromaDB + JSON cache) are included so the app is useful out of the box. User-specific log embeddings are **not** shipped. |

---

## Current architecture (baseline)

- **Entry point:** `desktop.py` — starts FastAPI (`backend.main:app`) via uvicorn on `127.0.0.1:8000`, then opens pywebview pointed at that URL.
- **Backend:** FastAPI in `backend/`; static UI in `static/`; SQLite via `backend.database` (`init_db()` on import).
- **Vector store:** ChromaDB (`backend/llm/vectorstore.py`) with five collections sharing one `chroma_db/` persist directory. Local embeddings via `all-MiniLM-L6-v2` (no API key needed).
- **KB tooling:** `kb-assistant/` is a **build-time-only** CLI for scraping/indexing KB articles and release notes into ChromaDB. It is **not** part of the runtime app.
- **Heavy dependencies:** ChromaDB (+onnxruntime, sentence-transformers), Presidio, spaCy, Plotly/Kaleido — bundling needs explicit datas/binaries/hidden imports.

---

## Pre-build cleanup

These items should be resolved before the first PyInstaller run.

### Remove dead dependencies

`polars` and `rapidfuzz` are in `requirements.txt` but **are not imported anywhere** in the Python source. Remove them — they add ~50-80 MB for zero benefit.

### Remove stray files from repo root

| File | Action |
|------|--------|
| `get-pip.py` | Delete — ~2 MB pip bootstrap, not needed in repo or build. |
| `26.0.1` | Delete — empty accidental file. |
| `app_legacy.py` | Delete or archive — dead code, superseded by `desktop.py`. |

### Decide on migration scripts

`migrate_db.py` and `migrate_db_v2.py` — either wire into startup (auto-migrate on version bump) or exclude from the frozen app. Shipping them as standalone scripts is confusing for end users.

---

## ChromaDB data strategy

All five collections currently live under one `chroma_db/` directory:

| Collection | Content | Ship? | Rationale |
|------------|---------|-------|-----------|
| `qlik_replicate_kb` | KB articles | **Yes** | Universal knowledge base — same for every user. |
| `qlik_replicate_release_notes` | Release note chunks | **Yes** | Same. |
| `log_summaries` | Per-file performance summaries | **No** | User-specific log analysis. |
| `error_contexts` | Per-file error embeddings | **No** | User-specific. |
| `anomaly_sections` | Per-file anomaly embeddings | **No** | User-specific. |

### Recommended split: two persist directories

Separate the KB/RN data from log-analysis data so they can be managed independently:

| Directory | Contents | Lifecycle |
|-----------|----------|-----------|
| `chroma_kb/` (shipped, read-only at runtime) | `qlik_replicate_kb` + `qlik_replicate_release_notes` | Built once by `kb-assistant/` before packaging. Bundled as a PyInstaller `datas` entry. Updated only when a new version of the app ships. |
| `chroma_db/` (user-local, writable) | `log_summaries` + `error_contexts` + `anomaly_sections` | Created on first use under `%LOCALAPPDATA%\ReplicateLogAnalyzer\chroma_db\`. Never shipped. |

This requires a small refactor in `vectorstore.py`: the KB/RN query methods (`query_kb`, `query_release_notes`, etc.) open a separate `PersistentClient` pointing at the shipped `chroma_kb/` path, while the log collections keep using the user-local path.

### Also ship: `data/release_notes_cache.json`

This JSON snapshot is the fast-path for release notes correlation (avoids a ChromaDB round-trip). Include it alongside `chroma_kb/` in the `datas` bundle.

---

## Dependency size budget and lazy-loading strategy

### Estimated frozen sizes

| Package group | Approx. size | Core or deferrable? |
|---------------|-------------|---------------------|
| **Python + stdlib** | ~30 MB | Core |
| **FastAPI + Uvicorn + Pydantic + SQLAlchemy** | ~20 MB | Core |
| **pywebview** | ~5 MB | Core |
| **ChromaDB + onnxruntime + sentence-transformers** | ~200-300 MB | Core (KB search + RAG) |
| **httpx** | ~5 MB | Core (LLM API calls) |
| **spaCy + `en_core_web_sm`** | ~100-150 MB | **Deferrable** |
| **Presidio (analyzer + anonymizer)** | ~30-50 MB | **Deferrable** |
| **Plotly + Kaleido** | ~50-80 MB | **Deferrable** |
| **python-docx, inflect** | ~5 MB | Core (small) |
| **Static assets + KB data** | ~20-50 MB | Core |
| | **Total estimate** | **~500-600 MB** (with lazy deps loaded on demand) |

### Lazy-load candidates

These packages are only needed in specific code paths and can be imported on first use instead of at module level:

1. **spaCy + Presidio** — only needed when PII sanitization is active (i.e., user is sending data to external LLMs). Graceful fallback: sanitization simply unavailable until the modules finish loading; log a warning in the UI.

2. **Plotly + Kaleido** — only needed when a vision-capable LLM is selected and chart rendering is triggered. Graceful fallback: text-only analysis until charts are ready.

Lazy-loading these cuts ~180-280 MB from the cold-start load and significantly improves first-launch time. The modules would still be **shipped** in the frozen bundle — they just wouldn't be imported until actually called.

---

## Recommended approach

### Phase A — Frozen application (PyInstaller)

1. **Pre-build cleanup** (see section above).
2. **ChromaDB split** — refactor `vectorstore.py` for two persist directories; run `kb-assistant/` to produce the clean `chroma_kb/` snapshot.
3. **Lazy imports** — wrap spaCy/Presidio and Plotly/Kaleido behind `importlib` or conditional `import` in the functions that use them.
4. Add PyInstaller with a **`.spec` file** (easier to maintain than a long CLI).
5. Set **`desktop.py`** as the entry point.
6. Use **`onedir`**:
   - Faster cold start than one-file.
   - Simpler debugging if something fails to load.
   - Users still only double-click **one** `.exe`.
7. Configure **`datas`**:
   - `static/` — entire tree served by FastAPI.
   - `chroma_kb/` — pre-built KB + release notes vector store.
   - `data/release_notes_cache.json` — fast-path release notes JSON.
   - spaCy `en_core_web_sm` model data.
8. Configure **`collect-all`** for packages that ship non-Python files:
   - Validate: `chromadb`, `onnxruntime`, `presidio_analyzer`, `presidio_anonymizer`, `spacy`, `pydantic`, `sentence_transformers`.
9. **Exclude** from the bundle:
   - `kb-assistant/` (build-time only).
   - `get-pip.py`, `app_legacy.py`, test files, migration scripts (unless auto-migrate is wired in).
   - `*.log`, `log_analyzer.db`, `uploads/`, `chroma_db/`.
10. Smoke-test on a **clean Windows VM** (no Python, no dev tools): cold start, file upload, KB search, LLM chat, export, window close.

### Phase B — Runtime data directories

When running frozen (`sys.frozen is True`), the app must resolve writable paths outside the install directory:

| Data | Location |
|------|----------|
| `log_analyzer.db` | `%LOCALAPPDATA%\ReplicateLogAnalyzer\log_analyzer.db` |
| `chroma_db/` (log embeddings) | `%LOCALAPPDATA%\ReplicateLogAnalyzer\chroma_db\` |
| `uploads/` | `%LOCALAPPDATA%\ReplicateLogAnalyzer\uploads\` |
| `chroma_kb/` (shipped, read-only) | Alongside the `.exe` in the install directory |

This requires a small helper (e.g. `backend/paths.py`) that checks `getattr(sys, 'frozen', False)` and returns the appropriate base paths. `database.py`, `vectorstore.py`, and the upload handler would import from it.

### Phase C — Installer (optional but "product-like")

1. **Inno Setup** (or WiX/MSIX):
   - Copies the PyInstaller output directory.
   - Creates **Start Menu** (and optionally Desktop) shortcut to the main `.exe`.
   - Uninstaller entry that also cleans `%LOCALAPPDATA%\ReplicateLogAnalyzer\` (with user prompt).
2. **WebView2 Runtime:** pywebview on Windows requires the **Microsoft Edge WebView2 Runtime**. Installer should **detect** it and launch the Evergreen bootstrapper if missing — otherwise users get a blank window.
3. **Visual C++ Redistributable:** only if frozen binaries fail on clean Windows — verify on a VM without dev tools.

### Phase D — Release hygiene

1. **Pinned dependencies:** fully pinned `requirements.txt` (or lock file) for reproducible builds.
2. **Versioning:** align executable/product version string with git tag or `__version__`.
3. **Signing:** code-sign installer + `.exe` if distributing outside a trusted internal network.
4. **Update path:** decide how KB data updates reach users (new installer release vs. in-app update mechanism).

---

## Explicit non-goals (for this plan)

- Supporting **browser-only** usage as a substitute for pywebview.
- Shipping a **bundle of `.bat` / manual `pip`** steps to end users.
- Bundling `kb-assistant/` in the distributed app (it is a build-time tool).

---

## Risks and unknowns (to validate during implementation)

| Risk | Mitigation |
|------|------------|
| PyInstaller misses DLLs or package data | Iterate spec `binaries` / `datas` / `hiddenimports`; test on clean Windows VM. |
| Large install size (~500-600 MB) | Expected with ML/NLP stack. Lazy-loading keeps cold start fast. One-folder avoids extraction overhead. |
| Antivirus false positives on frozen exe | Code signing and reputation help; one-folder sometimes triggers less than one-file. |
| First startup slow | Lazy-load heavy deps (spaCy/Presidio, Plotly/Kaleido). Consider a splash screen during FastAPI + ChromaDB init. |
| ChromaDB split breaks existing workflows | Keep collection names identical; only the persist directory changes. Test KB search + log analysis paths independently. |
| User data lost on uninstall | Installer should prompt before deleting `%LOCALAPPDATA%\ReplicateLogAnalyzer\`. |

---

## Decided items

- [x] **One-folder** PyInstaller output.
- [x] **Ship KB + release notes** ChromaDB data; exclude log embeddings.
- [x] **Exclude `kb-assistant/`** from the frozen app.
- [x] **Lazy-load** spaCy/Presidio and Plotly/Kaleido.
- [x] **Remove** `polars`, `rapidfuzz` from `requirements.txt`.

## Open decisions (fill in when ready)

- [ ] **Installer now vs zip-only** for first release artifact.
- [ ] **Per-user vs machine-wide** install path (`%LOCALAPPDATA%` vs `Program Files`).
- [ ] **Auto-migrate** SQLite schema on version bump, or skip migration scripts.
- [ ] **KB update strategy** — new app release only, or in-app refresh mechanism.

---

## Implementation order

Once this plan is approved:

1. **Clean up** — remove dead deps and stray files.
2. **`backend/paths.py`** — centralized path resolution (frozen vs dev).
3. **ChromaDB split** — refactor `vectorstore.py` for two persist dirs; rebuild `chroma_kb/`.
4. **Lazy imports** — wrap heavy deps in deferred loaders.
5. **`.spec` file** — PyInstaller spec with all datas/excludes/hidden imports.
6. **Smoke-test** on clean VM.
7. **Inno Setup script** (if installer path chosen).
8. `.gitignore` updates for `build/` and `dist/`.
