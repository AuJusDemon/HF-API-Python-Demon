"""
HFWatcher.py — Polling watcher for HackForums events.

New event types (all fired from _poll_thread at zero extra API cost):
  - thread_best_answer : someone marked a post as the best answer in the thread
  - thread_view_spike  : views jumped by VIEW_SPIKE or more in one poll cycle
  - thread_closed      : thread transitioned from open to closed

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

# Views must jump this much in a single poll cycle to fire thread_view_spike.
_VIEW_SPIKE_THRESHOLD = 500


# ── Watch job dataclasses ──────────────────────────────────────────────────────

@dataclass
class _ThreadWatch:
    tid:      int
    callback: Callback
    interval: int = 60
    my_uid:   str = ""   # token owner UID — if set, skips post fetch when we were last poster

    # Internal poll state
    _last_post:      int = field(default=0,   init=False, repr=False)
    _num_replies:    int = field(default=0,   init=False, repr=False)  # Bug #3: edit detection
    _lastposteruid:  str = field(default="",  init=False, repr=False)  # Bug #1
    _bestpid:        str = field(default="",  init=False, repr=False)  # best answer tracking
    _views:          int = field(default=0,   init=False, repr=False)  # view spike tracking
    _closed:         str = field(default="",  init=False, repr=False)  # closed detection
    _seen_pids:      set = field(default_factory=set, init=False, repr=False)


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

    IMPORTANT — owner-scoped endpoints:
        The contracts, disputes, and bratings endpoints only return data for
        the token's own authenticated user. This watcher's watch_bytes() uses
        the token owner's UID automatically. There is no way to watch another
        user's contracts or bytes with your own token.
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

    def watch_thread(
        self,
        tid: int,
        callback: Callback,
        interval: int = 60,
        my_uid: str = "",
    ) -> "HFWatcher":
        """
        Watch a thread for new replies.

        Args:
            tid:      Thread ID to watch.
            callback: Async function called on new reply/event.
            interval: Poll interval in seconds (default 60).
            my_uid:   Token owner's HF UID as a string. When provided, the
                      watcher skips the posts fetch on cycles where the last
                      poster was you — saves one API call per self-post.

        Callback receives one of these event dicts depending on what changed:

            thread_reply:
                { "event": "thread_reply", "tid": int, "pid": int|None,
                  "uid": str, "username": str, "subject": str,
                  "snippet": str, "dateline": int }

            thread_best_answer  (zero extra API cost):
                { "event": "thread_best_answer", "tid": int,
                  "pid": str, "subject": str }

            thread_view_spike  (zero extra API cost):
                { "event": "thread_view_spike", "tid": int, "subject": str,
                  "spike": int, "views": int }

            thread_closed  (zero extra API cost):
                { "event": "thread_closed", "tid": int, "subject": str }
        """
        self._thread_watches.append(
            _ThreadWatch(tid=tid, callback=callback, interval=interval, my_uid=my_uid)
        )
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
        # Bug #1 fix: added lastposteruid (was missing — caused redundant post fetches).
        # Also added views, bestpid, closed for zero-cost event detection.
        meta = await self._hf.read({
            "threads": {
                "_tid":          [w.tid],
                "tid":           True,
                "subject":       True,
                "lastpost":      True,
                "lastposteruid": True,   # Bug #1 fix: skip fetch when we were last poster
                "lastposter":    True,   # free username string, no extra cost
                "numreplies":    True,
                "views":         True,   # NEW: view spike detection
                "bestpid":       True,   # NEW: best answer detection
                "closed":        True,   # NEW: thread closed detection
            }
        })

        if not meta or "threads" not in meta:
            return

        threads = meta["threads"]
        if isinstance(threads, dict):
            threads = [threads]
        if not threads:
            log.info(f"watch_thread tid={w.tid} — thread absent from response (deleted/private/moved)")
            return

        t             = threads[0]
        lastpost      = int(t.get("lastpost") or 0)
        numreplies    = int(t.get("numreplies") or 0)
        lastposteruid = str(t.get("lastposteruid") or "")
        lastposter    = t.get("lastposter") or ""
        subject       = t.get("subject", "Thread")
        bestpid       = str(t.get("bestpid") or "")
        views         = int(t.get("views") or 0)
        closed        = str(t.get("closed") or "")

        # ── Seed on first poll — don't fire for existing state ─────────────────
        if w._last_post == 0:
            w._last_post     = lastpost
            w._num_replies   = numreplies
            w._lastposteruid = lastposteruid
            w._bestpid       = bestpid
            w._views         = views
            w._closed        = closed
            return

        # ── NEW: Best answer marked ───────────────────────────────────────────
        # bestpid changes when someone votes a post as the best answer.
        # "0" means no best answer set — ignore that transition.
        if bestpid and bestpid != "0" and bestpid != w._bestpid and w._bestpid != "":
            await w.callback({
                "event":   "thread_best_answer",
                "tid":     w.tid,
                "pid":     bestpid,
                "subject": subject,
            })
            log.debug(f"watch_thread tid={w.tid}: best answer set pid={bestpid}")
        w._bestpid = bestpid

        # ── NEW: View spike ───────────────────────────────────────────────────
        if w._views > 0 and views > 0 and (views - w._views) >= _VIEW_SPIKE_THRESHOLD:
            await w.callback({
                "event":   "thread_view_spike",
                "tid":     w.tid,
                "subject": subject,
                "spike":   views - w._views,
                "views":   views,
            })
            log.debug(f"watch_thread tid={w.tid}: view spike +{views - w._views}")
        w._views = views

        # ── NEW: Thread closed ────────────────────────────────────────────────
        if closed == "1" and w._closed != "1":
            await w.callback({
                "event":   "thread_closed",
                "tid":     w.tid,
                "subject": subject,
            })
            log.debug(f"watch_thread tid={w.tid}: thread closed")
        w._closed = closed

        # ── No new post — nothing more to do ─────────────────────────────────
        if lastpost <= w._last_post:
            return

        # ── Bug #1 fix: skip post fetch when token owner was last poster ──────
        if w.my_uid and lastposteruid == w.my_uid:
            log.debug(f"watch_thread tid={w.tid}: last poster is us ({w.my_uid}), skipping post fetch")
            w._last_post     = lastpost
            w._num_replies   = numreplies
            w._lastposteruid = lastposteruid
            return

        # ── Bug #3 fix: skip post fetch when numreplies unchanged (it's an edit)
        # lastpost updates on edits too, but numreplies does not.
        if w._num_replies > 0 and numreplies == w._num_replies:
            log.debug(f"watch_thread tid={w.tid}: numreplies={numreplies} unchanged — edit, skipping post fetch")
            w._last_post     = lastpost
            w._lastposteruid = lastposteruid
            return

        # ── Fetch newest posts ────────────────────────────────────────────────
        last_page = max(1, (numreplies + 1 + 9) // 10)
        post_data = await self._hf.read({
            "posts": {
                "_tid":     [w.tid],
                "_page":    last_page,
                "_perpage": 10,
                "pid":      True,
                "uid":      True,
                "username": True,   # Bug #2 fix: was missing, free inline field
                "dateline": True,
                "message":  True,
            }
        })

        w._last_post     = lastpost
        w._num_replies   = numreplies
        w._lastposteruid = lastposteruid

        if not post_data or "posts" not in post_data:
            # Couldn't fetch posts — still fire a minimal reply event so caller
            # isn't completely dark. uid/username/snippet are unknown.
            await w.callback({
                "event":    "thread_reply",
                "tid":      w.tid,
                "pid":      None,
                "uid":      lastposteruid,
                "username": lastposter,
                "subject":  subject,
                "snippet":  "",
                "dateline": lastpost,
            })
            return

        posts = post_data["posts"]
        if isinstance(posts, dict):
            posts = [posts]

        posts.sort(key=lambda p: int(p.get("dateline") or 0))

        for post in posts:
            pid      = int(post.get("pid") or 0)
            dateline = int(post.get("dateline") or 0)

            if dateline <= w._last_post - (lastpost - w._last_post):
                # Older than the window we care about
                continue
            if pid in w._seen_pids:
                continue

            w._seen_pids.add(pid)
            await w.callback({
                "event":    "thread_reply",
                "tid":      w.tid,
                "pid":      pid,
                "uid":      str(post.get("uid", "")),
                "username": post.get("username") or lastposter,   # Bug #2 fix
                "subject":  subject,
                "snippet":  _strip_bbcode(post.get("message", ""))[:200],
                "dateline": dateline,
            })

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
                "_fid":      [w.fid],
                "_page":     1,
                "_perpage":  20,
                "tid":       True,
                "uid":       True,
                "subject":   True,
                "dateline":  True,
                "lastpost":  True,
                "username":  True,
                "firstpost": True,
            }
        })
        if not data or "threads" not in data:
            return

        threads = data["threads"]
        if isinstance(threads, dict):
            threads = [threads]

        for t in sorted(threads or [], key=lambda x: int(x.get("dateline") or 0)):
            tid      = int(t.get("tid") or 0)
            dateline = int(t.get("dateline") or 0)

            if not tid or tid in w._seen_tids:
                continue

            if not w._initialized:
                w._seen_tids.add(tid)
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

        w._initialized = True

        if len(w._seen_tids) > 2000:
            w._seen_tids = set(list(w._seen_tids)[-1000:])

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
            for t in sorted(rows or [], key=lambda x: int(x.get("dateline") or 0)):
                tid      = int(t.get("tid") or 0)
                dateline = int(t.get("dateline") or 0)
                if not tid:
                    continue
                if not w._initialized:
                    w._seen_tids.add(tid)
                    continue
                if tid in w._seen_tids:
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
                for p in sorted(posts or [], key=lambda p: int(p.get("dateline") or 0)):
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
        fids = w.fids or []
        for fid in fids:
            data = await self._hf.read({
                "threads": {
                    "_fid":     [fid],
                    "_page":    1,
                    "_perpage": 20,
                    "tid":      True,
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
                tid     = int(t.get("tid") or 0)
                subject = t.get("subject", "")
                if not tid:
                    continue

                # Bug #6 fix: check _seen_tids (not _seen_pids) for thread IDs
                if tid in w._seen_tids:
                    continue

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
        if w._my_uid is None:
            me_data = await self._hf.read({"me": {"uid": True}})
            if not me_data or "me" not in me_data:
                return
            me = me_data["me"]
            if isinstance(me, list):
                me = me[0] if me else {}
            uid = int(me.get("uid") or 0)
            if not uid:
                # Transient failure — leave as None and retry next poll.
                # Bug #4: old code set this to 0 and permanently killed the watcher.
                return
            w._my_uid = uid

        data = await self._hf.read({
            "bytes": {
                "_to":      [w._my_uid],
                "_perpage": 10,
                "id":       True,
                "amount":   True,
                "reason":   True,
                "dateline": True,
                "from":     True,
            }
        })
        if not data or "bytes" not in data:
            return

        txs = data["bytes"]
        if isinstance(txs, dict):
            txs = [txs]

        for tx in sorted(txs or [], key=lambda x: int(x.get("dateline") or 0)):
            txid = str(tx.get("id") or "")
            if not txid:
                continue
            if not w._initialized:
                w._seen_ids.add(txid)
                continue
            if txid in w._seen_ids:
                continue

            w._seen_ids.add(txid)
            await w.callback({
                "event":     "bytes_received",
                "id":        txid,
                "amount":    float(tx.get("amount") or 0),
                "reason":    tx.get("reason") or "",
                "from_user": str(tx.get("from") or ""),
                "dateline":  int(tx.get("dateline") or 0),
            })

        w._initialized = True

        if len(w._seen_ids) > 500:
            w._seen_ids = set(list(w._seen_ids)[-250:])


# ── Helpers ────────────────────────────────────────────────────────────────────

def _strip_bbcode(text: str) -> str:
    """Strip BBCode tags and collapse whitespace."""
    text = re.sub(r"\[/?[a-zA-Z][^\]]*\]", "", text)
    return re.sub(r"\s+", " ", text).strip()
