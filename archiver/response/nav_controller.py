import json
import logging
from datetime import datetime, timezone

import connexion

from archiver.common.globals import get_globals
from archiver.db.database_manager import DatabaseManager
from archiver.response.cors_response import cors_200, cors_400, cors_200_no_content, cors_500, cors_response

from flask import request, Response

logger = logging.getLogger(__name__)

DBM = DatabaseManager.from_config(config=get_globals().config)

_INDENT = 4


def _parse_iso(s):
    if not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def create_nav_measurement(body):  # noqa: E501
    """Ingest a batch of vessel navigation data points."""
    if connexion.request.is_json:
        body = connexion.request.get_json()

    points = body.get("points")
    if not points or not isinstance(points, list):
        return cors_400(details="'points' array is required and must be non-empty")

    if len(points) > 1000:
        return cors_400(details="Maximum 1000 points per request")

    rows = []
    for i, pt in enumerate(points):
        ts = _parse_iso(pt.get("ts"))
        vessel_id = pt.get("vessel_id")
        if not ts:
            return cors_400(details=f"points[{i}].ts is required and must be valid ISO 8601")
        if not vessel_id:
            return cors_400(details=f"points[{i}].vessel_id is required")

        row = {
            "ts": ts,
            "vessel_id": vessel_id,
            "latitude": pt.get("latitude"),
            "longitude": pt.get("longitude"),
            "altitude_m": pt.get("altitude_m"),
            "fix_quality": pt.get("fix_quality"),
            "num_satellites": pt.get("num_satellites"),
            "hdop": pt.get("hdop"),
            "heading_true": pt.get("heading_true"),
            "motion_status": pt.get("motion_status"),
            "roll_deg": pt.get("roll_deg"),
            "pitch_deg": pt.get("pitch_deg"),
            "heave_m": pt.get("heave_m"),
            "rel_wind_speed_kts": pt.get("rel_wind_speed_kts"),
            "rel_wind_dir_deg": pt.get("rel_wind_dir_deg"),
            "true_wind_speed_kts": pt.get("true_wind_speed_kts"),
            "true_wind_dir_deg": pt.get("true_wind_dir_deg"),
            "pressure_hpa": pt.get("pressure_hpa"),
            "humidity_pct": pt.get("humidity_pct"),
            "aux": pt.get("aux"),
        }
        rows.append(row)

    try:
        counts = DBM.upsert_nav_data(rows)
        return cors_200_no_content(details={"points_processed": counts.inserted})
    except Exception:
        logger.exception("Failed to upsert nav data batch")
        return cors_500(details="Internal server error")


def get_nav_data(start=None, end=None, vessel_id=None, limit=1000):  # noqa: E501
    """Retrieve vessel navigation data by time range."""
    start_dt = _parse_iso(start)
    end_dt = _parse_iso(end)

    if limit is not None:
        limit = min(int(limit), 10000)
    else:
        limit = 1000

    try:
        rows = DBM.fetch_nav_data(
            start=start_dt,
            end=end_dt,
            vessel_id=vessel_id,
            limit=limit,
        )
        data = [r.to_dict() for r in rows]
        response_body = {"data": data, "size": len(data)}
        body_str = json.dumps(response_body, indent=_INDENT, sort_keys=True, default=str)
        return cors_response(
            req=request,
            status_code=200,
            body=body_str,
        )
    except Exception:
        logger.exception("Failed to fetch nav data")
        return cors_500(details="Internal server error")
