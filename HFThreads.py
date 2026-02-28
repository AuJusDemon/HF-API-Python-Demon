"""
HFThreads — read and create threads on HackForums.
Read requires 'Posts' scope. Create requires 'Posts Write' scope.

BUG FIX #1: All self.read() / self.write() calls changed to
self.read_sync() / self.write_sync().

API NOTE — lastposter is a free field:
    Every thread object includes lastposter (the username of whoever last
    replied) at no extra cost. poll_lastpost() requests it by default so
    callers get the replier's username without a follow-up users _uid call.
    Use lastposteruid if you need the UID too.

API NOTE — get_by_user() returns OP threads only:
    threads _uid only returns threads where the user is the original poster.
    Threads the user replied to but didn't create are invisible here.
    Use posts _uid (HFPosts.get_by_user) to discover all threads a user
    has participated in, then resolve to thread objects via get_many().
"""

from HFClient import HFClient

_FIELDS = {
    "tid": True, "uid": True, "fid": True, "subject": True,
    "closed": True, "numreplies": True, "views": True, "dateline": True,
    "firstpost": True, "lastpost": True, "lastposter": True,
    "lastposteruid": True, "prefix": True, "icon": True,
    "poll": True, "username": True, "sticky": True, "bestpid": True,
}


class HFThreads(HFClient):
    """Read and create threads (/read/threads and /write/threads endpoints)."""

    def get(self, tid: int) -> dict | None:
        """Get a single thread by ID."""
        threads = self.get_many([tid])
        return threads[0] if threads else None

    def get_many(self, tids: list[int]) -> list[dict]:
        """Get multiple threads by ID in one request (max 30)."""
        if not tids:
            return []
        data = self.read_sync({"threads": {"_tid": tids, **_FIELDS}})
        return self._unwrap(data, "threads")

    def get_by_forum(self, fid: int) -> list[dict]:
        """Get recent threads in a forum."""
        data = self.read_sync({"threads": {"_fid": [fid], **_FIELDS}})
        return self._unwrap(data, "threads")

    def get_by_user(self, uid: int, page: int = 1, perpage: int = 20) -> list[dict]:
        """
        Get threads created by a user (OP threads only).

        WARNING: threads _uid only returns threads where this user is the
        original poster. Threads the user replied to but didn't start are
        not returned here. Use HFPosts.get_by_user() (posts _uid) to find
        all threads a user has participated in.
        """
        data = self.read_sync({"threads": {
            "_uid": [uid], "_page": page, "_perpage": perpage,
            **_FIELDS,
        }})
        return self._unwrap(data, "threads")

    def poll_lastpost(self, tids: list[int]) -> list[dict]:
        """
        Lightweight poll — fetches lastpost, lastposter, lastposteruid,
        numreplies, and subject for the given thread IDs.

        lastposter is the username of whoever last replied and is included
        free on every thread response — no follow-up users _uid call needed.
        Use lastposteruid if you also need their UID.
        """
        if not tids:
            return []
        data = self.read_sync({"threads": {
            "_tid":          tids,
            "tid":           True,
            "subject":       True,
            "lastpost":      True,
            "lastposter":    True,  
            "lastposteruid": True,
            "numreplies":    True,
        }})
        return self._unwrap(data, "threads")

    def create(self, fid: int, subject: str, message: str) -> dict | None:
        """Create a new thread. Requires 'Posts Write' scope."""
        data = self.write_sync({"threads": {
            "_fid":     fid,
            "_subject": subject,
            "_message": message,
        }})
        rows = self._unwrap(data, "threads")
        return rows[0] if rows else None

    def get_all_by_user(self, uid: int, perpage: int = 20, max_pages: int = 50) -> list[dict]:
        """
        Get ALL threads created by a user, automatically paginating.

        Note: returns OP threads only. See get_by_user() for the full caveat.
        """
        from HFPaginator import HFPaginator
        return HFPaginator.get_all_threads_by_user(self, uid, perpage, max_pages)
