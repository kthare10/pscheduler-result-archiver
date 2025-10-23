# archiver/db/models.py
from __future__ import annotations

from typing import Optional, Dict, Any
from datetime import datetime

from sqlalchemy import (
    DateTime, Text, Float, Integer, String,
    Index, PrimaryKeyConstraint
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PsTestResult(Base):
    """
    Metric rows from pScheduler tests.
    Composite PK (run_id, metric_name, ts) to:
      - satisfy Timescale hypertable uniqueness rules
      - keep idempotent upserts per (run, metric, timestamp)
    Columns commonly queried by Grafana panels:
      - ts, metric_name, metric_value, src, dst, aux->>'traffic_dir'
    """
    __tablename__ = "ps_test_results"

    # time/identity
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    run_id: Mapped[str] = mapped_column(Text, nullable=False)
    metric_name: Mapped[str] = mapped_column(Text, nullable=False)

    # labels
    test_type: Mapped[str] = mapped_column(Text, nullable=False)
    tool: Mapped[str] = mapped_column(Text, nullable=False)
    src: Mapped[Optional[str]] = mapped_column(Text)
    dst: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[Optional[str]] = mapped_column(Text)
    duration_s: Mapped[Optional[float]] = mapped_column(Float)

    # value
    metric_value: Mapped[Optional[float]] = mapped_column(Float)
    unit: Mapped[Optional[str]] = mapped_column(Text)

    # raw details / drilldown
    aux: Mapped[Optional[dict]] = mapped_column(JSONB)

    __table_args__ = (
        # Timescale requires 'ts' (partition column) in all unique constraints
        PrimaryKeyConstraint("run_id", "metric_name", "ts", name="ps_test_results_pkey"),
        # Helpful indexes for dashboards
        Index("idx_ps_ts", "ts", postgresql_using="btree"),
        Index("idx_ps_metric", "metric_name", postgresql_using="btree"),
        Index("idx_ps_src_dst", "src", "dst", postgresql_using="btree"),
        # Fast filter by traffic_dir stored in aux JSONB
        Index("idx_ps_aux_traffic_dir",
              (aux.op("->>")("traffic_dir")),
              postgresql_using="btree"),
        # General JSONB GIN for other drilldown queries
        Index("idx_ps_aux_gin", "aux", postgresql_using="gin"),
    )


class PsTraceHop(Base):
    """
    One row per hop for a given traceroute run (optional side table).
    Primary key is (run_id, hop_idx) so re-ingesting the same run is idempotent.
    'ts' is the measurement timestamp (UTC).
    """
    __tablename__ = "ps_trace_hops"

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    src: Mapped[Optional[str]] = mapped_column(String)
    dst: Mapped[Optional[str]] = mapped_column(String)
    hop_idx: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-based
    hop_ip: Mapped[str] = mapped_column(String, nullable=False)
    rtt_ms: Mapped[Optional[float]] = mapped_column(Float)

    __table_args__ = (
        PrimaryKeyConstraint("run_id", "hop_idx", name="pk_ps_trace_hops"),
        Index("idx_ps_th_ts", "ts"),
        Index("idx_ps_th_ip", "hop_ip"),
        Index("idx_ps_th_src_dst", "src", "dst"),
    )

    def __repr__(self) -> str:
        return (f"PsTraceHop(run_id={self.run_id!r}, hop_idx={self.hop_idx}, "
                f"hop_ip={self.hop_ip!r}, rtt_ms={self.rtt_ms}, ts={self.ts})")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ts": self.ts.isoformat(),
            "run_id": self.run_id,
            "src": self.src,
            "dst": self.dst,
            "hop_idx": self.hop_idx,
            "hop_ip": self.hop_ip,
            "rtt_ms": self.rtt_ms,
        }
