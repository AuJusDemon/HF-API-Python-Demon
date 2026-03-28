"""
HFContracts — read contract data from HackForums.
Requires 'Contracts' scope.

Confirmed live status codes:
  "1" = Awaiting Approval
  "2" = Cancelled
  "5" = Active Deal
  "6" = Complete
  "7" = Disputed
  "8" = Expired

Confirmed live type codes:
  "1" = selling   "2" = buying   "3" = exchanging
  "4" = trading   "5" = vouchcopy

istatus / ostatus: "0" = not yet approved, "1" = approved
"""

from HFClient import HFClient

# ── Status constants (confirmed live) ─────────────────────────────────────────

CONTRACT_STATUS_AWAITING  = "1"   # Awaiting Approval
CONTRACT_STATUS_CANCELLED = "2"   # Cancelled
CONTRACT_STATUS_ACTIVE    = "5"   # Active Deal
CONTRACT_STATUS_COMPLETE  = "6"   # Complete
CONTRACT_STATUS_DISPUTED  = "7"   # Disputed
CONTRACT_STATUS_EXPIRED   = "8"   # Expired

CONTRACT_STATUS_LABELS = {
    "1": "Awaiting Approval",
    "2": "Cancelled",
    "3": "Unknown",
    "4": "Unknown",
    "5": "Active Deal",
    "6": "Complete",
    "7": "Disputed",
    "8": "Expired",
}

# Statuses that represent a closed/resolved contract
_CLOSED_STATUSES = {CONTRACT_STATUS_CANCELLED, CONTRACT_STATUS_COMPLETE,
                    CONTRACT_STATUS_DISPUTED,  CONTRACT_STATUS_EXPIRED}

# ── Type constants (confirmed live) ───────────────────────────────────────────

CONTRACT_TYPE_SELLING    = "1"
CONTRACT_TYPE_BUYING     = "2"
CONTRACT_TYPE_EXCHANGING = "3"
CONTRACT_TYPE_TRADING    = "4"
CONTRACT_TYPE_VOUCHCOPY  = "5"

CONTRACT_TYPE_LABELS = {
    "1": "Selling",
    "2": "Buying",
    "3": "Exchanging",
    "4": "Trading",
    "5": "Vouch Copy",
}

# Maps the _position strings used in write calls to their numeric type codes
_POSITION_TO_TYPE_CODE = {
    "selling":    CONTRACT_TYPE_SELLING,
    "buying":     CONTRACT_TYPE_BUYING,
    "exchanging": CONTRACT_TYPE_EXCHANGING,
    "trading":    CONTRACT_TYPE_TRADING,
    "vouchcopy":  CONTRACT_TYPE_VOUCHCOPY,
    "vouch_copy": CONTRACT_TYPE_VOUCHCOPY,
}

# ── Fields ────────────────────────────────────────────────────────────────────

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


def contract_value(c: dict) -> str:
    """
    Return a human-readable payment value string for a contract.

    Most contracts use currency="other" with the actual payment description
    stored in iproduct/oproduct (e.g. "12.99 Crypto or Credit Card").
    This function applies the correct fallback chain to extract a display value.

    Priority:
      1. Explicit numeric price + non-"other" currency  (e.g. "500 bytes")
      2. iproduct / oproduct description text
      3. Empty string if nothing useful is present

    Example:
        val = contract_value(contract)   # "12.99 Crypto or Credit Card"
        val = contract_value(contract)   # "500 bytes"
    """
    iprice   = c.get("iprice",   "0") or "0"
    icur     = c.get("icurrency", "other") or "other"
    oprice   = c.get("oprice",   "0") or "0"
    ocur     = c.get("ocurrency", "other") or "other"
    iproduct = c.get("iproduct", "") or ""
    oproduct = c.get("oproduct", "") or ""

    if iprice != "0" and icur.lower() != "other":
        return f"{iprice} {icur}"
    if oprice != "0" and ocur.lower() != "other":
        return f"{oprice} {ocur}"
    if iproduct.lower() not in ("", "other", "n/a"):
        return iproduct
    if oproduct.lower() not in ("", "other", "n/a"):
        return oproduct
    return ""


