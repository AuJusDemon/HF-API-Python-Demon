"""
HFBratings — read b-rating (buyer/seller rating) data.
Requires 'Contracts' scope.

BUG FIX #1: All methods now call self.read_sync() instead of self.read().
self.read() is an async coroutine — calling it without await returns a coroutine
object, not a dict. self.read_sync() runs the coroutine synchronously.
"""

from HFClient import HFClient

_FIELDS = {
    "crid": True, "contractid": True, "fromid": True, "toid": True,
    "dateline": True, "amount": True, "message": True,
}


class HFBratings(HFClient):
    """
    Read b-ratings (/read/bratings endpoint).

    B-ratings are +1/-1 ratings left after a contract completes.
    'amount' is +1 or -1. 'message' is the optional review text.

    Usage:
        ratings_api = HFBratings(access_token)
        ratings = ratings_api.get_received(uid=761578)
        ratings = ratings_api.get_given(uid=761578)
        ratings = ratings_api.get_by_contract(cid=409675)
    """

    def get(self, crids: list[int]) -> list[dict]:
        """Get b-ratings by b-rating ID(s)."""
        data = self.read_sync({"bratings": {"_crid": crids, **_FIELDS}})
        return self._unwrap(data, "bratings")

    def get_received(self, uid: int, page: int = 1, perpage: int = 30) -> list[dict]:
        """Get b-ratings received by a user."""
        data = self.read_sync({"bratings": {
            "_to":      [uid],
            "_page":    page,
            "_perpage": perpage,
            **_FIELDS,
        }})
        return self._unwrap(data, "bratings")

    def get_given(self, uid: int, page: int = 1, perpage: int = 30) -> list[dict]:
        """Get b-ratings given by a user."""
        data = self.read_sync({"bratings": {
            "_from":    [uid],
            "_page":    page,
            "_perpage": perpage,
            **_FIELDS,
        }})
        return self._unwrap(data, "bratings")

    def get_by_contract(self, cid: int) -> list[dict]:
        """Get b-ratings for a specific contract."""
        data = self.read_sync({"bratings": {"_cid": [cid], **_FIELDS}})
        return self._unwrap(data, "bratings")

    def get_score(self, uid: int) -> int:
        """Calculate total b-rating score for a user (sum of received amounts)."""
        ratings = self.get_received(uid, perpage=30)
        return sum(int(r.get("amount", 0)) for r in ratings)

    def get_all_received(self, uid: int, perpage: int = 30, max_pages: int = 50) -> list[dict]:
        """Get ALL b-ratings received by a user, automatically paginating."""
        from HFPaginator import HFPaginator
        return HFPaginator.get_all_bratings_received(self, uid, perpage, max_pages)

    def get_all_given(self, uid: int, perpage: int = 30, max_pages: int = 50) -> list[dict]:
        """Get ALL b-ratings given by a user, automatically paginating."""
        from HFPaginator import HFPaginator
        return HFPaginator.get_all_bratings_given(self, uid, perpage, max_pages)
