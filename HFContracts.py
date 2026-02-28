"""
HFContracts — read contract data from HackForums.
Requires 'Contracts' scope.

BUG FIX #1: All direct self.read() calls changed to self.read_sync().
Internal fetch_page lambdas passed to HFPaginator also updated.
"""

from HFClient import HFClient

_FIELDS = {
    "cid":           True,
    "dateline":      True,
    "otherdateline": True,
    "public":        True,
    "timeout_days":  True,
    "timeout":       True,
    "status":        True,
    "istatus":       True,
    "ostatus":       True,
    "cancelstatus":  True,
    "type":          True,
    "tid":           True,
    "inituid":       True,
    "otheruid":      True,
    "muid":          True,
    "iprice":        True,
    "oprice":        True,
    "iproduct":      True,
    "oproduct":      True,
    "icurrency":     True,
    "ocurrency":     True,
    "terms":         True,
    "iaddress":      True,
    "oaddress":      True,
}

_SUMMARY_FIELDS = {
    "cid":          True,
    "status":       True,
    "istatus":      True,
    "ostatus":      True,
    "cancelstatus": True,
    "type":         True,
    "inituid":      True,
    "otheruid":     True,
    "muid":         True,
    "iproduct":     True,
    "iprice":       True,
    "icurrency":    True,
    "dateline":     True,
}


def _is_set(val) -> bool:
    return bool(val) and str(val) not in ("", "0", "None", "null")


