"""Tests for archiver.common.config — startup validation and DSN resolution."""
import os
import pytest
import tempfile
from pathlib import Path

from archiver.common.config import Config


def _write_config(tmp_path: Path, runtime_block: str = "", db_block: str = "") -> Path:
    cfg = tmp_path / "config.yml"
    cfg.write_text(f"""
runtime:
  port: 3500
  {runtime_block}

logging:
  log-directory: {tmp_path / 'logs'}
  log-file: test.log
  metrics-log-file: metrics.log
  log-level: DEBUG
  log-retain: 1
  log-size: 1000
  logger: archiver

database:
  use-env-dsn: true
  {db_block}
""")
    return cfg


class TestBearerTokenValidation:
    """Config must reject insecure bearer tokens at startup."""

    def test_rejects_empty_token(self, tmp_path):
        cfg_path = _write_config(tmp_path, runtime_block="bearer_token: ''")
        old = os.environ.pop("ARCHIVER_BEARER_TOKEN", None)
        try:
            with pytest.raises(ValueError, match="bearer_token is missing or insecure"):
                Config.load_from_file(cfg_path)
        finally:
            if old is not None:
                os.environ["ARCHIVER_BEARER_TOKEN"] = old

    def test_rejects_changeme(self, tmp_path):
        cfg_path = _write_config(tmp_path, runtime_block="bearer_token: changeme")
        old = os.environ.pop("ARCHIVER_BEARER_TOKEN", None)
        try:
            with pytest.raises(ValueError, match="bearer_token is missing or insecure"):
                Config.load_from_file(cfg_path)
        finally:
            if old is not None:
                os.environ["ARCHIVER_BEARER_TOKEN"] = old

    def test_rejects_env_var_placeholder(self, tmp_path):
        cfg_path = _write_config(tmp_path, runtime_block="bearer_token: ${ARCHIVER_BEARER_TOKEN}")
        old = os.environ.pop("ARCHIVER_BEARER_TOKEN", None)
        try:
            with pytest.raises(ValueError, match="bearer_token is missing or insecure"):
                Config.load_from_file(cfg_path)
        finally:
            if old is not None:
                os.environ["ARCHIVER_BEARER_TOKEN"] = old

    def test_accepts_env_var_override(self, tmp_path):
        cfg_path = _write_config(tmp_path, runtime_block="bearer_token: ''")
        old = os.environ.get("ARCHIVER_BEARER_TOKEN")
        os.environ["ARCHIVER_BEARER_TOKEN"] = "my-secure-token-xyz"
        try:
            cfg = Config.load_from_file(cfg_path)
            assert cfg.runtime.bearer_token == "my-secure-token-xyz"
        finally:
            if old is not None:
                os.environ["ARCHIVER_BEARER_TOKEN"] = old
            else:
                os.environ.pop("ARCHIVER_BEARER_TOKEN", None)

    def test_accepts_strong_token_in_file(self, tmp_path):
        cfg_path = _write_config(tmp_path, runtime_block="bearer_token: a-strong-random-token-here")
        old = os.environ.pop("ARCHIVER_BEARER_TOKEN", None)
        try:
            cfg = Config.load_from_file(cfg_path)
            assert cfg.runtime.bearer_token == "a-strong-random-token-here"
        finally:
            if old is not None:
                os.environ["ARCHIVER_BEARER_TOKEN"] = old


class TestDSNResolution:
    """DatabaseConfig.dsn must resolve in the right precedence order."""

    def test_env_dsn_takes_precedence(self, tmp_path):
        cfg_path = _write_config(tmp_path, runtime_block="bearer_token: secure-tok-123")
        old_bt = os.environ.get("ARCHIVER_BEARER_TOKEN")
        old_dsn = os.environ.get("ARCHIVER_DSN")
        os.environ["ARCHIVER_BEARER_TOKEN"] = "secure-tok-123"
        os.environ["ARCHIVER_DSN"] = "postgresql+psycopg://env:env@envhost:5432/envdb"
        try:
            cfg = Config.load_from_file(cfg_path)
            assert cfg.database.dsn == "postgresql+psycopg://env:env@envhost:5432/envdb"
        finally:
            if old_bt is not None:
                os.environ["ARCHIVER_BEARER_TOKEN"] = old_bt
            else:
                os.environ.pop("ARCHIVER_BEARER_TOKEN", None)
            if old_dsn is not None:
                os.environ["ARCHIVER_DSN"] = old_dsn
            else:
                os.environ.pop("ARCHIVER_DSN", None)

    def test_builds_dsn_from_fields(self, tmp_path):
        db_block = """use-env-dsn: false
  host: myhost
  port: 5433
  user: myuser
  password: mypass
  database: mydb"""
        cfg_path = _write_config(tmp_path, runtime_block="bearer_token: secure-tok-123", db_block=db_block)
        old_bt = os.environ.get("ARCHIVER_BEARER_TOKEN")
        old_dsn = os.environ.pop("ARCHIVER_DSN", None)
        old_pw = os.environ.pop("ARCHIVER_DB_PASSWORD", None)
        os.environ["ARCHIVER_BEARER_TOKEN"] = "secure-tok-123"
        try:
            cfg = Config.load_from_file(cfg_path)
            assert "myhost:5433/mydb" in cfg.database.dsn
            assert "myuser:mypass@" in cfg.database.dsn
        finally:
            if old_bt is not None:
                os.environ["ARCHIVER_BEARER_TOKEN"] = old_bt
            else:
                os.environ.pop("ARCHIVER_BEARER_TOKEN", None)
            if old_dsn is not None:
                os.environ["ARCHIVER_DSN"] = old_dsn
            if old_pw is not None:
                os.environ["ARCHIVER_DB_PASSWORD"] = old_pw
