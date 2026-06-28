"""Tests for ntfy-notify.

These cover the pure logic (priority normalization, config parsing) and the
header/body construction in _publish, with httpx stubbed out so nothing hits the
network.
"""

from __future__ import annotations

import pytest

import server


# --------------------------------------------------------------------------- #
# _normalize_priority
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "given, expected",
    [
        ("high", "high"),
        ("HIGH", "high"),
        ("  Urgent  ", "urgent"),
        ("1", "1"),
        ("5", "5"),
        ("", "default"),
        ("bogus", "default"),
        ("6", "default"),  # out of the 1-5 range
    ],
)
def test_normalize_priority(given, expected):
    assert server._normalize_priority(given) == expected


# --------------------------------------------------------------------------- #
# _config
# --------------------------------------------------------------------------- #
def test_config_requires_topic(monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    with pytest.raises(RuntimeError):
        server._config()


def test_config_defaults(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "my-topic")
    monkeypatch.delenv("NTFY_BASE_URL", raising=False)
    monkeypatch.delenv("NTFY_TOKEN", raising=False)
    base_url, topic, token = server._config()
    assert base_url == server.DEFAULT_BASE_URL
    assert topic == "my-topic"
    assert token is None


def test_config_strips_trailing_slash_and_reads_token(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "my-topic")
    monkeypatch.setenv("NTFY_BASE_URL", "https://ntfy.example.com/")
    monkeypatch.setenv("NTFY_TOKEN", "tk_secret")
    base_url, topic, token = server._config()
    assert base_url == "https://ntfy.example.com"  # no trailing slash
    assert token == "tk_secret"


# --------------------------------------------------------------------------- #
# _publish (httpx stubbed)
# --------------------------------------------------------------------------- #
class _FakeResponse:
    def __init__(self, status_code=200, text="ok"):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise server.httpx.HTTPStatusError(
                "error", request=None, response=self
            )


def test_publish_builds_url_headers_and_body(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "my-topic")
    monkeypatch.setenv("NTFY_BASE_URL", "https://ntfy.sh")
    monkeypatch.setenv("NTFY_TOKEN", "tk_secret")
    captured = {}

    def fake_post(url, content, headers, timeout):
        captured["url"] = url
        captured["content"] = content
        captured["headers"] = headers
        return _FakeResponse(200)

    monkeypatch.setattr(server.httpx, "post", fake_post)

    result = server._publish(
        message="hello",
        title="Title here",
        priority="high",
        tags="tada,computer",
        click_url="https://example.com",
    )

    assert result.startswith("OK:")
    assert captured["url"] == "https://ntfy.sh/my-topic"
    assert captured["content"] == b"hello"  # body is the raw message
    h = captured["headers"]
    assert h["Title"] == "Title here"
    assert h["Priority"] == "high"
    assert h["Tags"] == "tada,computer"
    assert h["Click"] == "https://example.com"
    assert h["Authorization"] == "Bearer tk_secret"


def test_publish_omits_empty_optional_headers(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "my-topic")
    monkeypatch.delenv("NTFY_TOKEN", raising=False)
    captured = {}

    def fake_post(url, content, headers, timeout):
        captured["headers"] = headers
        return _FakeResponse(200)

    monkeypatch.setattr(server.httpx, "post", fake_post)

    server._publish(message="just a message")

    h = captured["headers"]
    assert "Title" not in h
    assert "Tags" not in h
    assert "Click" not in h
    assert "Authorization" not in h
    assert h["Priority"] == "default"  # always set


def test_publish_reports_http_error(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "my-topic")

    def fake_post(url, content, headers, timeout):
        return _FakeResponse(403, text="forbidden")

    monkeypatch.setattr(server.httpx, "post", fake_post)

    result = server._publish(message="hello")
    assert result.startswith("FAILED:")
    assert "403" in result


def test_publish_reports_network_error(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "my-topic")

    def fake_post(url, content, headers, timeout):
        raise server.httpx.ConnectError("no route to host")

    monkeypatch.setattr(server.httpx, "post", fake_post)

    result = server._publish(message="hello")
    assert result.startswith("FAILED:")
