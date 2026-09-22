"""Tests for FLM reliability metrics."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.llm.flm_metrics import get_flm_metrics, record_flm_completion, reset_flm_metrics


class TestFlmMetrics:
    def setup_method(self):
        reset_flm_metrics()

    def test_empty_response_rate(self):
        record_flm_completion(empty=False)
        record_flm_completion(empty=True)
        record_flm_completion(empty=False)
        metrics = get_flm_metrics()
        assert metrics["requests"] == 3
        assert metrics["empty_responses"] == 1
        assert metrics["flm_empty_response_rate"] == 0.3333
