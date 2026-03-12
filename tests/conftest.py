"""Shared fixtures for all tests.

Sets required environment variables and mocks the DatabaseManager BEFORE
any archiver controller modules are imported, so no real DB connection
is attempted.
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Must be set before archiver.common.config is imported
os.environ.setdefault("ARCHIVER_BEARER_TOKEN", "test-token-12345")
os.environ.setdefault("ARCHIVER_DSN", "postgresql+psycopg://test:test@localhost:5432/test")

# Point config to the real config.yml in the repo
_REPO_ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("APP_CONFIG_PATH", str(_REPO_ROOT / "archiver" / "config.yml"))

# Mock DatabaseManager.from_config and __init__ BEFORE any controller import.
# This prevents the module-level DBM = DatabaseManager.from_config(...) from
# attempting a real database connection.
_mock_dbm_instance = MagicMock()
_mock_dbm_instance.upsert_run.return_value = MagicMock(inserted=1, updated=0)
_mock_dbm_instance.upsert_trace_hops.return_value = None
_mock_dbm_instance.fetch_run_rows.return_value = []

_mock_session_ctx = MagicMock()
_mock_dbm_instance.SessionLocal.return_value = _mock_session_ctx
_mock_session_ctx.__enter__ = MagicMock(return_value=MagicMock())
_mock_session_ctx.__exit__ = MagicMock(return_value=False)

# Patch at the class level so from_config returns our mock
_from_config_patch = patch(
    "archiver.db.database_manager.DatabaseManager.__init__",
    return_value=None,
)
_from_config_patch.start()

_from_config_cls_patch = patch(
    "archiver.db.database_manager.DatabaseManager.from_config",
    return_value=_mock_dbm_instance,
)
_from_config_cls_patch.start()

import pytest


@pytest.fixture
def mock_dbm():
    """Provides the shared mock DatabaseManager for assertions."""
    _mock_dbm_instance.reset_mock()
    return _mock_dbm_instance


@pytest.fixture
def sample_body():
    """Minimal valid measurement request body (as dict, pre-JSON-parse)."""
    return {
        "run_id": "run-abc123",
        "ts": "2025-06-15T12:00:00+00:00",
        "src": {"ip": "10.0.0.1", "name": "ship-a"},
        "dst": {"ip": "23.134.232.50", "name": "shore-b"},
        "direction": "forward",
        "raw": {},
    }
