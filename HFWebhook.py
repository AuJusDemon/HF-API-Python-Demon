"""
HFWebhook.py — Emit HFWatcher events to Discord or any HTTP endpoint.

Bridges HFWatcher callbacks to outbound webhooks so you get HF notifications
in Discord without writing any formatting code, or POST raw JSON to any endpoint.

Supported targets:
  - Discord webhooks (auto-formats as rich embeds)
  - Generic HTTP     (sends raw JSON POST — plug into anything)

Usage — Discord:
    from HFClient  import HFClient
    from HFWatcher import HFWatcher
    from HFWebhook import HFWebhook

    hf      = HFClient("your_token")
    watcher = HFWatcher(hf)
    webhook = HFWebhook.discord("https://discord.com/api/webhooks/...")

    watcher.watch_thread(tid=6083735, callback=webhook.callback)
    watcher.watch_bytes(callback=webhook.callback)

    asyncio.run(watcher.start())

Usage — Multiple targets (one watcher, several webhooks):
    discord_hook = HFWebhook.discord("https://discord.com/api/webhooks/...")
    custom_hook  = HFWebhook.generic("https://myserver.com/hf-events")

    async def multi(event):
        await discord_hook.callback(event)
        await custom_hook.callback(event)

    watcher.watch_forum(fid=25, callback=multi)

Usage — Custom formatter:
    async def my_format(event: dict) -> dict:
        # Return the payload dict to POST — return None to suppress
        if event["event"] == "thread_reply":
            return {"content": f"New reply in {event['subject']}!"}
        return None

    webhook = HFWebhook("https://my-url.com/hook", formatter=my_format)
    watcher.watch_thread(tid=123, callback=webhook.callback)
"""

import asyncio
import json
import logging
import time
from typing import Callable, Awaitable

import httpx

log = logging.getLogger("hfapi.webhook")

# Type for custom formatter functions
Formatter = Callable[[dict], Awaitable[dict | None]]

# Embed colors per event type (Discord)
_DISCORD_COLORS = {
    "thread_reply":   0x5865F2,   # blurple
    "new_thread":     0x57F287,   # green
    "user_thread":    0x57F287,
    "user_post":      0x5865F2,
    "keyword_match":  0xFEE75C,   # yellow
    "bytes_received": 0xEB459E,   # pink
}

_HF_BASE = "https://hackforums.net"


class HFWebhook:
    """
    Posts HFWatcher events to a webhook URL.

    Args:
        url:       The webhook URL to POST to.
        formatter: Optional async function to build the payload from an event dict.
                   Return None to suppress the event. If not provided, a default
                   formatter is used based on the URL type (Discord/Slack/generic).
        headers:   Extra HTTP headers to include (e.g. Authorization for custom endpoints).
        timeout:   HTTP timeout in seconds (default 10).
    """

    def __init__(
        self,
        url: str,
        formatter: Formatter | None = None,
        headers: dict | None = None,
        timeout: float = 10.0,
    ):
        self._url       = url
        self._formatter = formatter or self._default_formatter
        self._headers   = {"Content-Type": "application/json", **(headers or {})}
        self._timeout   = timeout
        self._client: httpx.AsyncClient | None = None

    # ── Factory constructors ───────────────────────────────────────────────────

    @classmethod
    def discord(cls, webhook_url: str, username: str = "HF Radar", timeout: float = 10.0) -> "HFWebhook":
        """
        Create a webhook that posts rich embeds to a Discord channel.

        Args:
            webhook_url: Your Discord webhook URL.
            username:    Display name for the bot in Discord (default "HF Radar").
            timeout:     HTTP timeout.
        """
        instance = cls(webhook_url, timeout=timeout)
        instance._formatter = _make_discord_formatter(username)
        return instance

    @classmethod
    def generic(
        cls,
        url: str,
        headers: dict | None = None,
        timeout: float = 10.0,
    ) -> "HFWebhook":
        """
        Create a webhook that POSTs the raw event dict as JSON.

        Args:
            url:     Your endpoint URL.
            headers: Optional auth headers etc.
            timeout: HTTP timeout.
        """
        instance = cls(url, headers=headers, timeout=timeout)
        instance._formatter = _generic_formatter
        return instance

    # ── Callback ───────────────────────────────────────────────────────────────

    async def callback(self, event: dict) -> None:
        """
        The async callback to pass to HFWatcher.watch_*().

        Example:
            webhook = HFWebhook.discord("https://discord.com/api/webhooks/...")
            watcher.watch_thread(tid=123, callback=webhook.callback)
        """
        try:
            payload = await self._formatter(event)
        except Exception as e:
            log.warning(f"HFWebhook formatter error: {e}")
            return

        if payload is None:
            return

        await self._send(payload)

    # ── HTTP send ──────────────────────────────────────────────────────────────

    async def _send(self, payload: dict) -> None:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        try:
            r = await asyncio.wait_for(
                self._client.post(self._url, json=payload, headers=self._headers),
                timeout=self._timeout + 2,
            )
            if r.status_code not in (200, 204):
                log.warning(f"HFWebhook POST {self._url} → HTTP {r.status_code}: {r.text[:200]}")
            else:
                log.debug(f"HFWebhook sent event → HTTP {r.status_code}")
        except asyncio.TimeoutError:
            log.warning(f"HFWebhook POST timed out: {self._url}")
        except Exception as e:
            log.warning(f"HFWebhook POST error: {e}")

    # ── Default formatter (generic JSON) ───────────────────────────────────────

    @staticmethod
    async def _default_formatter(event: dict) -> dict | None:
        return event

    # ── Cleanup ────────────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close the underlying HTTP client. Call when shutting down."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# ── Discord formatter ──────────────────────────────────────────────────────────

