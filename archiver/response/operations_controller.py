import connexion
from typing import Dict
from typing import Tuple
from typing import Union

from sqlalchemy import text, select

from archiver.common.globals import get_globals
from archiver.db.database_manager import DatabaseManager
from archiver.openapi_server.models.get_health200_response import GetHealth200Response  # noqa: E501
from archiver.openapi_server.models.get_schema200_response import GetSchema200Response  # noqa: E501
from archiver.openapi_server.models.status401_unauthorized import Status401Unauthorized  # noqa: E501
from archiver.openapi_server import util
from archiver.response.cors_response import cors_500

DBM = DatabaseManager.from_config(config=get_globals().config)

# -------- helpers (minimal, no external deps) --------

def _db_health() -> tuple[str, str | None]:
    """
    Returns ("ok"|"down", error_message_or_None).
    """
    try:
        with DBM.SessionLocal() as s:
            s.execute(text("SELECT 1"))
        return "ok", None
    except Exception as e:
        return "down", str(e)

# Optional: centralize known metric descriptions shown in /schema
_METRIC_DESCRIPTIONS = {
    "throughput_mbps": "Throughput (Megabits per second), iperf3/nuttcp/ethr",
    "retransmits":     "TCP retransmissions observed by sender",
    "delay_ms":        "One/two-way latency (OWAMP/TWAMP)",
    "jitter_ms":       "Jitter (ms), IPDV or stddev depending on tool",
    "loss_pct":        "Packet loss percentage",
    "rtt_ms":          "Ping round-trip time (ms)",
    "mtu_bytes":       "Detected path MTU (bytes)",
    "hop_count":       "Traceroute hop count",
    "clock_diff_ms":   "Clock difference between local/remote (ms)",
    "clock_offset_s":  "Remote clock offset (seconds)",
}


def get_health():  # noqa: E501
    """Health/Liveness

     # noqa: E501


    :rtype: Union[GetHealth200Response, Tuple[GetHealth200Response, int], Tuple[GetHealth200Response, int, Dict[str, str]]
    """
    db_status, err = _db_health()

    # Prefer your package version if set; fallback to OpenAPI version/env
    try:
        import archiver as _pkg
        version = getattr(_pkg, "__version__", None) or "1.0.0"
    except Exception:
        version = "1.0.0"

    # Your OpenAPI defines only 200 for /health, so keep HTTP 200 and put db status in body
    resp = GetHealth200Response(status="ok", db=db_status, version=version)
    return resp, 200


def get_schema():  # noqa: E501
    """Metric catalog / minimal schema

     # noqa: E501


    :rtype: Union[GetSchema200Response, Tuple[GetSchema200Response, int], Tuple[GetSchema200Response, int, Dict[str, str]]
    """
    try:
        # Distinct (metric_name, unit) from your measurements table
        # Adjust table/model import if your ORM name differs.
        from archiver.db.models import PsTestResult  # ORM mapped class

        with DBM.SessionLocal() as s:
            rows = s.execute(
                select(PsTestResult.metric_name, PsTestResult.unit).distinct()
            ).all()

        metrics = []
        for name, unit in sorted(rows, key=lambda x: (x[0] or "", x[1] or "")):
            metrics.append({
                "name": name,
                "unit": unit,
                "description": _METRIC_DESCRIPTIONS.get(name)
            })

        # It’s fine if empty (fresh DB) — returns an empty list per schema.
        return GetSchema200Response(metrics=metrics), 200

    except Exception as e:
        return cors_500(details=str(e))
