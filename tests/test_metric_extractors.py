"""Tests for metric extraction functions in measurements_controller.

These test the pure extraction logic without touching the DB or Flask.
"""
import pytest
from unittest.mock import MagicMock

from archiver.response.measurements_controller import (
    _extract_clock,
    _extract_latency,
    _extract_mtu,
    _extract_rtt,
    _extract_throughput,
    _extract_trace,
    _parse_iso8601_duration_seconds,
    _m,
    _mk_measurement,
    _ensure_ips,
)
from archiver.openapi_server.models.measurement_request import MeasurementRequest
from archiver.openapi_server.models.node_ref import NodeRef


# ---- helper tests ----

class TestParseISO8601Duration:
    def test_valid_pt_seconds(self):
        assert _parse_iso8601_duration_seconds("PT0.123456S") == pytest.approx(0.123456)

    def test_valid_pt_integer(self):
        assert _parse_iso8601_duration_seconds("PT5S") == pytest.approx(5.0)

    def test_invalid_format(self):
        assert _parse_iso8601_duration_seconds("5 seconds") is None

    def test_empty_string(self):
        assert _parse_iso8601_duration_seconds("") is None

    def test_not_string(self):
        assert _parse_iso8601_duration_seconds(123) is None

    def test_partial_pt(self):
        assert _parse_iso8601_duration_seconds("PT") is None

    def test_pt_no_s(self):
        assert _parse_iso8601_duration_seconds("PT5") is None


class TestMetricHelper:
    def test_creates_metric_with_unit(self):
        m = _m("throughput_mbps", 50.5, "mbps")
        assert m.name == "throughput_mbps"
        assert m.value == pytest.approx(50.5)
        assert m.unit == "mbps"

    def test_creates_metric_without_unit(self):
        m = _m("count", 1.0)
        assert m.name == "count"
        assert m.unit is None


class TestEnsureIPs:
    def test_valid_ips(self):
        req = MeasurementRequest(
            src=NodeRef(ip="10.0.0.1"), dst=NodeRef(ip="10.0.0.2"), raw={}
        )
        assert _ensure_ips(req) is None

    def test_missing_src(self):
        req = MeasurementRequest(src=None, dst=NodeRef(ip="10.0.0.2"), raw={})
        assert _ensure_ips(req) is not None

    def test_missing_dst_ip(self):
        req = MeasurementRequest(src=NodeRef(ip="10.0.0.1"), dst=NodeRef(), raw={})
        assert _ensure_ips(req) is not None


# ---- clock extractor ----

class TestExtractClock:
    def test_with_difference_and_offset(self):
        raw = {"difference": "PT0.001234S", "remote": {"offset": 0.005}}
        test_type, tool, metrics, post_fn = _extract_clock(None, raw)
        assert test_type == "clock"
        assert tool == "pscheduler-clock"
        assert len(metrics) == 2
        assert metrics[0].name == "clock_diff_ms"
        assert metrics[0].value == pytest.approx(1.234)
        assert metrics[1].name == "clock_offset_s"
        assert metrics[1].value == pytest.approx(0.005)
        assert post_fn is None

    def test_with_only_difference(self):
        raw = {"difference": "PT0.5S"}
        _, _, metrics, _ = _extract_clock(None, raw)
        assert len(metrics) == 1
        assert metrics[0].name == "clock_diff_ms"
        assert metrics[0].value == pytest.approx(500.0)

    def test_no_parseable_data(self):
        raw = {"something": "else"}
        _, _, metrics, _ = _extract_clock(None, raw)
        assert len(metrics) == 0

    def test_invalid_difference_format(self):
        raw = {"difference": "invalid"}
        _, _, metrics, _ = _extract_clock(None, raw)
        assert len(metrics) == 0


# ---- latency extractor ----

class TestExtractLatency:
    def test_with_histogram(self):
        raw = {"histogram-latency": {"0.5": 10, "1.5": 10}}
        _, _, metrics, _ = _extract_latency(None, raw)
        assert len(metrics) == 1
        assert metrics[0].name == "avg_latency"
        assert metrics[0].value == pytest.approx(1.0)  # (0.5*10 + 1.5*10) / 20

    def test_empty_histogram(self):
        raw = {"histogram-latency": {}}
        _, _, metrics, _ = _extract_latency(None, raw)
        assert len(metrics) == 0

    def test_no_histogram(self):
        raw = {}
        _, _, metrics, _ = _extract_latency(None, raw)
        assert len(metrics) == 0


# ---- MTU extractor ----

class TestExtractMTU:
    def test_with_mtu_direct(self):
        raw = {"mtu": 1500}
        _, _, metrics, _ = _extract_mtu(None, raw)
        assert len(metrics) == 1
        assert metrics[0].name == "mtu_bytes"
        assert metrics[0].value == pytest.approx(1500.0)

    def test_with_mtu_in_results(self):
        raw = {"results": {"mtu": 9000}}
        _, _, metrics, _ = _extract_mtu(None, raw)
        assert len(metrics) == 1
        assert metrics[0].value == pytest.approx(9000.0)

    def test_fallback_to_result_indicator(self):
        raw = {"succeeded": True}
        _, _, metrics, _ = _extract_mtu(None, raw)
        assert len(metrics) == 1
        assert metrics[0].name == "mtu_result"
        assert metrics[0].value == pytest.approx(1.0)

    def test_failed_fallback(self):
        raw = {"succeeded": False}
        _, _, metrics, _ = _extract_mtu(None, raw)
        assert metrics[0].name == "mtu_result"
        assert metrics[0].value == pytest.approx(0.0)


