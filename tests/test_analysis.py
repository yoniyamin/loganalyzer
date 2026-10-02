"""Tests for backend.core.analysis."""

from backend.core.analysis import PerformanceCockpit, TablePerformanceAnalyzer


def test_get_pain_tables_treats_null_apply_times_as_zero():
    """Tables with ops but no finished apply can have NULL avg/max in DB."""
    stats = [
        {
            "table_name": "dbo.orders",
            "total_inserts": 10,
            "total_updates": 0,
            "total_deletes": 0,
            "total_merges": 0,
            "total_apply_time_seconds": 0.0,
            "avg_apply_time_seconds": None,
            "max_apply_time_seconds": None,
            "one_by_one_count": 0,
            "has_pk": True,
            "error_count": 0,
        }
    ]
    rows = TablePerformanceAnalyzer(stats).get_pain_tables(10)
    assert len(rows) == 1
    assert rows[0]["avg_apply_time"] == 0
    assert rows[0]["max_apply_time"] == 0
    assert rows[0]["total_operations"] == 10


def test_generate_summary_with_null_table_apply_times():
    perf = [
        {
            "timestamp": None,
            "source_latency": 1.0,
            "handling_latency": 1.0,
            "target_latency": 2.0,
            "line_number": 1,
        }
    ]
    table_stats = [
        {
            "table_name": "dbo.orders",
            "total_inserts": 1,
            "total_updates": 0,
            "total_deletes": 0,
            "total_merges": 0,
            "total_apply_time_seconds": 0.0,
            "avg_apply_time_seconds": None,
            "max_apply_time_seconds": None,
            "one_by_one_count": 0,
            "has_pk": True,
            "error_count": 0,
        }
    ]
    summary = PerformanceCockpit(performance_data=perf, table_stats=table_stats).generate_summary()
    assert summary["pain_tables"][0]["avg_apply_time"] == 0
