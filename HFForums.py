"""
HFForums — get forum info by forum ID.
Requires 'Posts' scope.

BUG FIX #1: self.read() changed to self.read_sync().
"""

from HFClient import HFClient


class HFForums(HFClient):
    """Get forum info (/read/forums endpoint)."""

    def get(self, fid: int) -> dict | None:
        """Get info for a single forum."""
        forums = self.get_many([fid])
        return forums[0] if forums else None

    def get_many(self, fids: list[int]) -> list[dict]:
        """Get info for multiple forums."""
        data = self.read_sync({"forums": {
            "_fid":        fids,
            "fid":         True,
            "name":        True,
            "description": True,
            "type":        True,
        }})
        return self._unwrap(data, "forums")
