# archiver_client.py
# Client for pscheduler-result-archiver (OpenAPI 3.0.0)
from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Any, Dict, Literal, Mapping, MutableMapping, Optional, Tuple, Union

import requests
from requests import Session, Response


# ----------------------------- Models (typed) -----------------------------

Direction = Literal["forward", "reverse"]


@dataclass
class NodeRef:
    """components/schemas/NodeRef"""
    ip: str
    name: Optional[str] = None


@dataclass
class MeasurementRequest:
    """
    components/schemas/MeasurementRequest
    NOTE: Server will generate ts/run_id if omitted.
    """
    src: NodeRef
    dst: NodeRef
    raw: Dict[str, Any]
    direction: Optional[Direction] = None
    ts: Optional[str] = None            # RFC3339/ISO8601
    run_id: Optional[str] = None

    def to_payload(self) -> Dict[str, Any]:
        d = {
            "src": asdict(self.src),
            "dst": asdict(self.dst),
            "raw": self.raw,
        }
        if self.direction:
            d["direction"] = self.direction
        if self.ts:
            d["ts"] = self.ts
        if self.run_id:
            d["run_id"] = self.run_id
        return d


# ----------------------------- Errors -----------------------------

class ArchiverError(Exception):
    """Base error for archiver_client failures."""
    def __init__(self, message: str, *, status: Optional[int] = None, payload: Optional[Any] = None):
        super().__init__(message)
        self.status = status
        self.payload = payload


class ArchiverHTTPError(ArchiverError):
    """HTTP status outside of 2xx."""
    pass


# ----------------------------- Client -----------------------------

class ArchiverClient:
    """
    Minimal, production-friendly archiver_client for pscheduler-result-archiver.
    - Supports Bearer and/or X-API-Key auth
    - Small retry helper for transient 5xx/connection issues
    """

    def __init__(
        self,
        base_url: str = os.getenv("ARCHIVER_BASE_URL", "http://localhost:8080"),
        bearer_token: Optional[str] = os.getenv("ARCHIVER_BEARER"),
        api_key: Optional[str] = os.getenv("ARCHIVER_API_KEY"),
        *,
        timeout: float = 15.0,
        session: Optional[Session] = None,
        user_agent: str = "archiver-archiver_client/1.0.0",
        retries: int = 2,
        retry_backoff_seconds: float = 0.5,
    ):
        self.base_url = base_url.rstrip("/")
        self.bearer_token = bearer_token
        self.api_key = api_key
        self.timeout = timeout
        self.session = session or requests.Session()
        self.user_agent = user_agent
        self.retries = max(0, retries)
        self.retry_backoff_seconds = retry_backoff_seconds

    # ---------- public: Operations ----------

    def get_health(self) -> Dict[str, Any]:
        """
        GET /health  -> { status: "ok", db: "ok|degraded|down", version: "..." }
        """
        return self._request_json("GET", "/health")

    def get_schema(self, *, request_id: Optional[str] = None) -> Dict[str, Any]:
        """
        GET /schema -> { metrics: [{name, unit, description?}, ...] }
        """
        return self._request_json("GET", "/schema", headers=self._id_header(request_id))

    # ---------- public: Archives ----------

    def get_archive(
        self,
        run_id: str,
        *,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        GET /archives/{run_id}
        """
        path = f"/archives/{self._url_escape(run_id)}"
        return self._request_json("GET", path, headers=self._id_header(request_id))

    # ---------- public: Measurements (create*) ----------

    def create_clock_measurement(
        self,
        body: MeasurementRequest,
        *,
        upsert: bool = True,
        request_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._post_measurement("/measurements/clock", body, upsert, request_id, idempotency_key)

    def create_latency_measurement(
        self,
        body: MeasurementRequest,
        *,
        upsert: bool = True,
        request_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._post_measurement("/measurements/latency", body, upsert, request_id, idempotency_key)

    def create_rtt_measurement(
        self,
        body: MeasurementRequest,
        *,
        upsert: bool = True,
        request_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._post_measurement("/measurements/rtt", body, upsert, request_id, idempotency_key)

    def create_throughput_measurement(
        self,
        body: MeasurementRequest,
        *,
        upsert: bool = True,
        request_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._post_measurement("/measurements/throughput", body, upsert, request_id, idempotency_key)

    def create_mtu_measurement(
        self,
        body: MeasurementRequest,
        *,
        upsert: bool = True,
        request_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._post_measurement("/measurements/mtu", body, upsert, request_id, idempotency_key)

    def create_trace_measurement(
        self,
        body: MeasurementRequest,
        *,
        upsert: bool = True,
        request_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._post_measurement("/measurements/trace", body, upsert, request_id, idempotency_key)

    # --------------------------- internal helpers ---------------------------

    def _post_measurement(
        self,
        path: str,
        body: MeasurementRequest,
        upsert: bool,
        request_id: Optional[str],
        idempotency_key: Optional[str],
    ) -> Dict[str, Any]:
        params = {"upsert": "true" if upsert else "false"}
        headers = self._id_header(request_id)
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return self._request_json("POST", path, params=params, json_body=body.to_payload(), headers=headers)

    def _request_json(
        self,
        method: Literal["GET", "POST"],
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json_body: Optional[Mapping[str, Any]] = None,
        headers: Optional[MutableMapping[str, str]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        hdrs = self._auth_headers()
        hdrs["Accept"] = "application/json"
        hdrs["User-Agent"] = self.user_agent
        if headers:
            hdrs.update(headers)

        # Simple retry loop for transient network/5xx
        last_exc: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                resp: Response = self.session.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers=hdrs,
                    timeout=self.timeout,
                )
                if 200 <= resp.status_code < 300:
                    # Some 200/201 responses may have empty bodies; normalize to {}
                    if resp.content and resp.headers.get("Content-Type", "").startswith("application/json"):
                        return resp.json()  # type: ignore[return-value]
                    return {}
                else:
                    # Try to parse server error payload
                    payload = None
                    try:
                        payload = resp.json()
                    except Exception:
                        payload = resp.text[:500]
                    raise ArchiverHTTPError(
                        f"{method} {url} -> HTTP {resp.status_code}",
                        status=resp.status_code,
                        payload=payload,
                    )
            except (requests.ConnectionError, requests.Timeout) as e:
                last_exc = e
                if attempt < self.retries:
                    time.sleep(self.retry_backoff_seconds * (2 ** attempt))
                    continue
                raise ArchiverError(f"Request failed after {self.retries + 1} attempts: {e}") from e
        # Shouldn’t reach; safeguard:
        if last_exc:
            raise ArchiverError(f"Request failed: {last_exc}") from last_exc
        raise ArchiverError("Unknown archiver_client error")

    def _auth_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    @staticmethod
    def _id_header(request_id: Optional[str]) -> Dict[str, str]:
        return {"X-Request-ID": request_id or str(uuid.uuid4())}

    @staticmethod
    def _url_escape(s: str) -> str:
        # Avoid bringing in urllib just for one field; this is fine for run_id tokens we control.
        return s.replace(" ", "%20")
