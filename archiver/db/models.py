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


class NavData(Base):
    """
    Navigation data from NMEA 0183 sentences (GPS position, heading, roll/pitch/heave).
    Composite PK (ts, vessel_id) enables idempotent upserts and satisfies
    TimescaleDB hypertable uniqueness rules.
    """
    __tablename__ = "nav_data"

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    vessel_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # GPS position ($INGGA)
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    altitude_m: Mapped[Optional[float]] = mapped_column(Float)
    fix_quality: Mapped[Optional[int]] = mapped_column(Integer)
    num_satellites: Mapped[Optional[int]] = mapped_column(Integer)
    hdop: Mapped[Optional[float]] = mapped_column(Float)

    # Heading ($INHDT)
    heading_true: Mapped[Optional[float]] = mapped_column(Float)

    # Motion status ($PSXN,20)
    motion_status: Mapped[Optional[int]] = mapped_column(Integer)

    # Roll/pitch/heave ($PSXN,23)
    roll_deg: Mapped[Optional[float]] = mapped_column(Float)
    pitch_deg: Mapped[Optional[float]] = mapped_column(Float)
    heave_m: Mapped[Optional[float]] = mapped_column(Float)

    # Wind data ($RELWS / $RELWD)
    rel_wind_speed_kts: Mapped[Optional[float]] = mapped_column(Float)
    rel_wind_dir_deg: Mapped[Optional[float]] = mapped_column(Float)
    true_wind_speed_kts: Mapped[Optional[float]] = mapped_column(Float)
    true_wind_dir_deg: Mapped[Optional[float]] = mapped_column(Float)

    # Environmental data (bare values after $RELWD)
    pressure_hpa: Mapped[Optional[float]] = mapped_column(Float)
    humidity_pct: Mapped[Optional[float]] = mapped_column(Float)

    # Raw details
    aux: Mapped[Optional[dict]] = mapped_column(JSONB)

    __table_args__ = (
        PrimaryKeyConstraint("ts", "vessel_id", name="nav_data_pkey"),
        Index("idx_nav_ts", "ts", postgresql_using="btree"),
        Index("idx_nav_vessel", "vessel_id", postgresql_using="btree"),
        Index("idx_nav_latlon", "latitude", "longitude", postgresql_using="btree"),
    )

    def __repr__(self) -> str:
        return (f"NavData(ts={self.ts}, vessel_id={self.vessel_id!r}, "
                f"lat={self.latitude}, lon={self.longitude})")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ts": self.ts.isoformat() if self.ts else None,
            "vessel_id": self.vessel_id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude_m": self.altitude_m,
            "fix_quality": self.fix_quality,
            "num_satellites": self.num_satellites,
            "hdop": self.hdop,
            "heading_true": self.heading_true,
            "motion_status": self.motion_status,
            "roll_deg": self.roll_deg,
            "pitch_deg": self.pitch_deg,
            "heave_m": self.heave_m,
            "rel_wind_speed_kts": self.rel_wind_speed_kts,
            "rel_wind_dir_deg": self.rel_wind_dir_deg,
            "true_wind_speed_kts": self.true_wind_speed_kts,
            "true_wind_dir_deg": self.true_wind_dir_deg,
            "pressure_hpa": self.pressure_hpa,
            "humidity_pct": self.humidity_pct,
            "aux": self.aux,
        }
