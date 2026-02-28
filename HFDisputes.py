"""
HFDisputes — read dispute data from HackForums.
Requires 'Contracts' scope.

BUG FIX #1: All self.read() calls changed to self.read_sync().

IMPORTANT: Querying disputes by _uid 503s on the HF API.
Always query by _cid (contract IDs) or _cdid (dispute IDs).
"""

from HFClient import HFClient

_FIELDS = {
    "cdid": True, "contractid": True, "claimantuid": True,
    "defendantuid": True, "dateline": True, "status": True,
    "dispute_tid": True, "claimantnotes": True, "defendantnotes": True,
}


class HFDisputes(HFClient):
    """Read dispute data (/read/disputes endpoint)."""

    def get(self, cdids: list[int]) -> list[dict]:
        """Get disputes by dispute ID(s)."""
        data = self.read_sync({"disputes": {"_cdid": cdids, **_FIELDS}})
        return self._unwrap(data, "disputes") or self._unwrap(data, "bratings")

    def get_by_contracts(self, cids: list[int]) -> list[dict]:
        """
        Get disputes for specific contract ID(s).
        This is the recommended way to query — _uid queries return 503.
        """
        if not cids:
            return []
        data = self.read_sync({"disputes": {"_cid": [int(c) for c in cids], **_FIELDS}})
        return self._unwrap(data, "disputes") or self._unwrap(data, "bratings")

    def get_by_claimant(self, uid: int) -> list[dict]:
        """Get disputes where a user is the claimant."""
        data = self.read_sync({"disputes": {"_claimantuid": [uid], **_FIELDS}})
        return self._unwrap(data, "disputes") or self._unwrap(data, "bratings")

    def get_by_defendant(self, uid: int) -> list[dict]:
        """Get disputes where a user is the defendant."""
        data = self.read_sync({"disputes": {"_defendantuid": [uid], **_FIELDS}})
        return self._unwrap(data, "disputes") or self._unwrap(data, "bratings")
