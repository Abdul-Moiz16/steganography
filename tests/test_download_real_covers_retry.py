"""Retry-policy tests for the HF dataset-server fetchers.

The 1000-group run was killed by a single TimeoutError during the real-
cover download because the retry block caught only URLError / HTTPError.
This pins the broadened retry class so a regression would surface here.
"""

from __future__ import annotations

from urllib.error import URLError

import pytest

from src.data import download_real_covers as drc


class _FakeResp:
    """Stand-in for urlopen's context-managed response."""

    def __init__(self, payload: bytes = b'{"rows":[]}') -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None


def test_request_json_retries_on_timeout_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A single TimeoutError mid-read used to kill the whole run."""
    calls = {"n": 0}

    def fake_urlopen(req, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("read operation timed out")
        return _FakeResp()

    monkeypatch.setattr(drc, "urlopen", fake_urlopen)
    monkeypatch.setattr(drc.time, "sleep", lambda *_: None)

    result = drc._request_json("https://example.test/rows", retries=3)
    assert result == {"rows": []}
    assert calls["n"] == 2  # one failure + one success


def test_request_json_retries_on_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_urlopen(req, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionResetError("connection reset by peer")
        return _FakeResp()

    monkeypatch.setattr(drc, "urlopen", fake_urlopen)
    monkeypatch.setattr(drc.time, "sleep", lambda *_: None)

    result = drc._request_json("https://example.test/rows", retries=5)
    assert result == {"rows": []}
    assert calls["n"] == 3


def test_request_json_retries_on_url_error_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    """URLError was the original retryable case; ensure it still triggers retry."""
    calls = {"n": 0}

    def fake_urlopen(req, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            raise URLError("dns failed")
        return _FakeResp()

    monkeypatch.setattr(drc, "urlopen", fake_urlopen)
    monkeypatch.setattr(drc.time, "sleep", lambda *_: None)

    drc._request_json("https://example.test/rows", retries=3)
    assert calls["n"] == 2


def test_request_json_gives_up_after_max_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """The final attempt's error must propagate so the caller sees the failure."""
    def fake_urlopen(req, timeout):
        raise TimeoutError("persistent timeout")

    monkeypatch.setattr(drc, "urlopen", fake_urlopen)
    monkeypatch.setattr(drc.time, "sleep", lambda *_: None)

    with pytest.raises(TimeoutError):
        drc._request_json("https://example.test/rows", retries=3)


def test_request_bytes_retries_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """_request_bytes shares the same retry policy for image downloads."""
    calls = {"n": 0}

    def fake_urlopen(req, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("image read timed out")
        return _FakeResp(payload=b"\xff\xd8\xff\xe0")

    monkeypatch.setattr(drc, "urlopen", fake_urlopen)
    monkeypatch.setattr(drc.time, "sleep", lambda *_: None)

    result = drc._request_bytes("https://example.test/img.jpg", retries=3)
    assert result.startswith(b"\xff\xd8")
    assert calls["n"] == 2
