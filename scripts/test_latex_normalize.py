"""Quick check for LM Studio LaTeX post-processing."""
from backend.llm.lmstudio_client import _normalize_latex_math

SAMPLE = (
    r"Average Handling Latency: $\text{avg } 714.33\text{s}$ (p95 $4781.76\text{s}$). "
    r"Detected **$195$** spikes and $0\%$ batches. Sustained $>5700\text{s}$ periods."
)

out = _normalize_latex_math(SAMPLE)
print(out)
assert "$" not in out, out
assert r"\text" not in out, out
assert "714.33s" in out
assert "195" in out
assert "0%" in out
assert ">5700s" in out
print("OK")
