import re
import uuid
from datetime import datetime, timezone

import connexion
from typing import Dict, List, Optional, Any

from numpy.ma.core import min_val

from archiver.common.globals import get_globals
from archiver.db.database_manager import DatabaseManager
from archiver.openapi_server.models import Metric, Measurement
from archiver.openapi_server.models.measurement_request import MeasurementRequest  # noqa: E501
from archiver.response.cors_response import cors_400, cors_200_no_content, cors_500

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
        # allow both with/without timezone; fallback to naive as UTC
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None

def _mk_measurement(body: Dict[str, Any], test_type: str, tool: str, metrics: List[Metric]) -> Measurement:
    src, dst = body["src"], body["dst"]
    run_id = body.get("run_id") or f"run-{uuid.uuid4().hex[:8]}"
    ts = body.get("ts") or _now_iso()
    direction = body.get("direction")  # "forward"|"reverse"|None
    status = "success"
    if isinstance(body.get("raw"), dict) and body["raw"].get("succeeded") is False:
        status = "failed"

    # attach useful labels into aux
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


def create_clock_measurement(body):  # noqa: E501
    """Ingest a pScheduler clock result (skew/offset)

     # noqa: E501

    :param measurement_request: 
    :type measurement_request: dict | bytes

    :rtype: Union[Status200OkNoContent, Tuple[Status200OkNoContent, int], Tuple[Status200OkNoContent, int, Dict[str, str]]
    """
    measurement_request = body
    if connexion.request.is_json:
        measurement_request = MeasurementRequest.from_dict(connexion.request.get_json())  # noqa: E501

    err = _ensure_ips(measurement_request)
    if err:
        return cors_400()

    raw = measurement_request.raw
    diff_s = None
    if isinstance(raw.get("difference"), str) and raw["difference"].startswith("PT") and raw["difference"].endswith("S"):
        try:
            diff_s = float(raw["difference"][2:-1])
        except Exception:
            pass
    offset_s = (raw.get("remote") or {}).get("offset")

    metrics: List[Metric] = []
    if diff_s is not None:
        metrics.append(_m("clock_diff_ms", diff_s * 1000.0, "ms"))
    if offset_s is not None:
        metrics.append(_m("clock_offset_s", float(offset_s), "s"))
    #if not metrics:
    #    metrics.append(_m("clock_result", 1.0 if raw.get("succeeded", True) else 0.0, "count"))

    meas = _mk_measurement(body, test_type="clock", tool="pscheduler-clock", metrics=metrics)
    try:
        c = DBM.upsert_run(meas, upsert=True)
        return cors_200_no_content(details={"run_id": meas.run_id})
    except Exception as e:
        return cors_500(details=str(e))

def create_latency_measurement(body):  # noqa: E501
    """Ingest pScheduler latency/owamp result (one/two-way delay, jitter, loss)

     # noqa: E501

    :param measurement_request: 
    :type measurement_request: dict | bytes

    :rtype: Union[Status200OkNoContent, Tuple[Status200OkNoContent, int], Tuple[Status200OkNoContent, int, Dict[str, str]]
    """
    measurement_request = body
    if connexion.request.is_json:
        measurement_request = MeasurementRequest.from_dict(connexion.request.get_json())  # noqa: E501
    err = _ensure_ips(measurement_request)
    if err:
        return cors_400()

    raw = measurement_request.raw
    avg_latency = None
    hist = raw.get("histogram-latency", {})
    if hist:
        total_count = sum(hist.values())
        avg_latency = sum(float(k) * v for k, v in hist.items()) / total_count

    metrics: List[Metric] = []
    if avg_latency is not None:
        metrics.append(_m("avg_latency", float(avg_latency), "ms"))

    meas = _mk_measurement(body, test_type="latency", tool="owamp/twping", metrics=metrics)
    try:
        c = DBM.upsert_run(meas, upsert=True)
        return cors_200_no_content(details={"run_id": meas.run_id})
    except Exception as e:
        return cors_500(details=str(e))