def _make_discord_formatter(username: str) -> Formatter:
    async def _format(event: dict) -> dict | None:
        embed = _event_to_discord_embed(event)
        if embed is None:
            return None
        return {
            "username": username,
            "embeds":   [embed],
        }
    return _format


def _event_to_discord_embed(event: dict) -> dict | None:
    etype   = event.get("event", "")
    color   = _DISCORD_COLORS.get(etype, 0x99AAB5)
    ts      = event.get("dateline") or int(time.time())

    if etype == "thread_reply":
        tid     = event.get("tid")
        pid     = event.get("pid")
        subject = event.get("subject", "Thread")
        snippet = event.get("snippet", "")
        url     = f"{_HF_BASE}/showthread.php?tid={tid}&pid={pid}#pid{pid}" if pid else f"{_HF_BASE}/showthread.php?tid={tid}"
        return {
            "title":       f"💬 New reply in {subject}",
            "url":         url,
            "description": snippet or "",
            "color":       color,
            "timestamp":   _iso(ts),
        }

    if etype in ("new_thread", "user_thread"):
        tid     = event.get("tid")
        subject = event.get("subject", "New Thread")
        uid     = event.get("uid")
        label   = "👥 New thread by a tracked user" if etype == "user_thread" else "📌 New thread"
        url     = f"{_HF_BASE}/showthread.php?tid={tid}"
        desc    = f"[{subject}]({url})"
        if uid:
            desc += f"\n[View profile]({_HF_BASE}/member.php?action=profile&uid={uid})"
        return {
            "title":       label,
            "url":         url,
            "description": desc,
            "color":       color,
            "timestamp":   _iso(ts),
        }

    if etype == "user_post":
        tid     = event.get("tid")
        pid     = event.get("pid")
        subject = event.get("subject", "Thread")
        snippet = event.get("snippet", "")
        url     = f"{_HF_BASE}/showthread.php?tid={tid}&pid={pid}#pid{pid}"
        return {
            "title":       f"👥 New post by tracked user in {subject}",
            "url":         url,
            "description": snippet or "",
            "color":       color,
            "timestamp":   _iso(ts),
        }

    if etype == "keyword_match":
        tid     = event.get("tid")
        pid     = event.get("pid")
        keyword = event.get("keyword", "")
        subject = event.get("subject", "")
        snippet = event.get("snippet", "")
        url     = (
            f"{_HF_BASE}/showthread.php?tid={tid}&pid={pid}#pid{pid}"
            if pid else
            f"{_HF_BASE}/showthread.php?tid={tid}"
        )
        return {
            "title":       f"🔍 Keyword match: `{keyword}`",
            "url":         url,
            "description": f"**{subject}**\n{snippet}",
            "color":       color,
            "timestamp":   _iso(ts),
        }

    if etype == "bytes_received":
        amount    = event.get("amount", 0)
        reason    = event.get("reason", "")
        from_user = event.get("from_user", "Unknown")
        return {
            "title":       f"💰 {amount:,.0f} bytes received from {from_user}",
            "description": reason or "",
            "url":         f"{_HF_BASE}/myps.php?action=history",
            "color":       color,
            "timestamp":   _iso(ts),
        }

    return None


def _iso(unix_ts: int) -> str:
    """Convert unix timestamp to ISO 8601 for Discord embeds."""
    import datetime
    return datetime.datetime.utcfromtimestamp(unix_ts).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Generic formatter ──────────────────────────────────────────────────────────

async def _generic_formatter(event: dict) -> dict | None:
    """Posts the raw event dict as JSON. Works with any HTTP endpoint."""
    return event
