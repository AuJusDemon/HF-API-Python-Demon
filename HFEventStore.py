"""
HFEventStore — SQLite-backed persistent event deduplication for HFWatcher.

Without this, HFWatcher stores seen IDs in memory only. On bot restart,
every event from the last poll fires again as "new". With HFEventStore,
seen IDs survive restarts permanently.

Usage — plug into HFWatcher:
    from HFWatcher   import HFWatcher
    from HFEventStore import HFEventStore

    store   = HFEventStore("events.db")
    watcher = HFWatcher(hf, event_store=store)

    # Watcher automatically persists all seen IDs to disk.
    # On restart, the watcher seeds from the DB instead of re-firing old events.

Usage — standalone:
    store = HFEventStore("events.db")

    store.add("thread_replies", "tid_6083735", 59852445)   # pid
    store.has("thread_replies", "tid_6083735", 59852445)   # True

    # Or bulk-check:
    new_pids = store.filter_new("thread_replies", "tid_6083735", [100, 200, 59852445])
    # [100, 200]  ← 59852445 was already seen

    # Cleanup old events (keep last N per namespace+key)
    store.prune("thread_replies", "tid_6083735", keep=500)

    # Full purge (wipe all data older than N days)
    store.purge_old(days=7)

    store.close()

Namespaces (match HFWatcher watch types):
    "thread_replies"  — pids seen per tid
    "forum_threads"   — tids seen per fid
    "user_threads"    — tids seen per uid
    "user_posts"      — pids seen per uid
    "keyword_matches" — pids/tids seen per pattern
    "bytes_received"  — tx ids seen (no sub-key needed)

Schema:
    events(
        namespace TEXT,     -- watch type, e.g. "thread_replies"
        key TEXT,           -- sub-key, e.g. "tid_6083735" or "uid_761578"
        event_id TEXT,      -- the seen ID (pid, tid, txid, etc.)
        seen_at INTEGER,    -- unix timestamp
        PRIMARY KEY (namespace, key, event_id)
    )
"""

import sqlite3
import time
import threading
import logging
from pathlib import Path

log = logging.getLogger("hfapi.eventstore")


