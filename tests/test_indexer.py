"""Integration tests for the indexer (process_log_file).

Uses the `indexed_file` fixture which indexes the sample log into a temp DB.
"""
import pytest
from sqlalchemy import text as sa_text

from backend.database import (
    LogFile, LogIndex, LogError, LogLineMeta, LogBatch,
    LogTableStats, LogTaskConfig, LogPerformance, FileVersion, LogStats,
)


class TestIndexerPersistence:
    """Verify the indexer populates all expected tables."""

    def test_file_status_ready(self, indexed_file):
        db, file_id, _ = indexed_file
        f = db.query(LogFile).filter(LogFile.id == file_id).first()
        assert f.status == "ready"
        assert f.line_count > 0

    def test_sparse_index_created(self, indexed_file):
        db, file_id, _ = indexed_file
        count = db.query(LogIndex).filter(LogIndex.file_id == file_id).count()
        assert count > 0

    def test_line_meta_dense(self, indexed_file):
        db, file_id, _ = indexed_file
        f = db.query(LogFile).filter(LogFile.id == file_id).first()
        meta_count = db.query(LogLineMeta).filter(LogLineMeta.file_id == file_id).count()
        # Dense meta should have roughly one row per non-empty line
        assert meta_count > 0
        assert meta_count <= f.line_count + 1

    def test_errors_extracted(self, indexed_file):
        db, file_id, _ = indexed_file
        errors = db.query(LogError).filter(LogError.file_id == file_id).all()
        assert len(errors) >= 3  # sample log has at least 3 errors

    def test_error_codes_populated(self, indexed_file):
        db, file_id, _ = indexed_file
        coded_errors = db.query(LogError).filter(
            LogError.file_id == file_id,
            LogError.error_code.isnot(None)
        ).all()
        assert len(coded_errors) >= 2
        codes = {e.error_code for e in coded_errors}
        assert "SqlState:HY000/1205" in codes or "ORA-00054" in codes

    def test_batch_extracted(self, indexed_file):
        db, file_id, _ = indexed_file
        batches = db.query(LogBatch).filter(LogBatch.file_id == file_id).all()
        assert len(batches) >= 1
        b = batches[0]
        assert b.duration_seconds > 0
        assert b.changes_count > 0

    def test_table_stats_extracted(self, indexed_file):
        db, file_id, _ = indexed_file
        stats = db.query(LogTableStats).filter(LogTableStats.file_id == file_id).all()
        assert len(stats) >= 1
        s = stats[0]
        assert s.table_name == "dbo.orders"
        assert s.total_inserts >= 5

    def test_task_config_extracted(self, indexed_file):
        db, file_id, _ = indexed_file
        cfg = db.query(LogTaskConfig).filter(LogTaskConfig.file_id == file_id).first()
        assert cfg is not None
        assert cfg.bulk_timeout_ms == 30000
        assert cfg.bulk_timeout_min_ms == 5000
        assert cfg.bulk_max_file_size_kb == 32768
        assert cfg.parallel_apply_threads == 4
        assert cfg.source_type == "Oracle"
        assert cfg.target_type == "Microsoft SQL Server"

    def test_performance_extracted(self, indexed_file):
        db, file_id, _ = indexed_file
        perf = db.query(LogPerformance).filter(LogPerformance.file_id == file_id).all()
        assert len(perf) >= 1
        p = perf[0]
        assert p.source_latency == pytest.approx(1.234)
        assert p.target_latency == pytest.approx(0.456)
        assert p.handling_latency == pytest.approx(0.789)

    def test_file_version_created(self, indexed_file):
        db, file_id, _ = indexed_file
        fv = db.query(FileVersion).filter(FileVersion.file_id == file_id).first()
        assert fv is not None
        assert fv.schema_version >= 1
        assert fv.extractor_version == 1
        assert fv.fts_version == 1
        assert fv.indexed_at is not None


class TestIndexerFTS:
    """Verify FTS5 indexing."""

    def test_fts_populated(self, indexed_file):
        db, file_id, _ = indexed_file
        result = db.execute(
            sa_text("SELECT count(*) FROM log_lines_fts WHERE file_id = :fid"),
            {"fid": file_id}
        ).scalar()
        assert result > 0

    def test_fts_search_match(self, indexed_file):
        db, file_id, _ = indexed_file
        result = db.execute(
            sa_text(
                "SELECT line_number FROM log_lines_fts "
                "WHERE body MATCH :q AND file_id = :fid LIMIT 5"
            ),
            {"q": '"ORA-00054"', "fid": file_id}
        ).fetchall()
        assert len(result) >= 1

    def test_fts_search_customers(self, indexed_file):
        db, file_id, _ = indexed_file
        result = db.execute(
            sa_text(
                "SELECT line_number FROM log_lines_fts "
                "WHERE body MATCH :q AND file_id = :fid LIMIT 5"
            ),
            {"q": "customers", "fid": file_id}
        ).fetchall()
        assert len(result) >= 1


class TestIndexerIdempotency:
    """Verify reindexing doesn't duplicate data."""

    def test_reindex_no_duplicates(self, indexed_file):
        """Simulate reindex as the endpoint does: delete derived data, then reprocess."""
        db, file_id, log_path = indexed_file
        from backend.core.indexer import process_log_file

        first_errors = db.query(LogError).filter(LogError.file_id == file_id).count()
        first_meta = db.query(LogLineMeta).filter(LogLineMeta.file_id == file_id).count()

        # Delete all derived data (as the endpoint does before calling process_log_file)
        db.query(LogIndex).filter(LogIndex.file_id == file_id).delete()
        db.query(LogError).filter(LogError.file_id == file_id).delete()
        db.query(LogLineMeta).filter(LogLineMeta.file_id == file_id).delete()
        db.query(LogBatch).filter(LogBatch.file_id == file_id).delete()
        db.query(LogTableStats).filter(LogTableStats.file_id == file_id).delete()
        db.query(LogTaskConfig).filter(LogTaskConfig.file_id == file_id).delete()
        db.query(FileVersion).filter(FileVersion.file_id == file_id).delete()
        db.execute(sa_text("DELETE FROM log_lines_fts WHERE file_id = :fid"), {"fid": file_id})
        db.commit()

        # Re-run the indexer
        process_log_file(db, file_id)

        second_errors = db.query(LogError).filter(LogError.file_id == file_id).count()
        second_meta = db.query(LogLineMeta).filter(LogLineMeta.file_id == file_id).count()

        assert first_errors == second_errors
        assert first_meta == second_meta
