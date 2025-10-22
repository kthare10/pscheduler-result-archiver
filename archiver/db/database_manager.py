# archiver/db/database_manager_orm.py
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, List, Tuple, Optional, Any, Dict
from datetime import datetime

from sqlalchemy import create_engine, update, text, select, desc
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .models import Base, PsTestResult
from ..common.config import Config


class ConflictError(Exception):
    """Raised when upsert=False and duplicates exist for (run_id, metric_name, ts)."""


class DatabaseError(Exception):
    """Generic DB error."""


@dataclass(frozen=True)
class UpsertCounts:
    inserted: int = 0
    updated: int = 0


class DatabaseManager:
    """
    SQLAlchemy ORM manager around Postgres/Timescale `ps_test_results`.

    DSN examples:
      postgresql+psycopg://user:pass@host:5432/perfsonar
    """

    def __init__(self, config: Config) -> None:
        self.engine = create_engine(
            config.database.dsn, **config.database.sqlalchemy_engine_kwargs()
        )
        self.SessionLocal = sessionmaker(bind=self.engine, class_=Session, expire_on_commit=False, future=True)

        # Create tables (ORM) if missing
        Base.metadata.create_all(self.engine)

        # Optionally ensure Timescale + hypertable (safe to run repeatedly)
        if getattr(config.database, "create_tables", False):
            self._ensure_timescale_and_hypertable()

    @classmethod
    def from_config(cls, config) -> "DatabaseManager":
        return cls(config=config)

    # ---------- public API ----------

    def upsert_run(self, run: Any, *, upsert: bool = True) -> UpsertCounts:
        """
        Insert/Upsert one run (multiple metrics).
        When upsert=False, perform INSERT ... DO NOTHING and raise ConflictError if any row existed.
        """
        rows = self._rows_from_run(run)
        if not rows:
            return UpsertCounts(0, 0)

        try:
            with self.SessionLocal.begin() as s:
                if upsert:
                    return self._upsert_rows(s, rows)
                else:
                    return self._insert_only_rows(s, rows)
        except ConflictError:
            raise
        except Exception as e:
            raise DatabaseError(str(e)) from e

    def upsert_bulk(
        self,
        runs: Iterable[Any],
        *,
        upsert: bool = True
    ) -> List[Tuple[str, UpsertCounts, Optional[str], str]]:
        """
        Returns [(run_id, counts, error_message_or_None, status)]
        where status ∈ {"ok","conflict","invalid","error"}.
        """
        results: list[tuple[str, UpsertCounts, Optional[str], str]] = []
        for run in runs:
            run_id = getattr(run, "run_id", None) or "unknown"
            try:
                if not getattr(run, "metrics", None):
                    results.append((run_id, UpsertCounts(), "metrics[] is required and must be non-empty", "invalid"))
                    continue
                counts = self.upsert_run(run, upsert=upsert)
                results.append((run_id, counts, None, "ok"))
            except ConflictError as ce:
                results.append((run_id, UpsertCounts(), str(ce), "conflict"))
            except Exception as e:
                results.append((run_id, UpsertCounts(), str(e), "error"))
        return results

    # ---------- internal SQL ops ----------

    def _upsert_rows(self, s: Session, rows: list[Dict[str, Any]]) -> UpsertCounts:
        """
        True UPSERT using PostgreSQL. We probe with DO NOTHING (returning) to count inserts,
        and issue UPDATE for existing rows. Conflict target must include (run_id, metric_name, ts).
        """
        inserted = 0
        updated = 0

        for r in rows:
            # Attempt insert; count as inserted if it returns a row.
            probe = (
                pg_insert(PsTestResult.__table__)
                .values(**r)
                .on_conflict_do_nothing()
                .returning(PsTestResult.__table__.c.run_id)
            )
            probe_res = s.execute(probe).fetchone()
            if probe_res:
                inserted += 1
            else:
                # Row exists for (run_id, metric_name, ts) -> update value & labels
                upd = (
                    update(PsTestResult)
                    .where(
                        (PsTestResult.run_id == r["run_id"]) &
                        (PsTestResult.metric_name == r["metric_name"]) &
                        (PsTestResult.ts == r["ts"])
                    )
                    .values(
                        # DO NOT change keys (run_id, metric_name, ts)
                        test_type=r["test_type"],
                        tool=r["tool"],
                        src=r["src"],
                        dst=r["dst"],
                        status=r["status"],
                        duration_s=r["duration_s"],
                        metric_value=r["metric_value"],
                        unit=r["unit"],
                        aux=r["aux"],
                    )
                )
                res = s.execute(upd)
                updated += res.rowcount or 0

        return UpsertCounts(inserted=inserted, updated=updated)

    def _insert_only_rows(self, s: Session, rows: list[Dict[str, Any]]) -> UpsertCounts:
        """
        INSERT ... DO NOTHING. If any conflicts occurred, raise ConflictError so the controller can return 409.
        Conflict target is PK (run_id, metric_name, ts).
        """
        stmt = (
            pg_insert(PsTestResult.__table__)
            .values(rows)
            .on_conflict_do_nothing()
            .returning(PsTestResult.run_id)
        )
        result = s.execute(stmt)
        inserted = len(result.fetchall())
        conflicts = len(rows) - inserted
        if conflicts > 0:
            raise ConflictError(
                f"{conflicts} duplicate metric row(s) for run_id={rows[0]['run_id']} (PK: run_id, metric_name, ts)"
            )
        return UpsertCounts(inserted=inserted, updated=0)

    # ---------- row builder ----------

    @staticmethod
    def _rows_from_run(run: Any) -> list[Dict[str, Any]]:
        """
        Convert a Connexion-generated Measurement (former IngestRun) to a list of dict rows.
        Ensures aux is JSONB-serializable.
        """
        ts = getattr(run, "ts", None)
        # Accept ISO 8601 strings for ts from the REST payload
        if isinstance(ts, str):
            # Let SQLAlchemy/psycopg handle tz-aware ISO strings if present;
            # but we try to parse first to catch obvious issues.
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                # leave as string; the DB driver may still coerce or raise (better error upstream)
                pass

        run_id = getattr(run, "run_id", None)
        test_type = getattr(run, "test_type", None)
        tool = getattr(run, "tool", None)
        src = getattr(run, "src", None)
        dst = getattr(run, "dst", None)
        status = getattr(run, "status", None)
        duration_s = getattr(run, "duration_s", None)
        metrics = getattr(run, "metrics", None) or []
        aux_obj = getattr(run, "aux", None)

        # ensure JSON serializable (convert to plain dict)
        aux_jsonb = None
        if aux_obj is not None:
            aux_jsonb = json.loads(json.dumps(aux_obj))

        out: list[Dict[str, Any]] = []
        for m in metrics:
            name = getattr(m, "name", None)
            value = getattr(m, "value", None)
            unit = getattr(m, "unit", None)
            if name is None or value is None:
                continue
            out.append(
                {
                    "ts": ts,
                    "run_id": run_id,
                    "test_type": test_type,
                    "tool": tool,
                    "src": src,
                    "dst": dst,
                    "status": status,
                    "duration_s": duration_s,
                    "metric_name": name,
                    "metric_value": float(value),
                    "unit": unit,
                    "aux": aux_jsonb,
                }
            )
        return out

    # ---------- reads / health / metadata ----------

    def fetch_run_rows(self, run_id: str) -> List[PsTestResult]:
        """Return all rows for a given run_id, newest first."""
        with self.SessionLocal() as s:
            stmt = (
                select(PsTestResult)
                .where(PsTestResult.run_id == run_id)
                .order_by(desc(PsTestResult.ts))
            )
            return list(s.execute(stmt).scalars().all())

    def check_health(self) -> tuple[str, str | None]:
        """
        Returns (db_status, error_message).
        db_status ∈ {"ok", "down"}.
        """
        try:
            with self.SessionLocal() as s:
                s.execute(text("SELECT 1"))
            return "ok", None
        except Exception as e:
            return "down", str(e)

    def get_metric_catalog(self, limit: int | None = None) -> list[dict]:
        """
        Returns [{'name': <metric_name>, 'unit': <unit or None>, 'description': <str>}, ...]
        Distinct by (metric_name, unit). Optionally limited.
        """
        DESCR = {
            "throughput_mbps": "Measured throughput from iperf3/nuttcp/ethr (Megabits per second)",
            "retransmits":     "Sender TCP retransmissions observed by iperf3",
            "rtt_ms":          "Round-trip time (ping), milliseconds",
            "delay_ms":        "One-way or two-way delay (owamp/twping), milliseconds",
            "loss_pct":        "Packet loss percentage",
            "mtu_bytes":       "Detected MTU for path, bytes",
            "hop_count":       "Traceroute hop count",
        }

        with self.SessionLocal() as s:
            stmt = (
                select(PsTestResult.metric_name, PsTestResult.unit)
                .distinct()
                .order_by(PsTestResult.metric_name.asc(), PsTestResult.unit.asc())
            )
            if limit:
                stmt = stmt.limit(limit)
            rows = s.execute(stmt).all()

        catalog = []
        for name, unit in rows:
            catalog.append({
                "name": name,
                "unit": unit,
                "description": DESCR.get(name)
            })
        return catalog

    def upsert_trace_hops(self, ts, run_id, src, dst, hops_flat: list[dict]):
        """
        Optional helper when you store per-hop rows in ps_trace_hops.
        hops_flat items: {'idx': int, 'ip': 'x.x.x.x'|'::', 'rtt_ms': float?}
        """
        from sqlalchemy.dialects.postgresql import insert
        from .models import PsTraceHop

        with self.SessionLocal.begin() as s:
            for h in hops_flat:
                ip = h.get("ip")
                if not ip:
                    continue
                stmt = (
                    insert(PsTraceHop)
                    .values(ts=ts, run_id=run_id, src=src, dst=dst,
                            hop_idx=h["idx"], hop_ip=ip, rtt_ms=h.get("rtt_ms"))
                    .on_conflict_do_update(
                        index_elements=[PsTraceHop.run_id, PsTraceHop.hop_idx],
                        set_={"ts": ts, "src": src, "dst": dst, "hop_ip": ip, "rtt_ms": h.get("rtt_ms")}
                    )
                )
                s.execute(stmt)

    # ---------- infra helpers ----------

    def _ensure_timescale_and_hypertable(self) -> None:
        """
        Best-effort: enable extension and create hypertable on ps_test_results(ts).
        Safe to run multiple times.
        """
        with self.engine.begin() as conn:
            # Timescale extension
            conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS timescaledb;")
            # Hypertable (requires PKs/unique indexes to include ts — already handled in models.py)
            conn.exec_driver_sql(
                "SELECT create_hypertable('ps_test_results','ts', if_not_exists => TRUE);"
            )
