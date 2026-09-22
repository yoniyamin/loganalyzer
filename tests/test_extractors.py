"""Unit tests for backend.core.extractors."""
import pytest
from datetime import datetime, timedelta
from backend.core.extractors import BatchExtractor, TableStatsExtractor, TaskConfigExtractor


class TestBatchExtractor:
    def _make_line(self, offset, thread, component, severity, message):
        ts = (datetime(2025, 6, 15, 10, 0, 0) + timedelta(seconds=offset)).strftime("%Y-%m-%dT%H:%M:%S")
        return f"{thread}: {ts} {component:<18}[{component:<16}]{severity}:  {message}\n"

    def test_basic_batch_cycle(self):
        ext = BatchExtractor()
        base = datetime(2025, 6, 15, 10, 0, 0)

        ext.feed(self._make_line(0, "00001", "TARGET_APPLY", "T",
                 "Going to start applying bulk changes"),
                 0, base, "TARGET_APPLY")
        ext.feed(self._make_line(1, "00001", "TARGET_APPLY", "T",
                 "Start applying 'INSERT (3)' changes for table 'dbo'.'orders'"),
                 1, base + timedelta(seconds=1), "TARGET_APPLY")
        ext.feed(self._make_line(2, "00001", "TARGET_APPLY", "T",
                 "Going to run INSERT statement for table 'dbo'.'orders' from seq 1 to seq 3"),
                 2, base + timedelta(seconds=2), "TARGET_APPLY")
        ext.feed(self._make_line(3, "00001", "TARGET_APPLY", "T",
                 "Finished applying of 3 'INSERT (3)' events for table 'dbo'.'orders'"),
                 3, base + timedelta(seconds=3), "TARGET_APPLY")
        ext.feed(self._make_line(5, "00001", "TARGET_APPLY", "T", "Bulk finished."),
                 5, base + timedelta(seconds=5), "TARGET_APPLY")

        assert len(ext.batches) == 1
        batch = ext.batches[0]
        assert batch["duration_seconds"] == 5.0
        assert batch["changes_count"] == 3
        assert batch["applies_count"] == 1
        assert batch["closure_reason"] == "Normal"
        assert "orders" in batch["tables"]

    def test_non_target_apply_ignored(self):
        ext = BatchExtractor()
        ext.feed("Start Bulk", 0, datetime.now(), "SORTER")
        assert len(ext.batches) == 0

    def test_no_start_means_no_batch(self):
        ext = BatchExtractor()
        base = datetime(2025, 6, 15, 10, 0, 0)
        ext.feed(self._make_line(5, "00001", "TARGET_APPLY", "T", "Bulk finished."),
                 5, base, "TARGET_APPLY")
        assert len(ext.batches) == 0


class TestTableStatsExtractor:
    def _make_line(self, offset, message):
        ts = (datetime(2025, 6, 15, 10, 0, 0) + timedelta(seconds=offset)).strftime("%Y-%m-%dT%H:%M:%S")
        return f"00001: {ts} TARGET_APPLY      [TARGET_APPLY    ]T:  {message}\n"

    def test_insert_stats(self):
        ext = TableStatsExtractor()
        base = datetime(2025, 6, 15, 10, 0, 0)

        ext.feed(self._make_line(0, "Start applying 'INSERT (10)' changes for table 'dbo'.'orders'"),
                 0, base, "TARGET_APPLY")
        ext.feed(self._make_line(2, "Finished applying of 10 'INSERT (10)' events for table 'dbo'.'orders'"),
                 2, base + timedelta(seconds=2), "TARGET_APPLY")

        results = ext.results
        assert len(results) == 1
        r = results[0]
        assert r["table_name"] == "dbo.orders"
        assert r["total_inserts"] == 10
        assert r["total_apply_time_seconds"] == pytest.approx(2.0)
        assert r["avg_apply_time_seconds"] == pytest.approx(2.0)

    def test_multiple_ops(self):
        ext = TableStatsExtractor()
        base = datetime(2025, 6, 15, 10, 0, 0)

        ext.feed(self._make_line(0, "Start applying 'UPDATE (5)' changes for table 'dbo'.'orders'"),
                 0, base, "TARGET_APPLY")
        ext.feed(self._make_line(1, "Finished applying of 5 'UPDATE (5)' events for table 'dbo'.'orders'"),
                 1, base + timedelta(seconds=1), "TARGET_APPLY")
        ext.feed(self._make_line(2, "Start applying 'DELETE (3)' changes for table 'dbo'.'orders'"),
                 2, base + timedelta(seconds=2), "TARGET_APPLY")
        ext.feed(self._make_line(3, "Finished applying of 3 'DELETE (3)' events for table 'dbo'.'orders'"),
                 3, base + timedelta(seconds=3), "TARGET_APPLY")

        results = ext.results
        assert len(results) == 1
        r = results[0]
        assert r["total_updates"] == 5
        assert r["total_deletes"] == 3

    def test_different_components_ignored(self):
        ext = TableStatsExtractor()
        ext.feed("Start applying 10 INSERT changes to table 'dbo'.'orders'",
                 0, datetime.now(), "SORTER")
        assert ext.results == []


class TestTaskConfigExtractor:
    def test_bulk_timeout(self):
        ext = TaskConfigExtractor()
        ext.feed("Set Bulk Timeout = 30000 milliseconds")
        assert ext.config["bulk_timeout_ms"] == 30000

    def test_bulk_timeout_min(self):
        ext = TaskConfigExtractor()
        ext.feed("Set Bulk Timeout Min = 5000 milliseconds")
        assert ext.config["bulk_timeout_min_ms"] == 5000

    def test_bulk_max_file_size(self):
        ext = TaskConfigExtractor()
        ext.feed("Bulk max file size: 32 MB, 32768 KB")
        assert ext.config["bulk_max_file_size_kb"] == 32768

    def test_parallel_apply(self):
        ext = TaskConfigExtractor()
        ext.feed("Parallel bulk apply enabled with maximum 4 apply threads")
        assert ext.config["parallel_apply_threads"] == 4

    def test_source_provider(self):
        ext = TaskConfigExtractor()
        ext.feed("Source endpoint 'Oracle' is using provider")
        assert ext.config["source_type"] == "Oracle"

    def test_target_provider(self):
        ext = TaskConfigExtractor()
        ext.feed("Target endpoint 'Microsoft SQL Server' is using provider")
        assert ext.config["target_type"] == "Microsoft SQL Server"

    def test_merge_detected(self):
        ext = TaskConfigExtractor()
        ext.feed("Going to execute MERGE INTO dbo.orders ...")
        assert ext.config.get("merge_enabled") is True
        assert ext.config.get("apply_mode") == "merge"

    def test_unrelated_lines_ignored(self):
        ext = TaskConfigExtractor()
        ext.feed("Some random log line")
        ext.feed("00001: 2025-01-01T00:00:00 SORTER [T]: Transaction committed")
        assert ext.config == {}