class HFContracts(HFClient):
    """Read contract data (/read/contracts endpoint)."""

    def get(self, cids: list[int], fields: dict = None) -> list[dict]:
        """Get contracts by contract ID(s)."""
        data = self.read_sync({"contracts": {"_cid": cids, **(fields or _FIELDS)}})
        return self._unwrap(data, "contracts")

    def get_by_user(self, uid: int, page: int = 1, perpage: int = 30) -> list[dict]:
        """Get contracts involving a user."""
        data = self.read_sync({"contracts": {
            "_uid":     [uid],
            "_page":    page,
            "_perpage": perpage,
            **_FIELDS,
        }})
        return self._unwrap(data, "contracts")

    def get_all_by_user(self, uid: int, perpage: int = 30, max_pages: int = 50) -> list[dict]:
        """Get ALL contracts for a user, automatically paginating."""
        from HFPaginator import HFPaginator
        return HFPaginator.get_all_contracts_by_user(self, uid, perpage, max_pages)

    def get_full(self, cid: int) -> dict | None:
        """Get a single contract with all fields and nested objects."""
        rows = self.get([cid], fields={
            **_FIELDS,
            "template_id": True,
            "inituser":    ["uid", "username", "reputation", "myps"],
            "otheruser":   ["uid", "username", "reputation", "myps"],
            "escrow":      ["uid", "username", "reputation"],
            "thread":      ["tid", "subject"],
            "idispute":    ["cdid", "status", "claimantuid", "defendantuid", "claimantnotes"],
            "odispute":    ["cdid", "status", "claimantuid", "defendantuid", "claimantnotes"],
            "ibrating":    ["crid", "amount", "message", "fromid", "dateline"],
            "obrating":    ["crid", "amount", "message", "fromid", "dateline"],
        })
        return rows[0] if rows else None

    def get_active(self, uid: int, max_pages: int = 10) -> list[dict]:
        inactive = {"cancelled", "complete", "incomplete"}
        return [
            c for c in self.get_all_by_user(uid, max_pages=max_pages)
            if str(c.get("status", "")).lower() not in inactive
        ]

    def get_pending(self, uid: int, max_pages: int = 10) -> list[dict]:
        return [
            c for c in self.get_all_by_user(uid, max_pages=max_pages)
            if (
                str(c.get("istatus", "")).lower() == "pending"
                or str(c.get("ostatus", "")).lower() == "pending"
            )
        ]

    def get_complete(self, uid: int, max_pages: int = 10) -> list[dict]:
        return [
            c for c in self.get_all_by_user(uid, max_pages=max_pages)
            if str(c.get("status", "")).lower() == "complete"
        ]

    def get_incomplete(self, uid: int, max_pages: int = 10) -> list[dict]:
        return [
            c for c in self.get_all_by_user(uid, max_pages=max_pages)
            if str(c.get("status", "")).lower() == "incomplete"
        ]

    def get_cancelled(self, uid: int, max_pages: int = 10) -> list[dict]:
        return [
            c for c in self.get_all_by_user(uid, max_pages=max_pages)
            if str(c.get("status", "")).lower() == "cancelled"
        ]

    def get_by_status(self, uid: int, status: str, max_pages: int = 10) -> list[dict]:
        return [
            c for c in self.get_all_by_user(uid, max_pages=max_pages)
            if str(c.get("status", "")).lower() == status.lower()
        ]

    def get_disputed(self, uid: int, max_pages: int = 10) -> list[dict]:
        from HFPaginator import HFPaginator

        def fetch_page(page):
            data = self.read_sync({"contracts": {
                "_uid":     [uid],
                "_page":    page,
                "_perpage": 30,
                **_SUMMARY_FIELDS,
                "idispute": ["cdid", "status", "claimantuid", "defendantuid"],
                "odispute": ["cdid", "status", "claimantuid", "defendantuid"],
            }})
            return self._unwrap(data, "contracts")

        all_contracts = HFPaginator._paginate(fetch_page, max_pages=max_pages)
        return [c for c in all_contracts if c.get("idispute") or c.get("odispute")]

    def get_cancellation_requested(self, uid: int, max_pages: int = 10) -> list[dict]:
        return [
            c for c in self.get_all_by_user(uid, max_pages=max_pages)
            if _is_set(c.get("cancelstatus"))
        ]

    def get_middleman_contracts(self, uid: int, max_pages: int = 10) -> list[dict]:
        from HFPaginator import HFPaginator

        def fetch_page(page):
            data = self.read_sync({"contracts": {
                "_uid":     [uid],
                "_page":    page,
                "_perpage": 30,
                **_SUMMARY_FIELDS,
                "escrow":   ["uid", "username", "reputation"],
            }})
            return self._unwrap(data, "contracts")

        all_contracts = HFPaginator._paginate(fetch_page, max_pages=max_pages)
        return [c for c in all_contracts if _is_set(c.get("muid"))]

    def is_middleman_contract(self, cid: int) -> bool:
        rows = self.get([cid], fields={"cid": True, "muid": True})
        return _is_set(rows[0].get("muid")) if rows else False

    def get_by_type(self, uid: int, contract_type: str, max_pages: int = 10) -> list[dict]:
        return [
            c for c in self.get_all_by_user(uid, max_pages=max_pages)
            if str(c.get("type", "")).lower() == contract_type.lower()
        ]

    def get_with_ratings(self, uid: int, max_pages: int = 10) -> list[dict]:
        from HFPaginator import HFPaginator

        def fetch_page(page):
            data = self.read_sync({"contracts": {
                "_uid":     [uid],
                "_page":    page,
                "_perpage": 30,
                **_SUMMARY_FIELDS,
                "ibrating": ["crid", "amount", "message", "fromid"],
                "obrating": ["crid", "amount", "message", "fromid"],
            }})
            return self._unwrap(data, "contracts")

        all_contracts = HFPaginator._paginate(fetch_page, max_pages=max_pages)
        return [c for c in all_contracts if c.get("ibrating") or c.get("obrating")]

    def get_summary(self, uid: int, max_pages: int = 10) -> dict:
        from HFPaginator import HFPaginator

        def fetch_page(page):
            data = self.read_sync({"contracts": {
                "_uid":     [uid],
                "_page":    page,
                "_perpage": 30,
                **_SUMMARY_FIELDS,
                "idispute": ["cdid"],
                "odispute": ["cdid"],
            }})
            return self._unwrap(data, "contracts")

        all_contracts = HFPaginator._paginate(fetch_page, max_pages=max_pages)

        by_status: dict[str, int] = {}
        by_type:   dict[str, int] = {}
        middleman  = 0
        disputed   = 0
        cancel_req = 0

        for c in all_contracts:
            status = str(c.get("status", "unknown")).lower()
            ctype  = str(c.get("type",   "unknown")).lower()
            by_status[status] = by_status.get(status, 0) + 1
            by_type[ctype]    = by_type.get(ctype, 0) + 1
            if _is_set(c.get("muid")):            middleman  += 1
            if c.get("idispute") or c.get("odispute"): disputed += 1
            if _is_set(c.get("cancelstatus")):    cancel_req += 1

        return {
            "total":                 len(all_contracts),
            "by_status":             by_status,
            "by_type":               by_type,
            "middleman":             middleman,
            "disputed":              disputed,
            "cancellation_pending":  cancel_req,
        }
