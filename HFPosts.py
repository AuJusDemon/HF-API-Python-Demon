"""
HFPosts — read and write posts on HackForums.
Read requires 'Posts' scope. Write requires 'Posts Write' scope.

BUG FIX #1: All self.read() / self.write() calls changed to
self.read_sync() / self.write_sync().
"""

from HFClient import HFClient

_FIELDS = {
    "pid": True, "tid": True, "uid": True, "fid": True,
    "dateline": True, "message": True, "subject": True,
    "edituid": True, "edittime": True, "editreason": True,
}


class HFPosts(HFClient):
    """Read and write posts (/read/posts and /write/posts endpoints)."""

    def get(self, pids: list[int]) -> list[dict]:
        """Get posts by post ID(s)."""
        data = self.read_sync({"posts": {"_pid": pids, **_FIELDS}})
        return self._unwrap(data, "posts")

    def get_by_thread(self, tid: int, page: int = 1, perpage: int = 20) -> list[dict]:
        """Get posts in a thread."""
        data = self.read_sync({"posts": {
            "_tid": [tid], "_page": page, "_perpage": perpage,
            **_FIELDS,
        }})
        return self._unwrap(data, "posts")

    def get_by_user(self, uid: int, page: int = 1, perpage: int = 20) -> list[dict]:
        """Get a user's recent posts."""
        data = self.read_sync({"posts": {
            "_uid": [uid], "_page": page, "_perpage": perpage,
            **_FIELDS,
        }})
        return self._unwrap(data, "posts")

    def get_last_page(self, tid: int, numreplies: int, perpage: int = 10) -> int:
        """Calculate the last page number of a thread."""
        return max(1, (numreplies + 1 + perpage - 1) // perpage)

    def reply(self, tid: int, message: str) -> dict | None:
        """Post a reply to a thread. Requires 'Posts Write' scope."""
        data = self.write_sync({"posts": {"_tid": tid, "_message": message}})
        rows = self._unwrap(data, "posts")
        return rows[0] if rows else None

    def get_all_by_user(
        self, uid: int, perpage: int = 20, max_pages: int = 50, stop_at_pid: int = 0
    ) -> list[dict]:
        """Get ALL posts by a user, automatically paginating."""
        from HFPaginator import HFPaginator
        return HFPaginator.get_all_posts_by_user(self, uid, perpage, max_pages, stop_at_pid)

    def get_all_by_thread(self, tid: int, perpage: int = 20, max_pages: int = 50) -> list[dict]:
        """Get ALL posts in a thread, automatically paginating."""
        from HFPaginator import HFPaginator
        return HFPaginator.get_all_posts_by_thread(self, tid, perpage, max_pages)
