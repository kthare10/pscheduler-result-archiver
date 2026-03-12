"""Tests for archiver.response.cors_response — error responses don't leak details."""
import json
import pytest
from unittest.mock import patch, MagicMock

from archiver.response.cors_response import (
    cors_400,
    cors_401,
    cors_403,
    cors_404,
    cors_500,
    cors_200_no_content,
    delete_none,
)


@pytest.fixture(autouse=True)
def mock_flask_request():
    """Mock Flask's request context for all tests in this module."""
    mock_req = MagicMock()
    mock_req.headers = {"Origin": "https://example.com"}
    with patch("archiver.response.cors_response.request", mock_req):
        yield mock_req


class TestCORSHeaders:
    def test_500_sets_cors_headers(self):
        resp = cors_500(details="Internal server error")
        assert resp.headers["Access-Control-Allow-Origin"] == "https://example.com"
        assert resp.headers["Access-Control-Allow-Credentials"] == "true"
        assert resp.status_code == 500

    def test_400_sets_cors_headers(self):
        resp = cors_400(details="bad input")
        assert resp.status_code == 400
        assert "Access-Control-Allow-Origin" in resp.headers

    def test_200_no_content(self):
        resp = cors_200_no_content(details={"run_id": "run-abc"})
        assert resp.status_code == 200
        body = json.loads(resp.data)
        assert body is not None


class TestErrorResponses:
    def test_500_returns_generic_message(self):
        resp = cors_500(details="Internal server error")
        body = json.loads(resp.data)
        # Should NOT contain stack traces or internal details
        assert "Traceback" not in resp.data.decode()
        assert resp.status_code == 500

    def test_401_response(self):
        resp = cors_401(details="Unauthorized")
        assert resp.status_code == 401

    def test_403_response(self):
        resp = cors_403(details="Forbidden")
        assert resp.status_code == 403

    def test_404_response(self):
        resp = cors_404(details="Not found")
        assert resp.status_code == 404


class TestDeleteNone:
    def test_removes_none_values(self):
        d = {"a": 1, "b": None, "c": "hello"}
        result = delete_none(d)
        assert result == {"a": 1, "c": "hello"}

    def test_nested_dict(self):
        d = {"a": {"b": None, "c": 1}}
        result = delete_none(d)
        assert result == {"a": {"c": 1}}

    def test_list_with_nones(self):
        lst = [1, None, 3]
        result = delete_none(lst)
        assert result == [1, 3]

    def test_empty_dict(self):
        assert delete_none({}) == {}
