"""
HFCache — TTL-based in-memory cache for HackForums API responses.

Bug #12 fix: get_or_fetch() previously never cached None results. For a
banned or deleted user, every call to users_api.get(uid) would hit the API
again because the None result was never stored. Fixed by caching None with a
short TTL (60s default) using an internal sentinel value so that callers
still receive None back but the re-fetch is rate-limited.
"""

from __future__ import annotations

import time
import threading
import logging
from typing import Any

log = logging.getLogger("hfapi.cache")

_SENTINEL   = object()   # distinct from None: marks an empty store slot
_NONE_CACHED = object()  # Bug #12: sentinel stored when fetch_fn() returned None


class HFCache:
    """
    Thread-safe in-memory cache with per-entry TTL.

    Args:
        ttl:     Default time-to-live in seconds (default 300 = 5 minutes).
        maxsize: Maximum number of entries before LRU eviction. 0 = unlimited.
    """

    def __init__(self, ttl: int = 300, maxsize: int = 0):
        self._default_ttl = ttl
        self._maxsize     = maxsize
        self._lock        = threading.Lock()
        self._store: dict[tuple, tuple] = {}
        self._hits   = 0
        self._misses = 0

    # ── Core API ───────────────────────────────────────────────────────────────

    def get(self, namespace: str, key: Any, default: Any = None) -> Any:
        """Get a cached value. Returns default if missing or expired."""
        cache_key = (namespace, _make_hashable(key))
        with self._lock:
            entry = self._store.get(cache_key, _SENTINEL)
            if entry is _SENTINEL:
                self._misses += 1
                return default
            value, expire_at = entry
            if time.monotonic() > expire_at:
                del self._store[cache_key]
                self._misses += 1
                return default
            self._hits += 1
            # Bug #12: unwrap the None-cached sentinel back to None for the caller
            return None if value is _NONE_CACHED else value

    def set(self, namespace: str, key: Any, value: Any, ttl: int | None = None) -> None:
        """Set a cache entry. value may be None."""
        cache_key  = (namespace, _make_hashable(key))
        expire_at  = time.monotonic() + (ttl if ttl is not None else self._default_ttl)
        # Store None as _NONE_CACHED so we can distinguish "not in cache" from "cached None"
        stored = _NONE_CACHED if value is None else value

        with self._lock:
            if self._maxsize and len(self._store) >= self._maxsize:
                oldest_key = min(self._store, key=lambda k: self._store[k][1])
                del self._store[oldest_key]
            self._store[cache_key] = (stored, expire_at)

    def delete(self, namespace: str, key: Any) -> bool:
        """Remove a specific cache entry. Returns True if it existed."""
        cache_key = (namespace, _make_hashable(key))
        with self._lock:
            return self._store.pop(cache_key, _SENTINEL) is not _SENTINEL

    def invalidate(self, namespace: str) -> int:
        """Remove all entries for a namespace. Returns count removed."""
        with self._lock:
            keys_to_del = [k for k in self._store if k[0] == namespace]
            for k in keys_to_del:
                del self._store[k]
        return len(keys_to_del)

    def clear(self) -> int:
        """Remove all cached entries."""
        with self._lock:
            count = len(self._store)
            self._store.clear()
        return count

    # ── Helpers ────────────────────────────────────────────────────────────────

    def get_or_fetch(
        self,
        namespace: str,
        key: Any,
        fetch_fn,
        ttl: int | None = None,
        none_ttl: int = 60,
    ) -> Any:
        """
        Return cached value, or call fetch_fn() and cache the result.

        Bug #12 fix: If fetch_fn() returns None (e.g. banned/deleted user),
        the None result is now cached for none_ttl seconds (default 60s).
        This prevents hammering the API for resources that don't exist.
        The caller still receives None — the caching is transparent.

        Args:
            namespace: Cache namespace.
            key:       Cache key.
            fetch_fn:  Zero-argument callable returning the value to cache.
            ttl:       Override TTL for non-None results.
            none_ttl:  TTL for None results (default 60s). Pass 0 to disable
                       None caching and restore legacy behaviour.
        """
        # get() returns None for both "not in cache" and "cached None" — so
        # we need to check the raw store to distinguish the two cases.
        cache_key = (namespace, _make_hashable(key))
        with self._lock:
            entry = self._store.get(cache_key, _SENTINEL)
            if entry is not _SENTINEL:
                value, expire_at = entry
                if time.monotonic() <= expire_at:
                    self._hits += 1
                    return None if value is _NONE_CACHED else value
                else:
                    del self._store[cache_key]
            self._misses += 1

        value = fetch_fn()
        if value is None:
            if none_ttl > 0:
                self.set(namespace, key, None, ttl=none_ttl)
        else:
            self.set(namespace, key, value, ttl=ttl)
        return value

    def purge_expired(self) -> int:
        """Remove all expired entries. Returns count removed."""
        now = time.monotonic()
        with self._lock:
            expired = [k for k, (_, exp) in self._store.items() if now > exp]
            for k in expired:
                del self._store[k]
        if expired:
            log.debug(f"HFCache: purged {len(expired)} expired entries")
        return len(expired)

    # ── Stats ──────────────────────────────────────────────────────────────────

    @property
    def size(self) -> int:
        return len(self._store)

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total else 0.0

    def stats(self) -> dict:
        return {
            "entries":  self.size,
            "hits":     self._hits,
            "misses":   self._misses,
            "hit_rate": round(self.hit_rate, 3),
            "ttl":      self._default_ttl,
        }

    def __repr__(self) -> str:
        return f"HFCache(entries={self.size}, ttl={self._default_ttl}s, hit_rate={self.hit_rate:.1%})"


