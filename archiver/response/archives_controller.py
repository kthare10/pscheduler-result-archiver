from datetime import datetime, timezone

from archiver.common.globals import get_globals
from archiver.db.database_manager import DatabaseManager
from archiver.openapi_server.models import Metric
from archiver.openapi_server.models.measurement import Measurement  # noqa: E501
from archiver.response.cors_response import cors_500, cors_404

DBM = DatabaseManager.from_config(config=get_globals().config)

def _dt_key(ts):
    # robust sort key for rows that might have NULL ts
    if ts is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def get_measurement(run_id, x_request_id=None):  # noqa: E501
    """Fetch a previously ingested run

     # noqa: E501

    :param run_id: 
    :type run_id: str
    :param x_request_id: Optional request correlation id
    :type x_request_id: str

    :rtype: Union[Measurement, Tuple[Measurement, int], Tuple[Measurement, int, Dict[str, str]]
    """
    try:
        # expects your DB manager to provide all rows for a run_id
        # each row is one metric for that run
        rows = DBM.fetch_run_rows(run_id)  # -> Iterable[PsTestResult]
    except Exception as e:
        return cors_500(details=str(e))

    if not rows:
        return cors_404(details=f"Run not found: {run_id}")

    # newest row provides canonical run-level fields
    newest = max(rows, key=lambda r: _dt_key(getattr(r, "ts", None)))

    # latest value per metric_name
    latest_by_metric = {}
    for r in rows:
        mname = getattr(r, "metric_name", None)
        if not mname:
            continue
        ts = getattr(r, "ts", None)
        prev = latest_by_metric.get(mname)
        if (prev is None) or (_dt_key(ts) > _dt_key(prev["ts"])):
            latest_by_metric[mname] = {
                "ts": ts,
                "value": getattr(r, "metric_value", None),
                "unit": getattr(r, "unit", None),
            }

    metrics = []
    for mname, md in sorted(latest_by_metric.items(), key=lambda kv: kv[0]):
        if md["unit"] is None:
            metrics.append(Metric(name=mname, value=md["value"]))
        else:
            metrics.append(Metric(name=mname, value=md["value"], unit=md["unit"]))

    # pick newest non-null aux for drilldown
    aux_payload = None
    for r in sorted(rows, key=lambda x: _dt_key(getattr(x, "ts", None)), reverse=True):
        aux = getattr(r, "aux", None)
        if aux is not None:
            aux_payload = aux
            break

    meas = Measurement(
        ts=getattr(newest, "ts", None),
        run_id=run_id,
        test_type=getattr(newest, "test_type", None),
        tool=getattr(newest, "tool", None),
        src=getattr(newest, "src", None),
        dst=getattr(newest, "dst", None),
        status=getattr(newest, "status", None),
        duration_s=getattr(newest, "duration_s", None),
        metrics=metrics,
        aux=aux_payload,
    )
    return meas, 200
