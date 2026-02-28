"""
HFBytes — send and read bytes transactions on HackForums.
Read requires 'Bytes' scope. Write requires 'Bytes Write' scope.

BUG FIX #1: All methods now call self.read_sync() / self.write_sync() instead
of the bare async self.read() / self.write() coroutines that were never awaited.
"""

from HFClient import HFClient

_FIELDS = {
    "id":       True,
    "amount":   True,
    "dateline": True,
    "type":     True,
    "reason":   True,
    "from":     True,
    "to":       True,
    "post":     True,
}

_FIELDS_LIGHT = {
    "id":       True,
    "amount":   True,
    "dateline": True,
    "type":     True,
    "reason":   True,
    "from":     True,
}


class HFBytes(HFClient):
    """
    Send and read bytes transactions (/read/bytes and /write/bytes endpoints).

    Usage:
        bytes_api = HFBytes(access_token)
        txid = bytes_api.send(to_uid=1, amount=5, reason="Thanks!")
        bytes_api.deposit(100)
        bytes_api.withdraw(50)
        bytes_api.bump(tid=6083735)
        txs = bytes_api.get_received(uid=761578)
    """

    def send(self, to_uid: int, amount: int, reason: str = "", pid: int = 0) -> str | None:
        """Send bytes to a user. Returns transaction ID or None on failure."""
        ask: dict = {
            "_uid":    str(to_uid),
            "_amount": str(amount),
        }
        if reason: ask["_reason"] = reason
        if pid:    ask["_pid"]    = str(pid)
        data = self.write_sync({"bytes": ask})
        rows = self._unwrap(data, "bytes")
        return rows[0].get("id") if rows else None

    def deposit(self, amount: int) -> bool:
        """Deposit bytes from your account into your API client vault."""
        data = self.write_sync({"bytes": {"_deposit": amount}})
        return data is not None

    def withdraw(self, amount: int) -> bool:
        """Withdraw bytes from your API client vault back to your account."""
        data = self.write_sync({"bytes": {"_withdraw": amount}})
        return data is not None

    def bump(self, tid: int) -> bool:
        """Bump a thread using bytes."""
        data = self.write_sync({"bytes": {"_bump": tid}})
        return data is not None

    def get_received(
        self,
        uid: int,
        page: int = 1,
        perpage: int = 20,
        include_post: bool = False,
    ) -> list[dict]:
        """Get bytes transactions received by a user."""
        fields = dict(_FIELDS) if include_post else dict(_FIELDS_LIGHT)
        data = self.read_sync({"bytes": {
            "_to":      [uid],
            "_page":    page,
            "_perpage": perpage,
            **fields,
        }})
        return self._unwrap(data, "bytes")

    def get_sent(
        self,
        uid: int,
        page: int = 1,
        perpage: int = 20,
        include_post: bool = False,
    ) -> list[dict]:
        """Get bytes transactions sent by a user."""
        fields = dict(_FIELDS) if include_post else dict(_FIELDS_LIGHT)
        data = self.read_sync({"bytes": {
            "_from":    [uid],
            "_page":    page,
            "_perpage": perpage,
            **fields,
        }})
        return self._unwrap(data, "bytes")

    def get_by_id(self, tx_ids: list[int], include_post: bool = False) -> list[dict]:
        """Get specific transactions by ID."""
        fields = dict(_FIELDS) if include_post else dict(_FIELDS_LIGHT)
        data = self.read_sync({"bytes": {"_id": tx_ids, **fields}})
        return self._unwrap(data, "bytes")

    def get_all_received(
        self,
        uid: int,
        perpage: int = 20,
        max_pages: int = 50,
        stop_at_id: int = 0,
        include_post: bool = False,
    ) -> list[dict]:
        """Get ALL bytes received by a user, automatically paginating."""
        from HFPaginator import HFPaginator
        return HFPaginator.get_all_bytes_received(self, uid, perpage, max_pages, stop_at_id)

    def get_all_sent(
        self,
        uid: int,
        perpage: int = 20,
        max_pages: int = 50,
    ) -> list[dict]:
        """Get ALL bytes sent by a user, automatically paginating."""
        from HFPaginator import HFPaginator
        return HFPaginator.get_all_bytes_sent(self, uid, perpage, max_pages)
