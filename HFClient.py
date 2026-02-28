"""
HFClient.py — Async HTTP client for the HackForums API v2.

BUG FIXES:
  #1  — Added read_sync() / write_sync() so resource classes (which are not
         async) can call self.read_sync(...) instead of the bare coroutine
         self.read(...) that was previously returned un-awaited.
  #10 — verify=False was applied to all requests globally. SSL verification
         is now only disabled when a proxy is configured (proxies can break
         the cert chain); direct requests to HF use proper TLS verification.
"""

import asyncio
import json
import logging
import time

import httpx

log = logging.getLogger("hfapi.client")

HF_READ  = "https://hackforums.net/api/v2/read"
HF_WRITE = "https://hackforums.net/api/v2/write"
HF_AUTH  = "https://hackforums.net/api/v2/authorize"

_DEFAULT_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

_DEFAULT_TIMEOUT = httpx.Timeout(connect=8.0, read=15.0, write=8.0, pool=5.0)

# ── Per-token rate limit state ─────────────────────────────────────────────────

_rate_limited_until:   dict[str, float] = {}
_rate_limit_remaining: dict[str, int]   = {}
_RATE_LIMIT_BACKOFF = 600


def get_rate_limit_remaining(token: str) -> int:
    return _rate_limit_remaining.get(token, 9999)


def is_rate_limited(token: str) -> bool:
    return time.time() < _rate_limited_until.get(token, 0)


def _mark_rate_limited(token: str) -> None:
    resume = time.time() + _RATE_LIMIT_BACKOFF
    _rate_limited_until[token] = resume
    log.warning(
        f"HF rate limit hit — pausing token ...{token[-6:]} for 10 minutes "
        f"(resumes {time.strftime('%H:%M:%S', time.localtime(resume))})"
    )


def _update_remaining(token: str, headers: httpx.Headers) -> None:
    raw = headers.get("x-rate-limit-remaining")
    if raw is None:
        return
    try:
        remaining = int(raw)
        _rate_limit_remaining[token] = remaining
        if remaining < 20:
            log.warning(f"HF rate limit low: {remaining} calls left this hour for token ...{token[-6:]}")
    except ValueError:
        pass


# ── Shared async client pool ───────────────────────────────────────────────────

_clients: dict[str | None, httpx.AsyncClient] = {}


def _get_http_client(proxy: str | None) -> httpx.AsyncClient:
    global _clients
    existing = _clients.get(proxy)
    if existing and not existing.is_closed:
        return existing

    # BUG #10 FIX: Only disable SSL verification when routing through a proxy.
    # Residential proxies can break the cert chain, so verify=False is
    # necessary there. For direct connections to HF, proper TLS is enforced.
    ssl_verify = proxy is None

    client = httpx.AsyncClient(
        proxy=proxy,
        timeout=_DEFAULT_TIMEOUT,
        verify=ssl_verify,
        headers=_DEFAULT_HEADERS,
        follow_redirects=True,
    )
    _clients[proxy] = client
    return client


async def _close_http_client(proxy: str | None) -> None:
    client = _clients.pop(proxy, None)
    if client and not client.is_closed:
        await client.aclose()


# ── Core request logic ─────────────────────────────────────────────────────────

async def _raw_post(
    token: str,
    url: str,
    asks: dict,
    proxy: str | None,
    timeout: float,
) -> tuple[int, bytes] | None:
    if is_rate_limited(token):
        log.info(f"Skipping request — token ...{token[-6:]} is rate limited")
        return None

    endpoint = url.rsplit("/", 1)[-1]
    log.debug(f"HF POST /{endpoint} asks={str(asks)[:100]}")

    async def _do_post():
        client  = _get_http_client(proxy)
        headers = {"Authorization": f"Bearer {token}"}
        data    = {"asks": json.dumps(asks)}
        return await client.post(url, data=data, headers=headers)

    try:
        r = await asyncio.wait_for(_do_post(), timeout=timeout)
    except asyncio.TimeoutError:
        log.warning(f"HF /{endpoint} timed out after {timeout}s — recycling connection pool")
        await _close_http_client(proxy)
        return None
    except httpx.ProxyError as e:
        log.warning(f"HF /{endpoint} proxy error: {e}")
        return None
    except httpx.ConnectError as e:
        log.warning(f"HF /{endpoint} connect error: {e}")
        return None
    except Exception as e:
        log.warning(f"HF /{endpoint} unexpected error: {e}")
        return None

    _update_remaining(token, r.headers)
    if b"MAX_HOURLY_CALLS_EXCEEDED" in r.content:
        _mark_rate_limited(token)

    preview = r.content[:200].decode("utf-8", errors="replace") if len(r.content) < 300 else f"({len(r.content)} bytes)"
    log.debug(f"HF /{endpoint} → HTTP {r.status_code} | {preview}")

    return r.status_code, r.content


def _parse_response(result: tuple | None, operation: str) -> dict | None:
    if result is None:
        return None
    status, body = result
    if status == 401:
        log.warning("HF 401 — token expired or revoked")
        return None
    if status == 403:
        log.warning("HF 403 — possible Cloudflare block; try a residential proxy")
        return None
    if status == 503:
        log.warning("HF 503 — server error or permission denied for this endpoint")
        return None
    if status != 200:
        log.warning(f"HF {operation} returned HTTP {status}")
        return None
    try:
        return json.loads(body)
    except Exception:
        log.warning(f"HF {operation} returned non-JSON: {body[:200]}")
        return None


