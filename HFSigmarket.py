"""
HFSigmarket — read signature market listings and orders.
Requires sigmarket scope.

BUG FIX #1: self.read() changed to self.read_sync().
"""

from HFClient import HFClient

_MARKET_FIELDS = {
    "uid":       True,
    "price":     True,
    "duration":  True,
    "active":    True,
    "sig":       True,
    "dateadded": True,
    "ppd":       True,
}

_ORDER_FIELDS = {
    "smid":      True,
    "startdate": True,
    "enddate":   True,
    "price":     True,
    "duration":  True,
    "active":    True,
}


class HFSigmarket(HFClient):
    """Read sigmarket listings and orders (/read/sigmarket endpoint)."""

    def get_listings(
        self,
        uid: int = 0,
        page: int = 1,
        perpage: int = 20,
        include_user: bool = False,
    ) -> list[dict]:
        """Get available signature market listings (type=market)."""
        ask: dict = {
            "_type":    "market",
            "_page":    [page],
            "_perpage": [perpage],
            **_MARKET_FIELDS,
        }
        if uid:
            ask["_uid"] = [uid]
        if include_user:
            ask["user"] = {
                "uid":        True,
                "username":   True,
                "reputation": True,
                "postnum":    True,
                "usergroup":  True,
            }
        data = self.read_sync(ask)
        return self._unwrap(data, "sigmarket")

    def get_orders(
        self,
        buyer_uid: int = 0,
        seller_uid: int = 0,
        smid: int = 0,
        page: int = 1,
        perpage: int = 20,
        include_users: bool = False,
    ) -> list[dict]:
        """Get signature market orders (type=order)."""
        ask: dict = {
            "_type":    "order",
            "_page":    [page],
            "_perpage": [perpage],
            **_ORDER_FIELDS,
        }
        if buyer_uid:  ask["_buyer"]  = [buyer_uid]
        if seller_uid: ask["_seller"] = [seller_uid]
        if smid:       ask["_smid"]   = [smid]
        if include_users:
            user_fields = {"uid": True, "username": True, "reputation": True}
            ask["buyer"]  = user_fields
            ask["seller"] = user_fields
        data = self.read_sync(ask)
        return self._unwrap(data, "sigmarket")

    def get_all_listings(
        self,
        uid: int = 0,
        perpage: int = 20,
        max_pages: int = 50,
        active_only: bool = False,
    ) -> list[dict]:
        """Get all sigmarket listings, automatically paginating."""
        from HFPaginator import HFPaginator
        results = HFPaginator._paginate(
            fetch_fn=lambda page: self.get_listings(uid=uid, page=page, perpage=perpage),
            max_pages=max_pages,
        )
        if active_only:
            return [r for r in results if str(r.get("active", "0")) == "1"]
        return results

    def get_all_orders(
        self,
        buyer_uid: int = 0,
        seller_uid: int = 0,
        perpage: int = 20,
        max_pages: int = 50,
        active_only: bool = False,
    ) -> list[dict]:
        """Get all sigmarket orders, automatically paginating."""
        from HFPaginator import HFPaginator
        results = HFPaginator._paginate(
            fetch_fn=lambda page: self.get_orders(
                buyer_uid=buyer_uid, seller_uid=seller_uid, page=page, perpage=perpage
            ),
            max_pages=max_pages,
        )
        if active_only:
            return [r for r in results if str(r.get("active", "0")) == "1"]
        return results

    def get_order(self, smid: int, include_users: bool = False) -> dict | None:
        """Get a single sigmarket order by order ID."""
        rows = self.get_orders(smid=smid, include_users=include_users)
        return rows[0] if rows else None