# ---- RTT extractor ----

class TestExtractRTT:
    def test_all_rtt_fields(self):
        raw = {"mean": "PT0.01S", "max": "PT0.05S", "min": "PT0.001S", "loss": 2.5}
        _, _, metrics, _ = _extract_rtt(None, raw)
        names = {m.name: m.value for m in metrics}
        assert names["mean_rtt_ms"] == pytest.approx(10.0)
        assert names["max_rtt_ms"] == pytest.approx(50.0)
        assert names["min_rtt_ms"] == pytest.approx(1.0)
        assert names["loss_pct"] == pytest.approx(2.5)

    def test_partial_rtt(self):
        raw = {"mean": "PT0.02S"}
        _, _, metrics, _ = _extract_rtt(None, raw)
        assert len(metrics) == 1
        assert metrics[0].name == "mean_rtt_ms"

    def test_invalid_rtt_format(self):
        raw = {"mean": "20ms", "loss": 0.0}
        _, _, metrics, _ = _extract_rtt(None, raw)
        assert len(metrics) == 1  # only loss_pct
        assert metrics[0].name == "loss_pct"

    def test_empty_raw(self):
        _, _, metrics, _ = _extract_rtt(None, {})
        assert len(metrics) == 0


# ---- throughput extractor ----

class TestExtractThroughput:
    def test_summary_throughput_bits(self):
        raw = {"summary": {"summary": {"throughput-bits": 100_000_000, "retransmits": 5}}}
        _, _, metrics, _ = _extract_throughput(None, raw)
        names = {m.name: m.value for m in metrics}
        assert names["throughput_mbps"] == pytest.approx(100.0)
        assert names["retransmits"] == pytest.approx(5.0)

    def test_iperf3_sum_sent_retransmits(self):
        raw = {
            "end": {"sum_sent": {"retransmits": 12}},
            "summary": {"summary": {"throughput-bits": 50_000_000}},
        }
        _, _, metrics, _ = _extract_throughput(None, raw)
        names = {m.name: m.value for m in metrics}
        assert names["retransmits"] == pytest.approx(12.0)

    def test_no_data(self):
        raw = {}
        _, _, metrics, _ = _extract_throughput(None, raw)
        assert len(metrics) == 0


# ---- trace extractor ----

class TestExtractTrace:
    def test_nested_paths(self):
        raw = {"paths": [[
            {"ip": "10.0.0.1", "rtt": "PT0.001S"},
            {"ip": "10.0.0.2", "rtt": "PT0.002S"},
        ]]}
        _, _, metrics, post_fn = _extract_trace(None, raw)
        assert metrics[0].name == "hop_count"
        assert metrics[0].value == pytest.approx(2.0)
        assert post_fn is not None

    def test_flat_paths(self):
        raw = {"paths": [
            {"ip": "10.0.0.1", "rtt": 0.001},
            {"ip": "10.0.0.2", "rtt": 0.002},
        ]}
        _, _, metrics, post_fn = _extract_trace(None, raw)
        assert metrics[0].value == pytest.approx(2.0)

    def test_empty_paths(self):
        raw = {"paths": []}
        _, _, metrics, _ = _extract_trace(None, raw)
        assert metrics[0].value == pytest.approx(0.0)

    def test_post_fn_sets_aux(self):
        raw = {"paths": [[{"ip": "10.0.0.1", "rtt": "PT0.001S"}]]}
        _, _, _, post_fn = _extract_trace(None, raw)

        meas = MagicMock()
        meas.aux = {}
        meas.ts = "2025-01-01T00:00:00Z"
        meas.run_id = "run-1"
        meas.src = "src"
        meas.dst = "dst"
        post_fn(meas, {})
        assert "hops_flat" in meas.aux
        assert "hop_ips" in meas.aux
        assert meas.aux["hop_ips"] == ["10.0.0.1"]


# ---- _mk_measurement ----

class TestMkMeasurement:
    def test_basic_measurement(self):
        body = {
            "run_id": "run-123",
            "ts": "2025-06-15T12:00:00Z",
            "src": {"ip": "10.0.0.1", "name": "src-node"},
            "dst": {"ip": "10.0.0.2", "name": "dst-node"},
            "direction": "forward",
            "raw": {"succeeded": True},
        }
        meas = _mk_measurement(body, "throughput", "iperf3", [_m("tp", 100.0, "mbps")])
        assert meas.run_id == "run-123"
        assert meas.src == "src-node"
        assert meas.dst == "dst-node"
        assert meas.status == "success"
        assert meas.aux["traffic_dir"] == "forward"

    def test_failed_status(self):
        body = {
            "src": {"ip": "10.0.0.1"},
            "dst": {"ip": "10.0.0.2"},
            "raw": {"succeeded": False},
        }
        meas = _mk_measurement(body, "rtt", "ping", [])
        assert meas.status == "failed"

    def test_generates_run_id_if_missing(self):
        body = {
            "src": {"ip": "10.0.0.1"},
            "dst": {"ip": "10.0.0.2"},
            "raw": {},
        }
        meas = _mk_measurement(body, "mtu", "mtu", [])
        assert meas.run_id.startswith("run-")

    def test_uses_ip_when_name_missing(self):
        body = {
            "src": {"ip": "10.0.0.1"},
            "dst": {"ip": "10.0.0.2"},
            "raw": {},
        }
        meas = _mk_measurement(body, "clock", "clock", [])
        assert meas.src == "10.0.0.1"
        assert meas.dst == "10.0.0.2"
