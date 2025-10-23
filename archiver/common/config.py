#!/usr/bin/env python3
"""
config.py

Typed loader for the pscheduler-result-archiver configuration YAML.

What's here
-----------
- RuntimeConfig: port, etc.
- LoggingConfig: rotates files via LogHelper
- DatabaseConfig:
    * Env-first DSN (ARCHIVER_DSN / DATABASE_DSN / POSTGRES_DSN)
    * Optional fallback DSN in YAML
    * Or discrete fields (host/user/password/port/database) with SSL + pool tuning
    * Helpers:
        - .dsn: resolved SQLAlchemy DSN (postgresql+psycopg://…)
        - .sqlalchemy_engine_kwargs(): pool settings for create_engine()

Usage:
    cfg = Config.load_from_file("config.yaml")
    cfg.logging.apply()

    # Build a SQLAlchemy engine:
    from sqlalchemy import create_engine
    engine = create_engine(cfg.database.dsn, **cfg.database.sqlalchemy_engine_kwargs())

    # Or pass DSN to your DatabaseManager(..., dsn=cfg.database.dsn)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional
import os
import yaml

from archiver.utils.log_helper import LogHelper

DEFAULT_CONFIG_PATH = os.getenv("APP_CONFIG_PATH", "config.yaml")


# -------------------- helpers --------------------

def _bool(x: Any) -> bool:
    if isinstance(x, bool):
        return x
    if isinstance(x, str):
        return x.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(x)


# -------------------- logging --------------------

@dataclass
class LoggingConfig:
    log_directory: Path
    log_file: str
    metrics_log_file: str
    log_level: str = "INFO"
    log_retain: int = 5
    log_size: int = 5_000_000
    logger: str = "archiver"

    def apply(self) -> None:
        """Set up rotating file handlers based on this config."""
        LogHelper.make_logger(
            log_dir=self.log_directory,
            log_file=self.log_file,
            log_level=self.log_level,
            log_retain=self.log_retain,
            log_size=self.log_size,
            logger=self.logger,
        )


# -------------------- runtime --------------------

@dataclass
class RuntimeConfig:
    port: int = 3500
    bearer_token: str = ""


# -------------------- database --------------------

@dataclass
class SSLConfig:
    mode: str = "disable"            # disable | require | verify-ca | verify-full
    root_cert: Optional[str] = None  # path to CA cert (when verify-*)


@dataclass
class PoolConfig:
    size: int = 10                   # pool_size
    max_overflow: int = 20           # extra connections
    timeout_s: int = 30              # pool_timeout
    recycle_s: int = 1800            # pool_recycle


@dataclass
class DatabaseConfig:
    # selection
    use_env_dsn: bool = True
    dsn_fallback: Optional[str] = None

    # discrete fields (used if env DSN missing and dsn_fallback not set)
    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    password: Optional[str] = None   # can be overridden by ARCHIVER_DB_PASSWORD
    database: str = "postgres"

    # options
    ssl: SSLConfig = field(default_factory=SSLConfig)
    pool: PoolConfig = field(default_factory=PoolConfig)
    create_tables: bool = False      # dev-only

    # -------- computed --------
    @property
    def dsn(self) -> str:
        """
        Resolve an SQLAlchemy DSN in the following precedence:
          1) ARCHIVER_DSN / DATABASE_DSN / POSTGRES_DSN (when use_env_dsn = True)
          2) dsn_fallback from config
          3) build from discrete fields (+ optional SSL query)
        """
        if self.use_env_dsn:
            env_dsn = (
                os.getenv("ARCHIVER_DSN")
                or os.getenv("DATABASE_DSN")
                or os.getenv("POSTGRES_DSN")
            )
            if env_dsn:
                return env_dsn

        if self.dsn_fallback:
            return self.dsn_fallback

        pwd = os.getenv("ARCHIVER_DB_PASSWORD", self.password or "")
        query_parts = []

        # SSL
        if self.ssl and self.ssl.mode and self.ssl.mode != "disable":
            query_parts.append(f"sslmode={self.ssl.mode}")
            if self.ssl.root_cert:
                query_parts.append(f"sslrootcert={self.ssl.root_cert}")

        q = ("?" + "&".join(query_parts)) if query_parts else ""

        return (
            f"postgresql+psycopg://{self.user}:{pwd}@{self.host}:{self.port}/{self.database}{q}"
        )

    def sqlalchemy_engine_kwargs(self) -> Dict[str, Any]:
        """
        Recommended kwargs for sqlalchemy.create_engine(...)
        """
        return {
            "pool_size": self.pool.size,
            "max_overflow": self.pool.max_overflow,
            "pool_timeout": self.pool.timeout_s,
            "pool_recycle": self.pool.recycle_s,
            "pool_pre_ping": True,
            "future": True,
        }


# -------------------- root config --------------------

@dataclass
class Config:
    runtime: RuntimeConfig
    logging: LoggingConfig
    database: DatabaseConfig

    # ----------- loader -----------
    @classmethod
    def load_from_file(cls, path: str | Path = DEFAULT_CONFIG_PATH) -> "Config":
        data = yaml.safe_load(Path(path).read_text())
        if not isinstance(data, dict):
            raise ValueError("Top-level YAML must be a mapping")

        # runtime
        runtime_raw = data.get("runtime") or {}
        runtime = RuntimeConfig(
            port=int(runtime_raw.get("port") or 3500),
            bearer_token=runtime_raw.get("bearer_token", "abcd1234")
        )

        # logging
        log_raw = data.get("logging") or {}
        logging_cfg = LoggingConfig(
            log_directory=Path(log_raw.get("log-directory") or "logs"),
            log_file=log_raw.get("log-file") or "archiver.log",
            metrics_log_file=log_raw.get("metrics-log-file") or "metrics.log",
            log_level=(log_raw.get("log-level") or "INFO").upper(),
            log_retain=int(log_raw.get("log-retain") or 5),
            log_size=int(log_raw.get("log-size") or 5_000_000),
            logger=log_raw.get("logger") or "archiver",
        )

        # database
        db_raw = data.get("database") or {}
        ssl_raw = db_raw.get("ssl") or {}
        pool_raw = db_raw.get("pool") or {}

        db_cfg = DatabaseConfig(
            use_env_dsn=_bool(db_raw.get("use-env-dsn", True)),
            dsn_fallback=db_raw.get("dsn"),
            host=db_raw.get("host", "localhost"),
            port=int(db_raw.get("port", 5432)),
            user=db_raw.get("user", "postgres"),
            password=db_raw.get("password"),  # may be None; env override applied in .dsn
            database=db_raw.get("database", "postgres"),
            ssl=SSLConfig(
                mode=ssl_raw.get("mode", "disable"),
                root_cert=ssl_raw.get("root-cert"),
            ),
            pool=PoolConfig(
                size=int(pool_raw.get("size", 10)),
                max_overflow=int(pool_raw.get("max-overflow", 20)),
                timeout_s=int(pool_raw.get("timeout-s", 30)),
                recycle_s=int(pool_raw.get("recycle-s", 1800)),
            ),
            create_tables=_bool(db_raw.get("create-tables", False)),
        )

        return cls(runtime=runtime, logging=logging_cfg, database=db_cfg)


# -------------------- module-level helpers --------------------

@lru_cache(maxsize=1)
def get_cfg(path: str | Path = DEFAULT_CONFIG_PATH) -> Config:
    """Load once, reuse everywhere."""
    return Config.load_from_file(path)


def init_cfg(path: str | Path) -> Config:
    """Call this once at startup if you want a non-default path or to reload."""
    get_cfg.cache_clear()
    return get_cfg(path)