def create_mtu_measurement(body):  # noqa: E501
    """Ingest pScheduler MTU result

     # noqa: E501

    :param measurement_request: 
    :type measurement_request: dict | bytes

    :rtype: Union[Status200OkNoContent, Tuple[Status200OkNoContent, int], Tuple[Status200OkNoContent, int, Dict[str, str]]
    """
    measurement_request = body
    if connexion.request.is_json:
        measurement_request = MeasurementRequest.from_dict(connexion.request.get_json())  # noqa: E501

    err = _ensure_ips(measurement_request)
    if err:
        return cors_400()

    raw = measurement_request.raw
    mtu = raw.get("mtu") or (raw.get("results") or {}).get("mtu")
    metrics: List[Metric] = []
    if mtu is not None:
        metrics.append(_m("mtu_bytes", float(mtu), "bytes"))
    if not metrics:
        metrics.append(_m("mtu_result", 1.0 if raw.get("succeeded", True) else 0.0, "count"))

    meas = _mk_measurement(body, test_type="mtu", tool="mtu", metrics=metrics)
    try:
        c = DBM.upsert_run(meas, upsert=True)
        return cors_200_no_content(details={"run_id": meas.run_id})
    except Exception as e:
        return cors_500(details=str(e))


def create_rtt_measurement(body):  # noqa: E501
    """Ingest pScheduler RTT/ping result

     # noqa: E501

    :param measurement_request: 
    :type measurement_request: dict | bytes

    :rtype: Union[Status200OkNoContent, Tuple[Status200OkNoContent, int], Tuple[Status200OkNoContent, int, Dict[str, str]]
    """
    measurement_request = body
    if connexion.request.is_json:
        measurement_request = MeasurementRequest.from_dict(connexion.request.get_json())  # noqa: E501
    err = _ensure_ips(measurement_request)
    if err:
        return cors_400()

    raw = measurement_request.raw

    mean_rtt = raw.get("mean")
    mean_rtt_val_sec = None
    if mean_rtt:
        match = re.match(r"PT(\d+(\.\d+)?)S", mean_rtt)
        if match:
            mean_rtt_val_sec = float(match.group(1))
    max_rtt = raw.get("max")
    max_rtt_val_sec = None
    if max_rtt:
        match = re.match(r"PT(\d+(\.\d+)?)S", max_rtt)
        if match:
            max_rtt_val_sec = float(match.group(1))
    min_rtt = raw.get("min")
    min_rtt_val_sec = None
    if min_rtt:
        match = re.match(r"PT(\d+(\.\d+)?)S", min_rtt)
        if match:
            min_rtt_val_sec = float(match.group(1))

    loss_pct = raw.get("loss")

    metrics: List[Metric] = []
    if mean_rtt_val_sec is not None:
        metrics.append(_m("mean_rtt_ms", float(mean_rtt_val_sec) * 1000, "ms"))
    if max_rtt_val_sec is not None:
        metrics.append(_m("max_rtt_ms", float(max_rtt_val_sec) * 1000, "ms"))
    if min_rtt_val_sec is not None:
        metrics.append(_m("min_rtt_ms", float(min_rtt_val_sec) * 1000, "ms"))
    if loss_pct is not None:
        metrics.append(_m("loss_pct", float(loss_pct), "pct"))

    meas = _mk_measurement(body, test_type="rtt", tool="ping", metrics=metrics)
    try:
        c = DBM.upsert_run(meas, upsert=True)
        return cors_200_no_content(details={"run_id": meas.run_id})
    except Exception as e:
        return cors_500(details=str(e))

