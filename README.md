# Replicate Log Analyzer

Small Flask app to inspect Qlik Replicate logs, parse `[PERFORMANCE]` lines,
and visualize source/target/handling latency with Plotly.

## Structure

- `app.py` – Flask backend (file upload, parsing, JSON API)
- `templates/index.html` – layout (top bar, log preview, Plotly graph, stats panel)
- `static/styles.css` – dark UI and layout
- `static/app.js` – Plotly rendering + click-to-jump in log
- `requirements.txt` – Python deps

## Usage

```bash
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000 and upload a Replicate log.
