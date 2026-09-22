"""Unit tests for backend.core.error_codes."""
import pytest
from backend.core.error_codes import extract_error_code


class TestSqlState:
    def test_basic_sqlstate_native(self):
        line = "[TARGET_APPLY]E: SqlState: HY000 NativeError: 1205 Message: Lock wait timeout"
        assert extract_error_code(line) == "SqlState:HY000/1205"

    def test_case_insensitive(self):
        line = "SQLSTATE: 42S02 NATIVEERROR: 208"
        assert extract_error_code(line) == "SqlState:42S02/208"

    def test_different_states(self):
        assert extract_error_code("SqlState: 22001 NativeError: 8152") == "SqlState:22001/8152"
        assert extract_error_code("SqlState: 23000 NativeError: 2627") == "SqlState:23000/2627"


class TestOracleErrors:
    def test_ora_basic(self):
        assert extract_error_code("ORA-00054: resource busy") == "ORA-00054"

    def test_ora_in_context(self):
        line = "00001234: 2025-06-15T10:00:00 SOURCE_CAPTURE [E]: Failed to read. ORA-01555: snapshot too old"
        assert extract_error_code(line) == "ORA-01555"

    def test_ora_case_insensitive(self):
        assert extract_error_code("ora-00060: deadlock detected") == "ORA-00060"


class TestMySQLErrors:
    def test_mysql_error(self):
        assert extract_error_code("MySQL Error 1205: Lock wait timeout") == "MySQL:1205"

    def test_mysql_with_context(self):
        line = "Got MySQL Error 1062 (duplicate key)"
        assert extract_error_code(line) == "MySQL:1062"


class TestPostgresErrors:
    def test_pg_sqlstate(self):
        assert extract_error_code("SQLSTATE 23505 unique_violation") == "PG:23505"

    def test_pg_prefix(self):
        assert extract_error_code("PG = 23505 unique_violation") == "PG:23505"


class TestODBCErrors:
    def test_retcode_error(self):
        assert extract_error_code("RetCode: SQL_ERROR") == "SQL_ERROR"

    def test_retcode_no_data(self):
        assert extract_error_code("RetCode: SQL_NO_DATA") == "SQL_NO_DATA"

    def test_retcode_success_ignored(self):
        assert extract_error_code("RetCode: SQL_SUCCESS") is None


class TestNativeOnly:
    def test_native_nonzero(self):
        assert extract_error_code("NativeError: 547") == "Native:547"

    def test_native_zero_ignored(self):
        assert extract_error_code("NativeError: 0") is None


class TestNoMatch:
    def test_plain_text(self):
        assert extract_error_code("This is a normal log line") is None

    def test_empty(self):
        assert extract_error_code("") is None

    def test_numbers_not_confused(self):
        assert extract_error_code("Processed 12345 rows in 6789 ms") is None
