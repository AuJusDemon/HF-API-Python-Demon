"""
HFContracts — read contract data from HackForums.
Requires 'Contracts' scope.
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
    """
    Read contract data (/read/contracts endpoint).

    OWNER-SCOPED: The contracts endpoint only returns contracts for the
    authenticated token's own user. You cannot read another user's contracts
    with your token. If you need another user's data, they must OAuth and
    you must use their token.
    """

    def get(self, cids: list[int], fields: dict = None) -> list[dict]:
        """
        Get contracts by specific contract ID(s).

        This is the only way to look up a contract you are NOT a party to,
        but only if the contract is public. Private contracts by CID that
        don't involve you will return empty.
        """
        data = self.read_sync({"contracts": {"_cid": cids, **(fields or _FIELDS)}})
        return self._unwrap(data, "contracts")

    def get_mine(self, uid: int, page: int = 1, perpage: int = 30) -> list[dict]:
        """
        Get contracts for the authenticated token owner (single page).

        OWNER-SCOPED: uid must be your own UID from the me endpoint.

        Args:
            uid:     Your UID.
            page:    Page number (default 1).
            perpage: Results per page (default 30, max 30).
        """
        data = self.read_sync({"contracts": {
            "_uid":     [uid],
            "_page":    page,
            "_perpage": perpage,
            **_FIELDS,
        }})
        return self._unwrap(data, "contracts")

    def get_by_user(self, uid: int, page: int = 1, perpage: int = 30) -> list[dict]:
        """Alias for get_mine(). uid must be the token owner's own UID."""
        return self.get_mine(uid, page, perpage)

    def get_all_mine(self, uid: int, perpage: int = 30, max_pages: int = 50) -> list[dict]:
        """
        Get ALL contracts for the authenticated token owner, auto-paginating.

        OWNER-SCOPED: uid must be your own UID from the me endpoint.
        """
        from HFPaginator import HFPaginator
        return HFPaginator.get_all_contracts_by_user(self, uid, perpage, max_pages)

    def get_all_by_user(self, uid: int, perpage: int = 30, max_pages: int = 50) -> list[dict]:
        """Alias for get_all_mine(). uid must be the token owner's own UID."""
        return self.get_all_mine(uid, perpage, max_pages)

    def get_full(self, cid: int) -> dict | None:
        """
        Get a single contract with all fields and nested objects.

        Includes inituser, otheruser, escrow (user objects), thread (linked
        thread), and ibrating/obrating (b-ratings) inline.
        """
        rows = self.get([cid], fields={
            **_FIELDS,
            "template_id": True,
            "inituser":    ["uid", "username", "reputation", "myps"],
            "otheruser":   ["uid", "username", "reputation", "myps"],
            "escrow":      ["uid", "username", "reputation"],
            "thread":      ["tid", "subject"],
            "ibrating":    ["crid", "amount", "message", "fromid", "dateline"],
            "obrating":    ["crid", "amount", "message", "fromid", "dateline"],
        })
        return rows[0] if rows else None

    # ── Filter helpers (all OWNER-SCOPED) ─────────────────────────────────────

    def get_active(self, uid: int, max_pages: int = 10) -> list[dict]:
        """
        Get active contracts (status not cancelled/complete/incomplete).

        OWNER-SCOPED: uid must be your own UID.
        """
        inactive = {"cancelled", "complete", "incomplete"}
        return [
            c for c in self.get_all_mine(uid, max_pages=max_pages)
            if str(c.get("status", "")).lower() not in inactive
        ]

    def get_pending(self, uid: int, max_pages: int = 10) -> list[dict]:
        """
        Get contracts where istatus or ostatus is 'pending'.

        OWNER-SCOPED: uid must be your own UID.
        """
        return [
            c for c in self.get_all_mine(uid, max_pages=max_pages)
            if (
                str(c.get("istatus", "")).lower() == "pending"
                or str(c.get("ostatus", "")).lower() == "pending"
            )
        ]

    def get_complete(self, uid: int, max_pages: int = 10) -> list[dict]:
        """
        Get completed contracts.

        OWNER-SCOPED: uid must be your own UID.
        """
        return [
            c for c in self.get_all_mine(uid, max_pages=max_pages)
            if str(c.get("status", "")).lower() == "complete"
        ]

    def get_incomplete(self, uid: int, max_pages: int = 10) -> list[dict]:
        """
        Get incomplete (timed-out) contracts.

        OWNER-SCOPED: uid must be your own UID.
        """
        return [
            c for c in self.get_all_mine(uid, max_pages=max_pages)
            if str(c.get("status", "")).lower() == "incomplete"
        ]

    def get_cancelled(self, uid: int, max_pages: int = 10) -> list[dict]:
        """
        Get cancelled contracts.

        OWNER-SCOPED: uid must be your own UID.
        """
        return [
            c for c in self.get_all_mine(uid, max_pages=max_pages)
            if str(c.get("status", "")).lower() == "cancelled"
        ]

    def get_disputed(self, uid: int, max_pages: int = 10) -> list[dict]:
        """
        Get contracts that have a dispute.

        OWNER-SCOPED: uid must be your own UID.

        Fetches all contracts then queries the disputes endpoint for those
        contract IDs. Returns only contracts with at least one dispute record.
        Disputes can exist on contracts of any status, including complete and
        cancelled.
        """
        contracts = self.get_all_mine(uid, max_pages=max_pages)
        if not contracts:
            return []
        cids = [int(c["cid"]) for c in contracts if c.get("cid")]
        if not cids:
            return []
        from HFDisputes import HFDisputes
        dispute_rows = HFDisputes(self.token, proxy=self.proxy).get_by_contracts(cids)
        disputed_cids = {str(d.get("contractid")) for d in dispute_rows if d.get("contractid")}
        return [c for c in contracts if str(c.get("cid")) in disputed_cids]

    def get_cancellation_requested(self, uid: int, max_pages: int = 10) -> list[dict]:
        """
        Get contracts where a cancellation has been requested but not yet resolved.

        OWNER-SCOPED: uid must be your own UID.
        """
        return [
            c for c in self.get_all_mine(uid, max_pages=max_pages)
            if _is_set(c.get("cancelstatus"))
        ]

    def get_middleman_contracts(self, uid: int, max_pages: int = 10) -> list[dict]:
        """
        Get contracts that involve a middleman/escrow (muid is set).

        OWNER-SCOPED: uid must be your own UID.
        """
        return [
            c for c in self.get_all_mine(uid, max_pages=max_pages)
            if _is_set(c.get("muid"))
        ]

    def get_by_type(self, uid: int, ctype: str, max_pages: int = 10) -> list[dict]:
        """
        Get contracts filtered by the initiator's position type.

        Args:
            uid:   Your UID (OWNER-SCOPED).
            ctype: One of: buying, selling, exchanging, trading, vouch_copy.
        """
        target = ctype.lower().strip()
        return [
            c for c in self.get_all_mine(uid, max_pages=max_pages)
            if str(c.get("type", "")).lower() == target
        ]

    def get_summary(self, uid: int, max_pages: int = 50) -> dict:
        """
        Return a statistical summary of all contracts for the token owner.

        OWNER-SCOPED: uid must be your own UID.

        Queries the disputes endpoint separately to get an accurate disputed
        count. Returns disputed=0 gracefully if the disputes call fails.

        Returns:
            {
              "total":                int,
              "by_status":            {"active": N, "complete": N, ...},
              "by_type":              {"standard": N, ...},
              "middleman":            int,
              "disputed":             int,
              "cancellation_pending": int,
            }
        """
        contracts = self.get_all_mine(uid, max_pages=max_pages)
        by_status: dict[str, int] = {}
        by_type:   dict[str, int] = {}
        middleman = cancel_pending = 0

        for c in contracts:
            status = str(c.get("status", "unknown")).lower()
            ctype  = str(c.get("type",   "unknown")).lower()
            by_status[status] = by_status.get(status, 0) + 1
            by_type[ctype]    = by_type.get(ctype, 0) + 1
            if _is_set(c.get("muid")):
                middleman += 1
            if _is_set(c.get("cancelstatus")):
                cancel_pending += 1

        disputed = 0
        if contracts:
            cids = [int(c["cid"]) for c in contracts if c.get("cid")]
            try:
                from HFDisputes import HFDisputes
                dispute_rows = HFDisputes(self.token, proxy=self.proxy).get_by_contracts(cids)
                disputed_cids = {str(d.get("contractid")) for d in dispute_rows if d.get("contractid")}
                disputed = len(disputed_cids)
            except Exception:
                pass

        return {
            "total":                len(contracts),
            "by_status":            by_status,
            "by_type":              by_type,
            "middleman":            middleman,
            "disputed":             disputed,
            "cancellation_pending": cancel_pending,
        }
