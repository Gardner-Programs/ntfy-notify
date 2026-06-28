"""ntfy-notify: an MCP server that pushes notifications to your phone via ntfy.

Exposes two tools over stdio:

  - send_notification(message, title, priority, tags, click_url)
  - send_job_alert(summary)

Configuration is read from the environment (never hardcode the topic):

  NTFY_TOPIC     required  the ntfy topic to publish to (your only secret)
  NTFY_BASE_URL  optional  default https://ntfy.sh
  NTFY_TOKEN     optional  bearer token for protected / self-hosted servers
"""

from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

DEFAULT_BASE_URL = "https://ntfy.sh"

# Valid ntfy priority names; ntfy also accepts the numeric strings "1".."5".
_PRIORITY_NAMES = {"min", "low", "default", "high", "urgent", "max"}

mcp = FastMCP("ntfy-notify")


def _config() -> tuple[str, str, str | None]:
    """Return (base_url, topic, token), raising if the topic is unset."""
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        raise RuntimeError(
            "NTFY_TOPIC is not set. Pick a long, random topic, subscribe to it "
            "in the ntfy phone app, and export it as NTFY_TOPIC."
        )
    base_url = os.environ.get("NTFY_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")
    token = os.environ.get("NTFY_TOKEN", "").strip() or None
    return base_url, topic, token


def _normalize_priority(priority: str) -> str:
    """Validate/normalize a priority into something ntfy accepts."""
    p = (priority or "default").strip().lower()
    if p in _PRIORITY_NAMES or p in {"1", "2", "3", "4", "5"}:
        return p
    return "default"


def _publish(
    message: str,
    title: str = "",
    priority: str = "default",
    tags: str = "",
    click_url: str = "",
) -> str:
    """POST a message to the configured ntfy topic. Returns a status string."""
    base_url, topic, token = _config()
    url = f"{base_url}/{topic}"

    # ntfy carries metadata in headers; the message is the raw request body.
    headers: dict[str, str] = {}
    if title.strip():
        headers["Title"] = title.strip()
    headers["Priority"] = _normalize_priority(priority)
    if tags.strip():
        headers["Tags"] = tags.strip()
    if click_url.strip():
        headers["Click"] = click_url.strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        resp = httpx.post(
            url,
            content=message.encode("utf-8"),
            headers=headers,
            timeout=15.0,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return (
            f"FAILED: ntfy returned {exc.response.status_code} for {url}. "
            f"Body: {exc.response.text[:200]}"
        )
    except httpx.HTTPError as exc:
        return f"FAILED: could not reach ntfy at {url}: {exc}"

    return f"OK: notification sent to topic '{topic}'."


@mcp.tool()
def send_notification(
    message: str,
    title: str = "",
    priority: str = "default",
    tags: str = "",
    click_url: str = "",
) -> str:
    """Send a push notification to the configured ntfy topic (your phone).

    Args:
        message: The notification body text.
        title: Optional bold title shown above the message.
        priority: One of min, low, default, high, urgent (or "1".."5").
            Anything unrecognized falls back to "default".
        tags: Comma-separated emoji shortcodes, e.g. "tada,computer".
        click_url: Optional URL opened when the notification is tapped.

    Returns:
        A status string starting with "OK:" on success or "FAILED:" on error.
    """
    return _publish(message, title, priority, tags, click_url)


@mcp.tool()
def send_job_alert(summary: str) -> str:
    """Send a job-search inbox-sweep summary with sensible defaults.

    Thin wrapper around send_notification: title "Job sweep", high priority,
    a briefcase tag. Intended for the daily job-inbox-sweep task.

    Args:
        summary: The summary text to push to your phone.

    Returns:
        A status string starting with "OK:" on success or "FAILED:" on error.
    """
    return _publish(
        message=summary,
        title="Job sweep",
        priority="high",
        tags="briefcase",
    )


def main() -> None:
    """Run the MCP server over stdio transport."""
    mcp.run()


if __name__ == "__main__":
    main()
