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

    OWNER-SCOPED: All _uid queries on the contracts endpoint only return
    contracts for the authenticated token's user. You cannot read another
    user's contracts with your token — use get_mine() (not get_by_user with
    a third-party UID). If you need another user's data, they must OAuth
    and you must use their token.
    """

    def get(self, cids: list[int], fields: dict = None) -> list[dict]:
        """
        Get contracts by specific contract ID(s).

        This is the only way to look up a contract you are NOT a party to —
        but only if the contract is public. Private contracts by CID that
        don't involve you will return empty.
        """
        data = self.read_sync({"contracts": {"_cid": cids, **(fields or _FIELDS)}})
        return self._unwrap(data, "contracts")

    def get_mine(self, page: int = 1, perpage: int = 30) -> list[dict]:
        """
        Get contracts for the authenticated token owner (page by page).

        OWNER-SCOPED: Only returns contracts involving the token's own user.
        There is no way to retrieve another user's contracts with your token.

        Args:
            page:    Page number (default 1).
            perpage: Results per page (default 30, max 30).

        Returns:
            List of contract dicts. Empty if no contracts or token mismatch.
        """
        data = self.read_sync({"contracts": {
            "_uid":     [0],   # 0 = "me" — HF ignores the value, uses the token
            "_page":    page,
            "_perpage": perpage,
            **_FIELDS,
        }})
        return self._unwrap(data, "contracts")

    def get_mine_with_uid(self, uid: int, page: int = 1, perpage: int = 30) -> list[dict]:
        """
        Get contracts, explicitly passing the token owner's own UID.

        Use this when you have the UID already and want to be explicit.
        The uid MUST be the token owner's UID — passing any other UID
        returns empty results silently.

        This is what the bot uses: it always passes my_uid (its own UID from
        the me endpoint) to make the intent clear in the call site.
        """
        data = self.read_sync({"contracts": {
            "_uid":     [uid],
            "_page":    page,
            "_perpage": perpage,
            **_FIELDS,
        }})
        return self._unwrap(data, "contracts")

    # ── Deprecated name — kept as alias so old callers don't break ────────────
    def get_by_user(self, uid: int, page: int = 1, perpage: int = 30) -> list[dict]:
        """
        DEPRECATED — renamed to get_mine_with_uid().

        OWNER-SCOPED: Despite the name, the uid here MUST be the token
        owner's own UID. Passing a third-party UID returns nothing.
        Use get_mine() or get_mine_with_uid(my_uid) instead.
        """
        return self.get_mine_with_uid(uid, page, perpage)

    def get_all_mine(self, perpage: int = 30, max_pages: int = 50) -> list[dict]:
        """
        Get ALL contracts for the authenticated token owner, auto-paginating.

        OWNER-SCOPED: Only returns contracts involving the token's own user.
        """
        from HFPaginator import HFPaginator
        return HFPaginator.get_all_contracts_by_user(self, 0, perpage, max_pages)

    def get_all_by_user(self, uid: int, perpage: int = 30, max_pages: int = 50) -> list[dict]:
        """
        DEPRECATED — renamed to get_all_mine().

        OWNER-SCOPED: uid must be the token owner's own UID.
        """
        from HFPaginator import HFPaginator
        return HFPaginator.get_all_contracts_by_user(self, uid, perpage, max_pages)

    def get_full(self, cid: int) -> dict | None:
        """
        Get a single contract with all fields and nested objects.

        Includes inituser, otheruser, escrow (user objects), thread (linked
        thread), and ibrating/obrating (b-ratings) inline.

        Note on disputes: the contracts endpoint does accept idispute/odispute
        as sub-field lists in the asks dict (matching the disputes endpoint
        schema), but this has not been verified against a live active dispute.
        Use HFDisputes.get_by_contracts([cid]) to fetch dispute data reliably
        until that behaviour is confirmed.
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

    def get_active_mine(self, max_pages: int = 10) -> list[dict]:
        """
        Get active contracts for the token owner (status not cancelled/complete/incomplete).

        OWNER-SCOPED: Only returns your own contracts.
        """
        inactive = {"cancelled", "complete", "incomplete"}
        return [
            c for c in self.get_all_mine(max_pages=max_pages)
            if str(c.get("status", "")).lower() not in inactive
        ]

    def get_active(self, uid: int, max_pages: int = 10) -> list[dict]:
        """DEPRECATED — renamed to get_active_mine(). uid must be token owner's UID."""
        return self.get_active_mine(max_pages=max_pages)

    def get_pending(self, uid: int, max_pages: int = 10) -> list[dict]:
        """
        Get contracts where istatus or ostatus is 'pending'.

        OWNER-SCOPED: uid must be the token owner's own UID.
        """
        return [
            c for c in self.get_all_by_user(uid, max_pages=max_pages)
            if (
                str(c.get("istatus", "")).lower() == "pending"
                or str(c.get("ostatus", "")).lower() == "pending"
            )
        ]

    def get_complete(self, uid: int, max_pages: int = 10) -> list[dict]:
        """
        Get completed contracts.

        OWNER-SCOPED: uid must be the token owner's own UID.
        """
        return [
            c for c in self.get_all_by_user(uid, max_pages=max_pages)
            if str(c.get("status", "")).lower() == "complete"
        ]

    def get_incomplete(self, uid: int, max_pages: int = 10) -> list[dict]:
        """
        Get incomplete contracts.

        OWNER-SCOPED: uid must be the token owner's own UID.
        """
        return [
            c for c in self.get_all_by_user(uid, max_pages=max_pages)
            if str(c.get("status", "")).lower() == "incomplete"
        ]

    def get_summary(self, uid: int, max_pages: int = 50) -> dict:
        """
        Return a statistical summary of all contracts for the token owner.

        OWNER-SCOPED: uid must be the token owner's own UID.

        Returns:
            {
              "total":                int,
              "by_status":            {"active": N, "complete": N, ...},
              "by_type":              {"standard": N, ...},
              "middleman":            int,   # contracts with a middleman
              "disputed":             int,
              "cancellation_pending": int,
            }
        """
        contracts = self.get_all_by_user(uid, max_pages=max_pages)
        by_status: dict[str, int] = {}
        by_type:   dict[str, int] = {}
        middleman = disputed = cancel_pending = 0

        for c in contracts:
            status = str(c.get("status", "unknown")).lower()
            ctype  = str(c.get("type",   "unknown")).lower()
            by_status[status] = by_status.get(status, 0) + 1
            by_type[ctype]    = by_type.get(ctype, 0) + 1
            if _is_set(c.get("muid")):
                middleman += 1
            if str(c.get("cancelstatus", "")).lower() not in ("", "0", "none"):
                cancel_pending += 1

        return {
            "total":                len(contracts),
            "by_status":            by_status,
            "by_type":              by_type,
            "middleman":            middleman,
            "disputed":             disputed,
            "cancellation_pending": cancel_pending,
        }