# ── Public client class ────────────────────────────────────────────────────────

class HFClient:
    """
    Async HackForums API client.

    Async methods (read, write) are coroutines for use with await in async code.
    Sync wrappers (read_sync, write_sync) are for synchronous resource classes.

    Args:
        token:   HF OAuth access token.
        proxy:   Optional HTTP proxy URL, e.g. "http://user:pass@host:port".
        timeout: Per-request timeout in seconds (default 25).
    """

    def __init__(self, token: str, proxy: str | None = None, timeout: float = 25.0):
        self.token   = token
        self.proxy   = proxy
        self.timeout = timeout

    # ── Async API ──────────────────────────────────────────────────────────────

    async def read(self, asks: dict) -> dict | None:
        """POST to /read asynchronously. Use with await."""
        result = await _raw_post(self.token, HF_READ, asks, self.proxy, self.timeout)
        return _parse_response(result, "read")

    async def write(self, asks: dict) -> dict | None:
        """POST to /write asynchronously. Use with await."""
        result = await _raw_post(self.token, HF_WRITE, asks, self.proxy, self.timeout)
        return _parse_response(result, "write")

    # ── BUG #1 FIX: Synchronous wrappers ──────────────────────────────────────
    # All resource classes (HFPosts, HFBytes, HFContracts, etc.) inherit from
    # HFClient and called self.read({...}) without await. Since read() is async,
    # this returned a coroutine object — never executed. _unwrap() then received
    # a coroutine instead of a dict, causing AttributeError on every call.
    #
    # Fix: resource classes now call self.read_sync() / self.write_sync() which
    # run the coroutine to completion in a new event loop. HFBatch continues
    # to use `await self._client.read()` correctly since it is already async.

    def read_sync(self, asks: dict) -> dict | None:
        """
        Synchronous wrapper around read(). Safe to call from non-async code.
        Used by all resource classes (HFPosts, HFBytes, HFContracts, etc.).
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Rare edge-case: called from within a running loop
                # (e.g. Jupyter). Create a fresh loop in a thread instead.
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(asyncio.run, self.read(asks))
                    return future.result()
            return loop.run_until_complete(self.read(asks))
        except RuntimeError:
            return asyncio.run(self.read(asks))

    def write_sync(self, asks: dict) -> dict | None:
        """
        Synchronous wrapper around write(). Safe to call from non-async code.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(asyncio.run, self.write(asks))
                    return future.result()
            return loop.run_until_complete(self.write(asks))
        except RuntimeError:
            return asyncio.run(self.write(asks))

    # ── _unwrap ────────────────────────────────────────────────────────────────

    def _unwrap(self, data: dict | None, key: str) -> list[dict]:
        """
        Extract a list of result dicts from an API response dict.

        Returns empty list if data is None or key is absent.
        Normalises single-dict responses (HF wraps some results as dicts).
        """
        if not data:
            return []
        value = data.get(key)
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return [value]
        return []

    # ── Helpers ────────────────────────────────────────────────────────────────

    async def ping(self) -> bool:
        """Check if the token is still valid. Returns True if alive."""
        result = await _raw_post(self.token, HF_READ, {"me": {"uid": True}}, self.proxy, 15.0)
        if result is None:
            return True
        status, _ = result
        return status != 401

    @property
    def rate_limit_remaining(self) -> int:
        return get_rate_limit_remaining(self.token)

    @property
    def is_rate_limited(self) -> bool:
        return is_rate_limited(self.token)


# ── OAuth token exchange ───────────────────────────────────────────────────────

async def exchange_code_for_token(
    code: str,
    client_id: str,
    client_secret: str,
    proxy: str | None = None,
) -> tuple[str | None, int | None, str | None]:
    """
    Exchange an OAuth authorization code for an access token.
    Returns (access_token, expires_unix_timestamp, hf_uid_str) or (None, None, None).
    """
    data = {
        "grant_type":    "authorization_code",
        "client_id":     client_id,
        "client_secret": client_secret,
        "code":          code,
    }
    # BUG #10 FIX: same rule — only skip SSL verification if using a proxy
    ssl_verify = proxy is None
    try:
        async with httpx.AsyncClient(
            proxy=proxy,
            timeout=httpx.Timeout(connect=15.0, read=30.0, write=15.0, pool=5.0),
            verify=ssl_verify,
            headers=_DEFAULT_HEADERS,
        ) as client:
            r = await asyncio.wait_for(client.post(HF_AUTH, data=data), timeout=40.0)
    except asyncio.TimeoutError:
        log.warning("Token exchange timed out")
        return None, None, None
    except Exception as e:
        log.warning(f"Token exchange error: {e}")
        return None, None, None

    if r.status_code != 200:
        log.warning(f"Token exchange HTTP {r.status_code}: {r.text[:300]}")
        return None, None, None

    resp    = r.json()
    token   = resp.get("access_token")
    expires = int(time.time()) + int(resp.get("expires_in", 7_776_000))
    uid     = str(resp.get("uid", ""))
    return token, expires, uid