class HFContracts(HFClient):
    """
    Read contract data (/read/contracts endpoint).

    OWNER-SCOPED: The contracts endpoint only returns contracts for the
    authenticated token's own user. You cannot read another user's contracts
    with your token. If you need another user's data, they must OAuth and
    you must use their token.

    STATUS CODES — the API returns numeric strings, not text:
        "1" = Awaiting Approval
        "2" = Cancelled
        "5" = Active Deal
        "6" = Complete
        "7" = Disputed
        "8" = Expired

    TYPE CODES — the API returns numeric strings, not text:
        "1" = Selling   "2" = Buying   "3" = Exchanging
        "4" = Trading   "5" = Vouch Copy

    APPROVAL FLAGS — istatus / ostatus:
        "0" = not yet approved by this party
        "1" = approved by this party
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

    # ── Value helper ───────────────────────────────────────────────────────────

    @staticmethod
    def contract_value(c: dict) -> str:
        """
        Return a human-readable payment value string for a contract.

        Applies the correct fallback chain: explicit price → iproduct → oproduct.
        Most contracts use currency="other" so the product field is the real value.

        Example:
            val = HFContracts.contract_value(contract)
        """
        return contract_value(c)

    # ── Filter helpers (all OWNER-SCOPED) ─────────────────────────────────────
    # BUG FIX #14: All filters now compare against the API's actual numeric
    # status/type codes. The old code compared against text strings
    # ("complete", "buying", etc.) which never matched — every filter
    # silently returned wrong results.

    def get_active(self, uid: int, max_pages: int = 10) -> list[dict]:
        """
        Get open contracts (Awaiting Approval or Active Deal).

        Excludes: Cancelled("2"), Complete("6"), Disputed("7"), Expired("8").

        OWNER-SCOPED: uid must be your own UID.
        """
        return [
            c for c in self.get_all_mine(uid, max_pages=max_pages)
            if c.get("status") not in _CLOSED_STATUSES
        ]

    def get_pending(self, uid: int, max_pages: int = 10) -> list[dict]:
        """
        Get contracts awaiting approval from one or both parties.

        Filters on status == "1" (Awaiting Approval).
        Check istatus/ostatus ("0"=not approved, "1"=approved) to see
        which party still needs to act.

        OWNER-SCOPED: uid must be your own UID.
        """
        return [
            c for c in self.get_all_mine(uid, max_pages=max_pages)
            if c.get("status") == CONTRACT_STATUS_AWAITING
        ]

    def get_complete(self, uid: int, max_pages: int = 10) -> list[dict]:
        """
        Get completed contracts (status == "6").

        OWNER-SCOPED: uid must be your own UID.
        """
        return [
            c for c in self.get_all_mine(uid, max_pages=max_pages)
            if c.get("status") == CONTRACT_STATUS_COMPLETE
        ]

    def get_incomplete(self, uid: int, max_pages: int = 10) -> list[dict]:
        """
        Get expired contracts (status == "8").

        NOTE: HF's API uses "8" for contracts that timed out without completing.
        This is labelled "Expired" in HF's UI. The wrapper preserves the
        "incomplete" method name for backward compatibility.

        OWNER-SCOPED: uid must be your own UID.
        """
        return [
            c for c in self.get_all_mine(uid, max_pages=max_pages)
            if c.get("status") == CONTRACT_STATUS_EXPIRED
        ]

    # Explicit alias with the correct HF label
    get_expired = get_incomplete

    def get_cancelled(self, uid: int, max_pages: int = 10) -> list[dict]:
        """
        Get cancelled contracts (status == "2").

        OWNER-SCOPED: uid must be your own UID.
        """
        return [
            c for c in self.get_all_mine(uid, max_pages=max_pages)
            if c.get("status") == CONTRACT_STATUS_CANCELLED
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
            ctype: Position name OR numeric code.
                   Names: selling, buying, exchanging, trading, vouchcopy, vouch_copy
                   Codes: "1", "2", "3", "4", "5"

        """
        # Accept either the text position name or the raw numeric code
        target = _POSITION_TO_TYPE_CODE.get(ctype.lower().strip(), ctype.strip())
        return [
            c for c in self.get_all_mine(uid, max_pages=max_pages)
            if c.get("type") == target
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
              "by_status":            {"Awaiting Approval": N, "Complete": N, ...},
              "by_type":              {"Selling": N, "Buying": N, ...},
              "middleman":            int,
              "disputed":             int,
              "cancellation_pending": int,
            }

        Status and type keys use human-readable labels (e.g. "Active Deal"),
        not raw numeric codes.
        """
        contracts = self.get_all_mine(uid, max_pages=max_pages)
        by_status: dict[str, int] = {}
        by_type:   dict[str, int] = {}
        middleman = cancel_pending = 0

        for c in contracts:
            status_code = str(c.get("status", ""))
            type_code   = str(c.get("type",   ""))

            status_label = CONTRACT_STATUS_LABELS.get(status_code, f"unknown({status_code})")
            type_label   = CONTRACT_TYPE_LABELS.get(type_code,     f"unknown({type_code})")

            by_status[status_label] = by_status.get(status_label, 0) + 1
            by_type[type_label]     = by_type.get(type_label, 0) + 1

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
