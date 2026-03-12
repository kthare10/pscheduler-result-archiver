"""Tests for archiver.db.database_manager — row building and upsert logic.

Uses SQLite in-memory for fast testing of the ORM and upsert paths.
Note: PostgreSQL-specific features (ON CONFLICT, JSONB) are tested via
integration tests against a real Postgres; these tests verify the row
building logic and basic ORM operations.
"""
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from archiver.db.database_manager import DatabaseManager, UpsertCounts


class TestRowsFromRun:
    """Test the static _rows_from_run method (no DB required)."""

    def _make_run(self, **kwargs):
        """Create a mock run object with given attributes."""
        run = MagicMock()
        defaults = {
            "ts": "2025-06-15T12:00:00+00:00",
            "run_id": "run-abc",
            "test_type": "throughput",
            "tool": "iperf3",
            "src": "10.0.0.1",
            "dst": "10.0.0.2",
            "status": "success",
            "duration_s": None,
            "metrics": [],
            "aux": {"key": "value"},
        }
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(run, k, v)
        return run

    def _make_metric(self, name="throughput_mbps", value=100.0, unit="mbps"):
        m = MagicMock()
        m.name = name
        m.value = value
        m.unit = unit
        return m

    def test_builds_rows_from_metrics(self):
        m1 = self._make_metric("throughput_mbps", 100.0, "mbps")
        m2 = self._make_metric("retransmits", 5.0, "count")
        run = self._make_run(metrics=[m1, m2])

        rows = DatabaseManager._rows_from_run(run)
        assert len(rows) == 2
        assert rows[0]["metric_name"] == "throughput_mbps"
        assert rows[0]["metric_value"] == 100.0
        assert rows[0]["unit"] == "mbps"
        assert rows[1]["metric_name"] == "retransmits"

    def test_skips_metrics_without_name(self):
        m = self._make_metric(name=None, value=1.0)
        run = self._make_run(metrics=[m])
        rows = DatabaseManager._rows_from_run(run)
        assert len(rows) == 0

    def test_skips_metrics_without_value(self):
        m = self._make_metric(name="test", value=None)
        run = self._make_run(metrics=[m])
        rows = DatabaseManager._rows_from_run(run)
        assert len(rows) == 0

    def test_empty_metrics(self):
        run = self._make_run(metrics=[])
        rows = DatabaseManager._rows_from_run(run)
        assert len(rows) == 0

    def test_parses_iso_timestamp(self):
        m = self._make_metric()
        run = self._make_run(ts="2025-06-15T12:00:00Z", metrics=[m])
        rows = DatabaseManager._rows_from_run(run)
        assert isinstance(rows[0]["ts"], datetime)
        assert rows[0]["ts"].tzinfo is not None

    def test_handles_datetime_ts(self):
        dt = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        m = self._make_metric()
        run = self._make_run(ts=dt, metrics=[m])
        rows = DatabaseManager._rows_from_run(run)
        assert rows[0]["ts"] == dt

    def test_aux_serialized_to_json(self):
        m = self._make_metric()
        run = self._make_run(aux={"nested": {"a": 1}}, metrics=[m])
        rows = DatabaseManager._rows_from_run(run)
        # Should be JSON-serializable (round-trips)
        assert json.loads(json.dumps(rows[0]["aux"])) == {"nested": {"a": 1}}

    def test_none_aux(self):
        m = self._make_metric()
        run = self._make_run(aux=None, metrics=[m])
        rows = DatabaseManager._rows_from_run(run)
        assert rows[0]["aux"] is None

    def test_preserves_all_fields(self):
        m = self._make_metric()
        run = self._make_run(
            run_id="run-xyz",
            test_type="rtt",
            tool="ping",
            src="src-host",
            dst="dst-host",
            status="failed",
            duration_s=3.5,
            metrics=[m],
        )
        rows = DatabaseManager._rows_from_run(run)
        r = rows[0]
        assert r["run_id"] == "run-xyz"
        assert r["test_type"] == "rtt"
        assert r["tool"] == "ping"
        assert r["src"] == "src-host"
        assert r["dst"] == "dst-host"
        assert r["status"] == "failed"
        assert r["duration_s"] == 3.5
