# Log Analyzer – Setup Guide

Instructions for setting up the Log Analyzer project on a new computer.

---

## Prerequisites

- **Python 3.10–3.13** (recommended: 3.12)
  - Avoid Python 3.14+ pre-release; many dependencies lack wheels and builds may fail.
- **Git** (for cloning)
- **.NET Framework 4.0+** (Windows only, for pywebview)

---

## Quick Setup

```powershell
# 1. Clone the repository
git clone <repo-url>
cd log_analyzer

# 2. Create virtual environment
python -m venv .venv

# 3. Activate (PowerShell)
.\.venv\Scripts\Activate.ps1

# 4. Install dependencies
pip install -r requirements.txt

# 5. Download spaCy language model (required for PII detection)
python -m spacy download en_core_web_lg

# 6. Run the app
python desktop.py
```

---

## Common Issues & Workarounds

### 1. Virtual environment path mismatch

**Symptom:** `Fatal error in launcher: Unable to create process using '...python.exe'` or `The system cannot find the file specified`

**Cause:** The project was moved (e.g. from `PycharmProjects` to `OneDrive\...\PycharmProjects`). The venv stores absolute paths that become invalid.

**Fix:** Recreate the virtual environment:

```powershell
deactivate
Remove-Item -Recurse -Force .venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

### 2. `pythonnet` build failure on Windows

**Symptom:** `Failed building wheel for pythonnet` with NuGet errors such as:
- `Content Types XML does not match schema`
- `Command 'tools\nuget\nuget.exe update -self' returned non-zero exit status 1`

**Cause:** `pywebview` uses `pythonnet` on Windows for the native window. `pythonnet` must build from source when no wheel exists for your Python version, and the build can fail due to NuGet or .NET tooling issues.

**Workarounds (try in order):**

#### A. Use Python 3.12 or 3.13

Pre-built wheels are more likely to exist. Install Python 3.12 from [python.org](https://www.python.org/downloads/) and recreate the venv with it.

#### B. Install a pre-built wheel

1. Go to [Christoph Gohlke's Windows wheels](https://www.lfd.uci.edu/~gohlke/pythonlibs/#pythonnet)
2. Download the wheel matching your Python version and architecture (e.g. `cp312` for Python 3.12, `win_amd64`)
3. Install it before `requirements.txt`:

```powershell
pip install path\to\pythonnet‑3.0.3‑cp312‑cp312‑win_amd64.whl
pip install -r requirements.txt
```

#### C. Use the Qt backend instead of pythonnet

Install pywebview with the Qt backend so pythonnet is not required:

```powershell
pip install pywebview[qt]
# Then install the rest (excluding pywebview to avoid pulling pythonnet)
pip install fastapi uvicorn python-multipart sqlalchemy pydantic chromadb httpx presidio-analyzer presidio-anonymizer python-docx inflect rapidfuzz polars spacy
```

Set the environment variable before running:

```powershell
$env:USE_QT = "1"
python desktop.py
```

---

### 3. OneDrive and project location

If the project lives under OneDrive, syncing can cause:

- Venv paths to break when the folder moves
- Large `.venv` folders to sync unnecessarily

**Recommendations:**

- Add `.venv` to `.gitignore` (if not already)
- Consider excluding `.venv` from OneDrive sync
- Recreate the venv after cloning or moving the project

---

### 4. spaCy model not found

**Symptom:** `Can't find model 'en_core_web_lg'`

**Fix:**

```powershell
python -m spacy download en_core_web_lg
```

---

## Running the Application

- **Desktop GUI:** `python desktop.py`
- **Web only (no GUI):** `uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000`

---

## Optional: API keys

For AI features (e.g. Tavily search), configure API keys in the app’s settings or via environment variables. See the project docs for details.

---

## Summary checklist

- [ ] Python 3.10–3.13 installed
- [ ] Virtual environment created and activated
- [ ] `pip install -r requirements.txt` completed
- [ ] `python -m spacy download en_core_web_lg` run
- [ ] If pythonnet fails: try Python 3.12, a pre-built wheel, or `pywebview[qt]`
- [ ] `python desktop.py` runs successfully