def create_throughput_measurement(body):  # noqa: E501
    """Ingest pScheduler throughput (iperf3/nuttcp/ethr) result

     # noqa: E501

    :param measurement_request: 
    :type measurement_request: dict | bytes

    :rtype: Union[Status200OkNoContent, Tuple[Status200OkNoContent, int], Tuple[Status200OkNoContent, int, Dict[str, str]]
    """
    measurement_request = body
    if connexion.request.is_json:
        measurement_request = MeasurementRequest.from_dict(connexion.request.get_json())  # noqa: E501
    err = _ensure_ips(measurement_request)
    if err:
        return cors_400()

    raw = measurement_request.raw
    metrics: List[Metric] = []

    # 1) Try standard iperf3 shape first
    end = raw.get("end", {}) if isinstance(raw, dict) else {}
    sum_recv = end.get("sum_received") or {}
    sum_sent = end.get("sum_sent") or {}
    bits_total = None
    retrans = sum_sent.get("retransmits")

    # 2) If missing, derive bps from summary: { start, end, summary: { throughput-bits, retransmits? } }
    summary = raw.get("summary") or {}
    summary_summary = summary.get("summary") or {}
    bits_total = summary_summary.get("throughput-bits") or summary_summary.get("throughput_bits")
    # try to pick retransmits from summary if available
    if retrans is None:
        r = summary_summary.get("retransmits")
        if r is not None:
            try:
                retrans = float(r)
            except Exception:
                pass

    # metrics assembly
    if bits_total is not None:
        metrics.append(_m("throughput_mbps", float(bits_total) / 1e6, "mbps"))
    if retrans is not None:
        try:
            metrics.append(_m("retransmits", float(retrans), "count"))
        except Exception:
            pass
    #if not metrics:
    #    metrics.append(_m("throughput_result", 1.0 if raw.get("succeeded", True) else 0.0, "count"))

    meas = _mk_measurement(body, test_type="throughput", tool="iperf3/nuttcp/ethr", metrics=metrics)
    try:
        c = DBM.upsert_run(meas, upsert=True)
        return cors_200_no_content(details={"run_id": meas.run_id})
    except Exception as e:
        return cors_500(details=str(e))


def create_trace_measurement(body):  # noqa: E501
    """Ingest pScheduler Trace result

     # noqa: E501

    :param measurement_request: 
    :type measurement_request: dict | bytes

    :rtype: Union[Status200OkNoContent, Tuple[Status200OkNoContent, int], Tuple[Status200OkNoContent, int, Dict[str, str]]
    """
    measurement_request = body
    if connexion.request.is_json:
        measurement_request = MeasurementRequest.from_dict(connexion.request.get_json())  # noqa: E501
    err = _ensure_ips(measurement_request)
    if err:
        return cors_400()

    raw = measurement_request.raw
    paths = raw.get("paths") or []

    # Support both shapes: [ [ {ip,rtt}, ... ] ]  or  [ {ip,rtt}, ... ]
    first_path = []
    if paths and isinstance(paths[0], list):
        first_path = paths[0]
    elif paths and isinstance(paths[0], dict):
        first_path = paths

    # Compute hop_count
    hop_count = len(first_path)

    # Flatten hops with index and rtt_ms if available
    hops_flat = []
    hop_ips = []
    for idx, hop in enumerate(first_path, start=1):
        ip = hop.get("ip")
        rtt_ms = None
        rtt = hop.get("rtt")
        # handle ISO8601 PTxxS or numeric seconds
        if isinstance(rtt, str) and rtt.startswith("PT") and rtt.endswith("S"):
            try:
                rtt_ms = float(rtt[2:-1]) * 1000.0
            except Exception:
                rtt_ms = None
        elif isinstance(rtt, (int, float)):
            # assume seconds
            rtt_ms = float(rtt) * 1000.0
        if ip:
            hop_ips.append(ip)
        hops_flat.append({"idx": idx, "ip": ip, "rtt_ms": rtt_ms})

    metrics = (
        [_m("hop_count", float(hop_count), "count")]
        #if hop_count
        #else [_m("trace_result", 1.0 if raw.get("succeeded", True) else 0.0, "count")]
    )

    # Build measurement (this will merge into aux)
    meas = _mk_measurement(body, test_type="trace", tool="traceroute", metrics=metrics)

    # Inject our flat views into aux for easy querying
    aux = meas.aux or {}
    aux["hops_flat"] = hops_flat          # [{idx, ip, rtt_ms}, ...]
    aux["hop_ips"] = hop_ips              # ["10.0.0.1", "10.0.0.2", ...]
    meas.aux = aux

    try:
        c = DBM.upsert_run(meas, upsert=True)
        DBM.upsert_trace_hops(
            ts=meas.ts,
            run_id=meas.run_id,
            src=meas.src,
            dst=meas.dst,
            hops_flat=hops_flat
        )
        return cors_200_no_content(details={"run_id": meas.run_id})
    except Exception as e:
        return cors_500(details=str(e))
