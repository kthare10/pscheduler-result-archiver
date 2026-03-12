import logging
import re
import uuid
from datetime import datetime, timezone

import connexion
from typing import Callable, Dict, List, Optional, Any

from archiver.common.globals import get_globals
from archiver.db.database_manager import DatabaseManager
from archiver.openapi_server.models import Metric, Measurement
from archiver.openapi_server.models.measurement_request import MeasurementRequest  # noqa: E501
from archiver.response.cors_response import cors_400, cors_200_no_content, cors_500

logger = logging.getLogger(__name__)

DBM = DatabaseManager.from_config(config=get_globals().config)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _m(name: str, value: float, unit: Optional[str] = None) -> Metric:
    m = Metric(name=name, value=float(value))
    if unit:
        m.unit = unit
    return m

def _ensure_ips(body: MeasurementRequest) -> Optional[str]:
    if not body.src or not body.src.ip:
        return "src.ip is required"
    if not body.dst or not body.dst.ip:
        return "dst.ip is required"
    return None

def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None

def _parse_iso8601_duration_seconds(s: str) -> Optional[float]:
    """Parse 'PTxS' ISO 8601 duration strings to float seconds."""
    if isinstance(s, str) and s.startswith("PT") and s.endswith("S"):
        try:
            return float(s[2:-1])
        except (ValueError, TypeError):
            return None
    return None

def _mk_measurement(body: Dict[str, Any], test_type: str, tool: str, metrics: List[Metric]) -> Measurement:
    src, dst = body["src"], body["dst"]
    run_id = body.get("run_id") or f"run-{uuid.uuid4().hex[:8]}"
    ts = body.get("ts") or _now_iso()
    direction = body.get("direction")  # "forward"|"reverse"|None
    status = "success"
    if isinstance(body.get("raw"), dict) and body["raw"].get("succeeded") is False:
        status = "failed"

    aux = body.get("raw") or {}
    aux = {**aux, "src": src, "dst": dst}
    if direction:
        aux["traffic_dir"] = direction

    return Measurement(
        ts=ts,
        run_id=run_id,
        test_type=test_type,
        tool=tool,
        src=src.get("name") or src["ip"],
        dst=dst.get("name") or dst["ip"],
        status=status,
        metrics=metrics,
        aux=aux,
    )


def _ingest(body, extract_fn: Callable[[MeasurementRequest, Dict[str, Any]], tuple]):
    """Common ingestion pipeline shared by all measurement types.

    extract_fn receives (measurement_request, raw) and returns
    (test_type, tool, metrics, post_fn_or_None) where post_fn is called
    with (meas, body) after _mk_measurement for any post-processing
    (e.g. trace hops).
    """
    measurement_request = body
    if connexion.request.is_json:
        measurement_request = MeasurementRequest.from_dict(connexion.request.get_json())

    err = _ensure_ips(measurement_request)
    if err:
        return cors_400()

    raw = measurement_request.raw
    test_type, tool, metrics, post_fn = extract_fn(measurement_request, raw)

    meas = _mk_measurement(body, test_type=test_type, tool=tool, metrics=metrics)
    if post_fn:
        post_fn(meas, body)

    try:
        DBM.upsert_run(meas, upsert=True)
        return cors_200_no_content(details={"run_id": meas.run_id})
    except Exception:
        logger.exception("Failed to upsert %s measurement", test_type)
        return cors_500(details="Internal server error")


# ---- metric extractors (one per test type) ----

def _extract_clock(_req, raw):
    diff_s = _parse_iso8601_duration_seconds(raw.get("difference", ""))
    offset_s = (raw.get("remote") or {}).get("offset")

    metrics: List[Metric] = []
    if diff_s is not None:
        metrics.append(_m("clock_diff_ms", diff_s * 1000.0, "ms"))
    if offset_s is not None:
        metrics.append(_m("clock_offset_s", float(offset_s), "s"))

    return "clock", "pscheduler-clock", metrics, None


def _extract_latency(_req, raw):
    avg_latency = None
    hist = raw.get("histogram-latency", {})
    if hist:
        total_count = sum(hist.values())
        avg_latency = sum(float(k) * v for k, v in hist.items()) / total_count

    metrics: List[Metric] = []
    if avg_latency is not None:
        metrics.append(_m("avg_latency", float(avg_latency), "ms"))

    return "latency", "owamp/twping", metrics, None


