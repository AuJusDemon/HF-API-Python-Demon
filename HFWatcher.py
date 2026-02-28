"""
HFWatcher.py — Polling watcher for HackForums events.

Bug fixes applied:
  - Bug #4: _my_uid=0 permanently killed the bytes watcher. The UID fetch is
    now scoped to _BytesWatch (not shared on self), and if uid resolves to 0
    (empty/missing field) it is treated as a transient failure and retried
    next poll instead of permanently short-circuiting.

  - Bug #6: The keyword watcher used a single _seen_pids set for both thread
    IDs and post IDs. A thread with tid=X and a post with pid=X would collide
    and one would be silently skipped. Fixed by splitting into _seen_tids and
    _seen_pids.
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Awaitable

from HFClient import HFClient

log = logging.getLogger("hfapi.watcher")

Callback = Callable[[dict], Awaitable[None]]


# ── Watch job dataclasses ──────────────────────────────────────────────────────

@dataclass
class _ThreadWatch:
    tid:      int
    callback: Callback
    interval: int   = 60
    _last_post: int = field(default=0, init=False, repr=False)
    _seen_pids: set = field(default_factory=set, init=False, repr=False)


@dataclass
class _ForumWatch:
    fid:      int
    callback: Callback
    interval: int   = 120
    _seen_tids: set = field(default_factory=set, init=False, repr=False)
    _initialized: bool = field(default=False, init=False, repr=False)


@dataclass
class _UserWatch:
    uid:         int
    callback:    Callback
    interval:    int  = 120
    mode:        str  = "threads"
    _seen_tids: set = field(default_factory=set, init=False, repr=False)
    _seen_pids: set = field(default_factory=set, init=False, repr=False)
    _initialized: bool = field(default=False, init=False, repr=False)


@dataclass
class _KeywordWatch:
    pattern:  re.Pattern
    callback: Callback
    interval: int   = 120
    fids:     list  = field(default_factory=list)
    # Bug #6 fix: separate sets for thread IDs and post IDs
    _seen_tids: set = field(default_factory=set, init=False, repr=False)
    _seen_pids: set = field(default_factory=set, init=False, repr=False)
    _last_check: float = field(default_factory=time.time, init=False, repr=False)


@dataclass
class _BytesWatch:
    callback: Callback
    interval: int   = 60
    _seen_ids: set = field(default_factory=set, init=False, repr=False)
    _initialized: bool = field(default=False, init=False, repr=False)
    # Bug #4 fix: uid scoped to the watch, not shared on self._my_uid
    # None = not yet fetched, 0 = fetch failed transiently (retry next poll)
    _my_uid: int | None = field(default=None, init=False, repr=False)


# ── Watcher ────────────────────────────────────────────────────────────────────

class HFWatcher:
    """
    Polls the HackForums API for new activity and fires async callbacks.

    Args:
        client:    An HFClient instance (already has your token + proxy).
        on_error:  Optional async callback fired when a poll cycle raises.
    """

    def __init__(self, client: HFClient, on_error: Callback | None = None):
        self._hf       = client
        self._on_error = on_error
        self._running  = False

        self._thread_watches:  list[_ThreadWatch]  = []
        self._forum_watches:   list[_ForumWatch]   = []
        self._user_watches:    list[_UserWatch]    = []
        self._keyword_watches: list[_KeywordWatch] = []
        self._bytes_watches:   list[_BytesWatch]   = []

    # ── Registration API ───────────────────────────────────────────────────────

    def watch_thread(self, tid: int, callback: Callback, interval: int = 60) -> "HFWatcher":
        self._thread_watches.append(_ThreadWatch(tid=tid, callback=callback, interval=interval))
        return self

    def watch_forum(self, fid: int, callback: Callback, interval: int = 120) -> "HFWatcher":
        self._forum_watches.append(_ForumWatch(fid=fid, callback=callback, interval=interval))
        return self

    def watch_user(
        self,
        uid: int,
        callback: Callback,
        interval: int = 120,
        mode: str = "threads",
    ) -> "HFWatcher":
        self._user_watches.append(_UserWatch(uid=uid, callback=callback, interval=interval, mode=mode))
        return self

    def watch_keyword(
        self,
        keyword: str,
        callback: Callback,
        interval: int = 120,
        fids: list[int] | None = None,
        case_sensitive: bool = False,
    ) -> "HFWatcher":
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            pattern = re.compile(keyword, flags)
        except re.error:
            pattern = re.compile(re.escape(keyword), flags)

        self._keyword_watches.append(_KeywordWatch(
            pattern=pattern,
            callback=callback,
            interval=interval,
            fids=list(fids or []),
        ))
        return self

    def watch_bytes(self, callback: Callback, interval: int = 60) -> "HFWatcher":
        self._bytes_watches.append(_BytesWatch(callback=callback, interval=interval))
        return self

    # ── Run loop ───────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True
        log.info(
            f"HFWatcher starting — "
            f"{len(self._thread_watches)} thread(s), "
            f"{len(self._forum_watches)} forum(s), "
            f"{len(self._user_watches)} user(s), "
            f"{len(self._keyword_watches)} keyword(s), "
            f"{len(self._bytes_watches)} bytes watcher(s)"
        )
        tasks = []
        for w in self._thread_watches:
            tasks.append(asyncio.create_task(self._thread_loop(w), name=f"watch_thread_{w.tid}"))
        for w in self._forum_watches:
            tasks.append(asyncio.create_task(self._forum_loop(w), name=f"watch_forum_{w.fid}"))
        for w in self._user_watches:
            tasks.append(asyncio.create_task(self._user_loop(w), name=f"watch_user_{w.uid}"))
        for w in self._keyword_watches:
            tasks.append(asyncio.create_task(self._keyword_loop(w), name="watch_keyword"))
        for w in self._bytes_watches:
            tasks.append(asyncio.create_task(self._bytes_loop(w), name="watch_bytes"))

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for t in tasks:
                t.cancel()

    def stop(self) -> None:
        self._running = False

    # ── Poll implementations ───────────────────────────────────────────────────

    async def _thread_loop(self, w: _ThreadWatch) -> None:
        while self._running:
            try:
                await self._poll_thread(w)
            except Exception as e:
                log.warning(f"watch_thread tid={w.tid} error: {e}")
                if self._on_error:
                    await self._on_error("thread", e)
            await asyncio.sleep(w.interval)

    async def _poll_thread(self, w: _ThreadWatch) -> None:
        meta = await self._hf.read({
            "threads": {
                "_tid":       [w.tid],
                "tid":        True,
                "subject":    True,
                "lastpost":   True,
                "numreplies": True,
            }
        })
        if not meta or "threads" not in meta:
            return

        threads = meta["threads"]
        if isinstance(threads, dict):
            threads = [threads]
        if not threads:
            return

        t          = threads[0]
        lastpost   = int(t.get("lastpost") or 0)
        numreplies = int(t.get("numreplies") or 0)
        subject    = t.get("subject", "Thread")

        if w._last_post == 0:
            w._last_post = lastpost
            return

        if lastpost <= w._last_post:
            return

        last_page = max(1, (numreplies + 1 + 9) // 10)
        post_data = await self._hf.read({
            "posts": {
                "_tid":     [w.tid],
                "_page":    last_page,
                "_perpage": 10,
                "pid":      True,
                "uid":      True,
                "dateline": True,
                "message":  True,
            }
        })
        if not post_data or "posts" not in post_data:
            await w.callback({
                "event":    "thread_reply",
                "tid":      w.tid,
                "pid":      None,
                "uid":      None,
                "subject":  subject,
                "snippet":  "",
                "dateline": lastpost,
            })
            w._last_post = lastpost
            return

        posts = post_data["posts"]
        if isinstance(posts, dict):
            posts = [posts]

        posts.sort(key=lambda p: int(p.get("dateline") or 0))

        for post in posts:
            pid      = int(post.get("pid") or 0)
            dateline = int(post.get("dateline") or 0)

            if dateline <= w._last_post:
                continue
            if pid in w._seen_pids:
                continue

            w._seen_pids.add(pid)
            await w.callback({
                "event":    "thread_reply",
                "tid":      w.tid,
                "pid":      pid,
                "uid":      str(post.get("uid", "")),
                "subject":  subject,
                "snippet":  _strip_bbcode(post.get("message", ""))[:200],
                "dateline": dateline,
            })

        w._last_post = lastpost
        if len(w._seen_pids) > 500:
            w._seen_pids = set(list(w._seen_pids)[-250:])

    async def _forum_loop(self, w: _ForumWatch) -> None:
        while self._running:
            try:
                await self._poll_forum(w)
            except Exception as e:
                log.warning(f"watch_forum fid={w.fid} error: {e}")
                if self._on_error:
                    await self._on_error("forum", e)
            await asyncio.sleep(w.interval)

    async def _poll_forum(self, w: _ForumWatch) -> None:
        data = await self._hf.read({
            "threads": {
                "_fid":     [w.fid],
                "tid":      True,
                "uid":      True,
                "subject":  True,
                "dateline": True,
            }
        })
        if not data or "threads" not in data:
            return

        threads = data["threads"]
        if isinstance(threads, dict):
            threads = [threads]

        if not w._initialized:
            for t in (threads or []):
                tid = int(t.get("tid") or 0)
                if tid:
                    w._seen_tids.add(tid)
            w._initialized = True
            return

        for t in sorted(threads or [], key=lambda x: int(x.get("dateline") or 0)):
            tid      = int(t.get("tid") or 0)
            dateline = int(t.get("dateline") or 0)
            if not tid or tid in w._seen_tids:
                continue
            w._seen_tids.add(tid)
            await w.callback({
                "event":    "new_thread",
                "fid":      w.fid,
                "tid":      tid,
                "uid":      str(t.get("uid", "")),
                "subject":  t.get("subject", ""),
                "dateline": dateline,
            })

        if len(w._seen_tids) > 1000:
            w._seen_tids = set(list(w._seen_tids)[-500:])

    async def _user_loop(self, w: _UserWatch) -> None:
        while self._running:
            try:
                await self._poll_user(w)
            except Exception as e:
                log.warning(f"watch_user uid={w.uid} error: {e}")
                if self._on_error:
                    await self._on_error("user", e)
            await asyncio.sleep(w.interval)

    async def _poll_user(self, w: _UserWatch) -> None:
        thread_data = await self._hf.read({
            "threads": {
                "_uid":     [w.uid],
                "_page":    1,
                "_perpage": 20,
                "tid":      True,
                "subject":  True,
                "dateline": True,
            }
        })
        if thread_data and "threads" in thread_data:
            rows = thread_data["threads"]
            if isinstance(rows, dict):
                rows = [rows]
            if not w._initialized:
                for t in (rows or []):
                    tid = int(t.get("tid") or 0)
                    if tid:
                        w._seen_tids.add(tid)
            else:
                for t in sorted(rows or [], key=lambda x: int(x.get("dateline") or 0)):
                    tid      = int(t.get("tid") or 0)
                    dateline = int(t.get("dateline") or 0)
                    if not tid or tid in w._seen_tids:
                        continue
                    w._seen_tids.add(tid)
                    await w.callback({
                        "event":    "user_thread",
                        "uid":      w.uid,
                        "tid":      tid,
                        "subject":  t.get("subject", ""),
                        "dateline": dateline,
                    })

        if w.mode == "all":
            post_data = await self._hf.read({
                "posts": {
                    "_uid":     [w.uid],
                    "_page":    1,
                    "_perpage": 20,
                    "pid":      True,
                    "tid":      True,
                    "subject":  True,
                    "dateline": True,
                    "message":  True,
                }
            })
            if post_data and "posts" in post_data:
                posts = post_data["posts"]
                if isinstance(posts, dict):
                    posts = [posts]
                posts_sorted = sorted(posts or [], key=lambda p: int(p.get("dateline") or 0))
                for p in posts_sorted:
                    pid      = int(p.get("pid") or 0)
                    dateline = int(p.get("dateline") or 0)
                    if not pid:
                        continue
                    if not w._initialized:
                        w._seen_pids.add(pid)
                        continue
                    if pid in w._seen_pids:
                        continue
                    w._seen_pids.add(pid)
                    await w.callback({
                        "event":    "user_post",
                        "uid":      w.uid,
                        "tid":      int(p.get("tid") or 0),
                        "pid":      pid,
                        "subject":  p.get("subject", ""),
                        "snippet":  _strip_bbcode(p.get("message", ""))[:200],
                        "dateline": dateline,
                    })

        w._initialized = True

        if len(w._seen_tids) > 500:
            w._seen_tids = set(list(w._seen_tids)[-250:])
        if len(w._seen_pids) > 500:
            w._seen_pids = set(list(w._seen_pids)[-250:])

    async def _keyword_loop(self, w: _KeywordWatch) -> None:
        while self._running:
            try:
                await self._poll_keyword(w)
            except Exception as e:
                log.warning(f"watch_keyword error: {e}")
                if self._on_error:
                    await self._on_error("keyword", e)
            await asyncio.sleep(w.interval)

    async def _poll_keyword(self, w: _KeywordWatch) -> None:
        # Bug #6 fix: use w._seen_tids for thread IDs and w._seen_pids for post IDs
        fids = w.fids if w.fids else []
        if not fids:
            log.warning("watch_keyword: no fids specified — keyword watching requires at least one forum ID")
            return

        for fid in fids:
            data = await self._hf.read({
                "threads": {
                    "_fid":     [fid],
                    "tid":      True,
                    "uid":      True,
                    "subject":  True,
                    "dateline": True,
                }
            })
            if not data or "threads" not in data:
                continue

            threads = data["threads"]
            if isinstance(threads, dict):
                threads = [threads]

            for t in (threads or []):
                tid      = int(t.get("tid") or 0)
                subject  = t.get("subject", "")
                dateline = int(t.get("dateline") or 0)

                if not tid or tid in w._seen_tids:
                    continue

                # Check subject match
                if w.pattern.search(subject):
                    w._seen_tids.add(tid)
                    await w.callback({
                        "event":    "keyword_match",
                        "keyword":  w.pattern.pattern,
                        "fid":      fid,
                        "tid":      tid,
                        "pid":      None,
                        "subject":  subject,
                        "snippet":  subject,
                        "dateline": dateline,
                    })
                    continue

                # Skip old threads for content scanning
                if time.time() - dateline > 3600:
                    w._seen_tids.add(tid)
                    continue

                # Check post content for recent threads
                post_data = await self._hf.read({
                    "posts": {
                        "_tid":     [tid],
                        "_page":    1,
                        "_perpage": 5,
                        "pid":      True,
                        "message":  True,
                        "dateline": True,
                    }
                })
                if not post_data or "posts" not in post_data:
                    continue

                posts = post_data["posts"]
                if isinstance(posts, dict):
                    posts = [posts]
                for post in (posts or []):
                    pid     = int(post.get("pid") or 0)
                    message = post.get("message", "")
                    # Bug #6 fix: check _seen_pids (not _seen_tids) for post IDs
                    if pid in w._seen_pids:
                        continue
                    if w.pattern.search(message):
                        w._seen_pids.add(pid)
                        await w.callback({
                            "event":    "keyword_match",
                            "keyword":  w.pattern.pattern,
                            "fid":      fid,
                            "tid":      tid,
                            "pid":      pid,
                            "subject":  subject,
                            "snippet":  _strip_bbcode(message)[:200],
                            "dateline": int(post.get("dateline") or 0),
                        })
                w._seen_tids.add(tid)

        # Bound both sets
        if len(w._seen_tids) > 2000:
            w._seen_tids = set(list(w._seen_tids)[-1000:])
        if len(w._seen_pids) > 2000:
            w._seen_pids = set(list(w._seen_pids)[-1000:])

    async def _bytes_loop(self, w: _BytesWatch) -> None:
        while self._running:
            try:
                await self._poll_bytes(w)
            except Exception as e:
                log.warning(f"watch_bytes error: {e}")
                if self._on_error:
                    await self._on_error("bytes", e)
            await asyncio.sleep(w.interval)

    async def _poll_bytes(self, w: _BytesWatch) -> None:
        # Bug #4 fix: _my_uid is scoped to the _BytesWatch dataclass, not self.
        # None = not yet fetched (retry next poll).
        # A valid UID is cached after first successful fetch.
        # If the API returns a missing/empty uid we leave it as None and retry
        # next poll — we do NOT set it to 0 and permanently kill the watcher.
        if w._my_uid is None:
            me = await self._hf.read({"me": {"uid": True}})
            if not me or "me" not in me:
                return   # transient failure — retry next poll
            me_data = me["me"]
            if isinstance(me_data, list):
                me_data = me_data[0] if me_data else {}
            uid_val = int(me_data.get("uid") or 0)
            if not uid_val:
                # uid came back empty — transient or bad response, retry next poll
                log.warning("watch_bytes: /me returned empty uid, will retry next poll")
                return
            w._my_uid = uid_val

        data = await self._hf.read({
            "bytes": {
                "_to":      [w._my_uid],
                "_perpage": 20,
                "id":       True,
                "amount":   True,
                "dateline": True,
                "reason":   True,
                "from":     True,
            }
        })
        if not data or "bytes" not in data:
            return

        txs = data["bytes"]
        if isinstance(txs, dict):
            txs = [txs]

        if not w._initialized:
            for tx in (txs or []):
                txid = str(tx.get("id", ""))
                if txid:
                    w._seen_ids.add(txid)
            w._initialized = True
            return

        for tx in sorted(txs or [], key=lambda x: int(x.get("dateline") or 0)):
            txid = str(tx.get("id", ""))
            if not txid or txid in w._seen_ids:
                continue
            w._seen_ids.add(txid)
            from_data = tx.get("from") or {}
            if isinstance(from_data, list) and from_data:
                from_data = from_data[0]
            from_user = from_data.get("username", "") if isinstance(from_data, dict) else ""
            await w.callback({
                "event":     "bytes_received",
                "id":        txid,
                "amount":    float(tx.get("amount") or 0),
                "reason":    tx.get("reason", ""),
                "from_user": from_user,
                "dateline":  int(tx.get("dateline") or 0),
            })


# ── Helpers ────────────────────────────────────────────────────────────────────

def _strip_bbcode(text: str) -> str:
    """Remove BBCode tags and collapse whitespace."""
    import re as _re
    text = _re.sub(r'\[/?[a-zA-Z][^\]]*\]', '', text)
    return _re.sub(r'\s+', ' ', text).strip()