def _make_hashable(key: Any) -> Any:
    if isinstance(key, list):
        return tuple(key)
    if isinstance(key, dict):
        return tuple(sorted(key.items()))
    return key


# ── Cached API class wrappers ──────────────────────────────────────────────────

class CachedHFUsers:
    """HFUsers with built-in TTL cache. Drop-in replacement."""

    def __init__(self, token: str, ttl: int = 300, proxy: str | None = None):
        from HFUsers import HFUsers
        self._api   = HFUsers(token, proxy=proxy)
        self._cache = HFCache(ttl=ttl)

    def get(self, uid: int) -> dict | None:
        """Get a user profile by UID, cached. Caches None for deleted/banned users."""
        return self._cache.get_or_fetch("user", uid, lambda: self._api.get(uid))

    def get_many(self, uids: list[int]) -> list[dict]:
        """Get multiple user profiles, serving cached ones where possible."""
        cached_results = []
        uncached_uids  = []

        for uid in uids:
            # Check raw store to distinguish "not cached" from "cached None"
            cached = self._cache.get("user", uid, default=_SENTINEL)
            if cached is not _SENTINEL:
                if cached is not None:
                    cached_results.append(cached)
                # None means cached as deleted/banned — skip API call
            else:
                uncached_uids.append(uid)

        if uncached_uids:
            fresh = self._api.get_many(uncached_uids)
            fetched_uids = set()
            for user in fresh:
                if user.get("uid"):
                    uid = int(user["uid"])
                    self._cache.set("user", uid, user)
                    fetched_uids.add(uid)
                    cached_results.append(user)
            # Cache None for UIDs that came back empty
            for uid in uncached_uids:
                if uid not in fetched_uids:
                    self._cache.set("user", uid, None, ttl=60)

        return cached_results

    def get_username(self, uid: int) -> str | None:
        user = self.get(uid)
        return user.get("username") if user else None

    def get_usernames_map(self, uids: list[int]) -> dict[int, str]:
        users = self.get_many(uids)
        return {int(u["uid"]): u["username"] for u in users if u.get("uid") and u.get("username")}

    def invalidate(self, uid: int | None = None) -> None:
        if uid:
            self._cache.delete("user", uid)
        else:
            self._cache.invalidate("user")

    @property
    def cache_stats(self) -> dict:
        return self._cache.stats()


class CachedHFForums:
    """HFForums with built-in TTL cache. Drop-in replacement."""

    def __init__(self, token: str, ttl: int = 3600, proxy: str | None = None):
        from HFForums import HFForums
        self._api   = HFForums(token, proxy=proxy)
        self._cache = HFCache(ttl=ttl)

    def get(self, fid: int) -> dict | None:
        return self._cache.get_or_fetch("forum", fid, lambda: self._api.get(fid))

    def get_many(self, fids: list[int]) -> list[dict]:
        cached_results = []
        uncached_fids  = []

        for fid in fids:
            cached = self._cache.get("forum", fid, default=_SENTINEL)
            if cached is not _SENTINEL:
                if cached is not None:
                    cached_results.append(cached)
            else:
                uncached_fids.append(fid)

        if uncached_fids:
            fresh = self._api.get_many(uncached_fids)
            for forum in fresh:
                if forum.get("fid"):
                    self._cache.set("forum", int(forum["fid"]), forum)
            cached_results.extend(fresh)

        return cached_results

    def invalidate(self, fid: int | None = None) -> None:
        if fid:
            self._cache.delete("forum", fid)
        else:
            self._cache.invalidate("forum")


class CachedHFMe:
    """HFMe with built-in TTL cache. Use a short TTL (60s default)."""

    def __init__(self, token: str, ttl: int = 60, proxy: str | None = None):
        from HFMe import HFMe
        self._api   = HFMe(token, proxy=proxy)
        self._cache = HFCache(ttl=ttl)
        self._token = token

    def get(self, advanced: bool = True) -> dict | None:
        cache_key = f"me_{'adv' if advanced else 'basic'}"
        return self._cache.get_or_fetch(
            "me", cache_key,
            lambda: self._api.get(advanced=advanced),
        )

    def get_unread_pms(self) -> int:
        me = self.get(advanced=True)
        return int(me.get("unreadpms", 0)) if me else 0

    def get_bytes_balance(self) -> float:
        me = self.get(advanced=False)
        return float(me.get("bytes", 0)) if me else 0.0

    def invalidate(self) -> None:
        self._cache.invalidate("me")