def _extract_mtu(_req, raw):
    mtu = raw.get("mtu") or (raw.get("results") or {}).get("mtu")
    metrics: List[Metric] = []
    if mtu is not None:
        metrics.append(_m("mtu_bytes", float(mtu), "bytes"))
    if not metrics:
        metrics.append(_m("mtu_result", 1.0 if raw.get("succeeded", True) else 0.0, "count"))

    return "mtu", "mtu", metrics, None


def _extract_rtt(_req, raw):
    metrics: List[Metric] = []
    for field, metric_name in [("mean", "mean_rtt_ms"), ("max", "max_rtt_ms"), ("min", "min_rtt_ms")]:
        val_s = _parse_iso8601_duration_seconds(raw.get(field, ""))
        if val_s is not None:
            metrics.append(_m(metric_name, val_s * 1000, "ms"))
    loss_pct = raw.get("loss")
    if loss_pct is not None:
        metrics.append(_m("loss_pct", float(loss_pct), "pct"))

    return "rtt", "ping", metrics, None


def _extract_throughput(_req, raw):
    metrics: List[Metric] = []

    end = raw.get("end", {}) if isinstance(raw, dict) else {}
    sum_sent = end.get("sum_sent") or {}
    retrans = sum_sent.get("retransmits")

    summary = raw.get("summary") or {}
    summary_summary = summary.get("summary") or {}
    bits_total = summary_summary.get("throughput-bits") or summary_summary.get("throughput_bits")
    if retrans is None:
        r = summary_summary.get("retransmits")
        if r is not None:
            try:
                retrans = float(r)
            except (ValueError, TypeError):
                pass

    if bits_total is not None:
        metrics.append(_m("throughput_mbps", float(bits_total) / 1e6, "mbps"))
    if retrans is not None:
        try:
            metrics.append(_m("retransmits", float(retrans), "count"))
        except (ValueError, TypeError):
            pass

    return "throughput", "iperf3/nuttcp/ethr", metrics, None


def _extract_trace(_req, raw):
    paths = raw.get("paths") or []

    first_path = []
    if paths and isinstance(paths[0], list):
        first_path = paths[0]
    elif paths and isinstance(paths[0], dict):
        first_path = paths

    hop_count = len(first_path)

    hops_flat = []
    hop_ips = []
    for idx, hop in enumerate(first_path, start=1):
        ip = hop.get("ip")
        rtt_ms = None
        rtt = hop.get("rtt")
        if isinstance(rtt, str):
            val = _parse_iso8601_duration_seconds(rtt)
            if val is not None:
                rtt_ms = val * 1000.0
        elif isinstance(rtt, (int, float)):
            rtt_ms = float(rtt) * 1000.0
        if ip:
            hop_ips.append(ip)
        hops_flat.append({"idx": idx, "ip": ip, "rtt_ms": rtt_ms})

    metrics = [_m("hop_count", float(hop_count), "count")]

    def _post_trace(meas, _body):
        aux = meas.aux or {}
        aux["hops_flat"] = hops_flat
        aux["hop_ips"] = hop_ips
        meas.aux = aux
        try:
            DBM.upsert_trace_hops(
                ts=meas.ts, run_id=meas.run_id,
                src=meas.src, dst=meas.dst,
                hops_flat=hops_flat,
            )
        except Exception:
            logger.exception("Failed to upsert trace hops for run_id=%s", meas.run_id)

    return "trace", "traceroute", metrics, _post_trace


# ---- public endpoint handlers (auto-routed by Connexion) ----

def create_clock_measurement(body):  # noqa: E501
    """Ingest a pScheduler clock result (skew/offset)"""
    return _ingest(body, _extract_clock)

def create_latency_measurement(body):  # noqa: E501
    """Ingest pScheduler latency/owamp result (one/two-way delay, jitter, loss)"""
    return _ingest(body, _extract_latency)

def create_mtu_measurement(body):  # noqa: E501
    """Ingest pScheduler MTU result"""
    return _ingest(body, _extract_mtu)

def create_rtt_measurement(body):  # noqa: E501
    """Ingest pScheduler RTT/ping result"""
    return _ingest(body, _extract_rtt)

def create_throughput_measurement(body):  # noqa: E501
    """Ingest pScheduler throughput (iperf3/nuttcp/ethr) result"""
    return _ingest(body, _extract_throughput)

def create_trace_measurement(body):  # noqa: E501
    """Ingest pScheduler Trace result"""
    return _ingest(body, _extract_trace)