class HFEventStore:
    """
    SQLite-backed persistent deduplication store for HFWatcher events.

    Thread-safe — uses a threading.Lock so it can be shared across asyncio
    tasks running in the same thread.

    Args:
        db_path: Path to the SQLite database file.
                 Defaults to "hf_events.db" in the current directory.
                 Use ":memory:" for a non-persistent in-memory store.

    Example:
        store = HFEventStore("events.db")

        # Check and record a single event
        if not store.has("thread_replies", "tid_6083735", 59852445):
            store.add("thread_replies", "tid_6083735", 59852445)
            # process the new reply...

        # Or use add_if_new() which does the same atomically:
        if store.add_if_new("thread_replies", "tid_6083735", 59852445):
            # process the new reply...

        # Filter a batch to only new IDs:
        new = store.filter_new("thread_replies", "tid_6083735", [100, 200, 300])
    """

    def __init__(self, db_path: str = "hf_events.db"):
        self._path = db_path
        self._lock = threading.Lock()
        self._conn = self._connect()
        self._init_schema()
        log.info(f"HFEventStore opened: {db_path}")

    # ── Connection ─────────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self._path,
            check_same_thread=False,   # we handle thread safety with our own lock
            timeout=10,
        )
        conn.execute("PRAGMA journal_mode=WAL")   # faster concurrent reads
        conn.execute("PRAGMA synchronous=NORMAL")  # safe but not slow
        conn.execute("PRAGMA cache_size=2000")
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    namespace TEXT    NOT NULL,
                    key       TEXT    NOT NULL DEFAULT '',
                    event_id  TEXT    NOT NULL,
                    seen_at   INTEGER NOT NULL,
                    PRIMARY KEY (namespace, key, event_id)
                )
            """)
            # Index for efficient prune/purge queries
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_seen_at
                ON events (namespace, key, seen_at)
            """)
            self._conn.commit()

    # ── Core API ───────────────────────────────────────────────────────────────

    def has(self, namespace: str, key: str, event_id: int | str) -> bool:
        """
        Check if an event ID has been seen.

        Args:
            namespace: Watch type — e.g. "thread_replies".
            key:       Sub-key — e.g. "tid_6083735" or "" for global.
            event_id:  The ID to check (pid, tid, txid, etc.).

        Returns:
            True if already seen.

        Example:
            if store.has("thread_replies", "tid_6083735", pid):
                pass  # already processed
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM events WHERE namespace=? AND key=? AND event_id=? LIMIT 1",
                (namespace, str(key), str(event_id)),
            ).fetchone()
        return row is not None

    def add(self, namespace: str, key: str, event_id: int | str) -> None:
        """
        Mark an event ID as seen.

        Args:
            namespace: Watch type.
            key:       Sub-key.
            event_id:  The ID to record.

        Note:
            Silently ignores if already present (INSERT OR IGNORE).
        """
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO events (namespace, key, event_id, seen_at) VALUES (?,?,?,?)",
                (namespace, str(key), str(event_id), int(time.time())),
            )
            self._conn.commit()

    def add_if_new(self, namespace: str, key: str, event_id: int | str) -> bool:
        """
        Mark an event ID as seen and return True if it was new.

        Atomic check-and-insert — preferred over calling has() + add() separately.

        Args:
            namespace: Watch type.
            key:       Sub-key.
            event_id:  The ID to check/record.

        Returns:
            True if this ID was new (first time seen).
            False if it was already in the store.

        Example:
            if store.add_if_new("thread_replies", f"tid_{tid}", pid):
                # this is a new reply — fire the callback
                await callback(event)
        """
        with self._lock:
            cur = self._conn.execute(
                "SELECT 1 FROM events WHERE namespace=? AND key=? AND event_id=? LIMIT 1",
                (namespace, str(key), str(event_id)),
            )
            if cur.fetchone():
                return False   # already seen
            self._conn.execute(
                "INSERT INTO events (namespace, key, event_id, seen_at) VALUES (?,?,?,?)",
                (namespace, str(key), str(event_id), int(time.time())),
            )
            self._conn.commit()
        return True

    def filter_new(self, namespace: str, key: str, event_ids: list) -> list:
        """
        Filter a list of IDs to only those not yet seen.

        More efficient than calling has() in a loop — uses one SQL IN query.

        Args:
            namespace:  Watch type.
            key:        Sub-key.
            event_ids:  List of IDs to check.

        Returns:
            List of IDs from event_ids that have NOT been seen yet.
            Preserves input order.

        Example:
            new_pids = store.filter_new("thread_replies", f"tid_{tid}", all_pids)
            for pid in new_pids:
                store.add("thread_replies", f"tid_{tid}", pid)
                # process new reply...
        """
        if not event_ids:
            return []
        str_ids = [str(e) for e in event_ids]
        placeholders = ",".join("?" * len(str_ids))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT event_id FROM events WHERE namespace=? AND key=? AND event_id IN ({placeholders})",
                (namespace, str(key), *str_ids),
            ).fetchall()
        seen = {row[0] for row in rows}
        return [e for e in event_ids if str(e) not in seen]

    def add_many(self, namespace: str, key: str, event_ids: list) -> int:
        """
        Bulk-insert multiple event IDs.

        Skips IDs already in the store. Useful for seeding on first poll.

        Args:
            namespace:  Watch type.
            key:        Sub-key.
            event_ids:  List of IDs to mark as seen.

        Returns:
            Number of new IDs inserted (existing ones are skipped).

        Example:
            # Seed on first poll — don't fire for existing events
            store.add_many("forum_threads", f"fid_{fid}", existing_tids)
        """
        if not event_ids:
            return 0
        now  = int(time.time())
        rows = [(namespace, str(key), str(eid), now) for eid in event_ids]
        with self._lock:
            cur = self._conn.executemany(
                "INSERT OR IGNORE INTO events (namespace, key, event_id, seen_at) VALUES (?,?,?,?)",
                rows,
            )
            self._conn.commit()
        inserted = cur.rowcount
        if inserted:
            log.debug(f"HFEventStore: seeded {inserted} IDs into {namespace}/{key}")
        return inserted

    # ── Maintenance ────────────────────────────────────────────────────────────

    def prune(self, namespace: str, key: str, keep: int = 500) -> int:
        """
        Keep only the N most recent event IDs for a given namespace+key.

        Use this to stop unbounded DB growth for high-volume keys.

        Args:
            namespace: Watch type.
            key:       Sub-key.
            keep:      Number of most recent IDs to keep (default 500).

        Returns:
            Number of rows deleted.

        Example:
            # After processing, keep only 500 most recent pids for this thread
            store.prune("thread_replies", f"tid_{tid}", keep=500)
        """
        with self._lock:
            # Count total for this namespace+key
            total = self._conn.execute(
                "SELECT COUNT(*) FROM events WHERE namespace=? AND key=?",
                (namespace, str(key)),
            ).fetchone()[0]

            if total <= keep:
                return 0

            # Delete oldest (by seen_at)
            delete_count = total - keep
            cur = self._conn.execute(
                """DELETE FROM events WHERE rowid IN (
                    SELECT rowid FROM events
                    WHERE namespace=? AND key=?
                    ORDER BY seen_at ASC
                    LIMIT ?
                )""",
                (namespace, str(key), delete_count),
            )
            self._conn.commit()

        deleted = cur.rowcount
        log.debug(f"HFEventStore: pruned {deleted} old IDs from {namespace}/{key}")
        return deleted

    def purge_old(self, days: int = 7) -> int:
        """
        Delete all events older than N days across all namespaces.

        Run this periodically to keep the database from growing indefinitely.
        Watcher events older than a week are almost certainly irrelevant.

        Args:
            days: Delete events seen more than this many days ago.

        Returns:
            Number of rows deleted.

        Example:
            # Run nightly cleanup
            deleted = store.purge_old(days=7)
            print(f"Purged {deleted} old events")
        """
        cutoff = int(time.time()) - (days * 86400)
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM events WHERE seen_at < ?",
                (cutoff,),
            )
            self._conn.commit()
        deleted = cur.rowcount
        if deleted:
            log.info(f"HFEventStore: purged {deleted} events older than {days} days")
        return deleted

    def stats(self) -> dict[str, int]:
        """
        Return row counts per namespace.

        Returns:
            Dict mapping namespace -> count.

        Example:
            print(store.stats())
            # {"thread_replies": 1240, "forum_threads": 88, "bytes_received": 30}
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT namespace, COUNT(*) FROM events GROUP BY namespace"
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def clear(self, namespace: str | None = None, key: str | None = None) -> int:
        """
        Delete events — optionally scoped to a namespace or namespace+key.

        Args:
            namespace: Delete only events in this namespace (None = all).
            key:       Delete only events with this key (requires namespace).

        Returns:
            Number of rows deleted.

        Example:
            store.clear()                                   # wipe everything
            store.clear("thread_replies")                   # wipe all thread replies
            store.clear("thread_replies", "tid_6083735")    # wipe one thread
        """
        with self._lock:
            if namespace and key:
                cur = self._conn.execute(
                    "DELETE FROM events WHERE namespace=? AND key=?",
                    (namespace, str(key)),
                )
            elif namespace:
                cur = self._conn.execute(
                    "DELETE FROM events WHERE namespace=?",
                    (namespace,),
                )
            else:
                cur = self._conn.execute("DELETE FROM events")
            self._conn.commit()
        return cur.rowcount

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            self._conn.close()
        log.info("HFEventStore closed")

    def __enter__(self) -> "HFEventStore":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def __repr__(self) -> str:
        total = sum(self.stats().values())
        return f"HFEventStore(path={self._path!r}, total_events={total})"
