"""
HFBatch — request multiple HF API resource types in a single /read call.

The HF API natively supports batching multiple resource types into one POST.
Without this class you'd make 3 separate calls to get me + user + threads.
With HFBatch you get them all in one round trip.

Usage:
    import asyncio
    from HFClient import HFClient
    from HFBatch  import HFBatch

    hf = HFClient("your_token")

    result = await (
        HFBatch(hf)
        .me()
        .user(761578)
        .user(1337)
        .threads(tids=[6083735, 6084000])
        .posts(pids=[59852445])
        .bytes_received(uid=761578, perpage=10)
        .fetch()
    )

    print(result.me["username"])
    print(result.users[0]["myps"])
    print(result.threads[0]["subject"])

Bug fix (Bug #5): bytes_sent and bytes_received previously both wrote to
self._asks["bytes"], so calling both in one batch silently discarded one.
A clear ValueError is now raised if you attempt to batch both directions
at once — use two separate fetches instead.
"""

from __future__ import annotations

import asyncio
from typing import Any


# ── Result wrapper ─────────────────────────────────────────────────────────────

class HFBatchResult:
    """
    Wrapper around the raw API response from a batch fetch.

    Provides both attribute access (result.me) and dict access (result["me"]).
    All list resources (users, posts, etc.) default to [] if not in the batch.
    The 'me' resource defaults to {} (single object, not a list).
    """

    def __init__(self, raw: dict):
        self._raw = raw or {}

        me_raw = self._raw.get("me")
        if isinstance(me_raw, list):
            self.me = me_raw[0] if me_raw else {}
        elif isinstance(me_raw, dict):
            self.me = me_raw
        else:
            self.me = {}

        self.users:     list[dict] = self._as_list("users")
        self.posts:     list[dict] = self._as_list("posts")
        self.threads:   list[dict] = self._as_list("threads")
        self.forums:    list[dict] = self._as_list("forums")
        self.bytes:     list[dict] = self._as_list("bytes")
        self.contracts: list[dict] = self._as_list("contracts")
        self.bratings:  list[dict] = self._as_list("bratings")
        self.disputes:  list[dict] = (
            self._as_list("disputes") or self._as_list("bratings_disputes")
        )

    def _as_list(self, key: str) -> list[dict]:
        val = self._raw.get(key)
        if val is None:
            return []
        if isinstance(val, list):
            return val
        if isinstance(val, dict):
            return [val]
        return []

    def has(self, resource: str) -> bool:
        return resource in self._raw and bool(self._raw[resource])

    def __getitem__(self, key: str) -> Any:
        return self._raw[key]

    def __contains__(self, key: str) -> bool:
        return key in self._raw

    def __repr__(self) -> str:
        keys = [k for k, v in self._raw.items() if v]
        return f"HFBatchResult(resources={keys})"


# ── Batch builder ──────────────────────────────────────────────────────────────

class HFBatch:
    """
    Builder for batching multiple HF API resource reads into a single POST.

    Chain calls to describe what you want, then call fetch() once.

    BUG #5 FIX: bytes_sent() and bytes_received() both previously wrote to
    self._asks["bytes"], so the second call silently overwrote the first.
    Calling both in the same batch now raises ValueError immediately.
    Use two separate batch fetches if you need both directions.
    """

    def __init__(self, client):
        self._client = client
        self._asks:  dict = {}
        # Track which bytes direction has been added to detect collision
        self._bytes_direction: str | None = None  # "sent" | "received"

    def _reset(self) -> None:
        self._asks = {}
        self._bytes_direction = None

    # ── Resource builders ──────────────────────────────────────────────────────

    def me(
        self,
        uid: bool = True,
        username: bool = True,
        usergroup: bool = True,
        bytes_: bool = True,
        reputation: bool = True,
        unreadpms: bool = True,
        vault: bool = True,
        advanced: bool = True,
        fields: dict | None = None,
    ) -> "HFBatch":
        if fields:
            self._asks["me"] = fields
        else:
            ask = {
                "uid": uid, "username": username, "usergroup": usergroup,
                "bytes": bytes_, "reputation": reputation, "vault": vault,
                "postnum": True, "threadnum": True, "avatar": True,
                "usertitle": True, "timeonline": True, "referrals": True,
                "lastvisit": True,
            }
            if advanced:
                ask.update({
                    "unreadpms": unreadpms, "lastactive": True,
                    "invisible": True, "totalpms": True, "warningpoints": True,
                })
            self._asks["me"] = ask
        return self

    def user(self, uid: int, fields: dict | None = None) -> "HFBatch":
        existing = self._asks.get("users", {})
        uids     = existing.get("_uid", [])
        uids.append(uid)
        self._asks["users"] = {
            "_uid": uids,
            **(fields or {
                "uid": True, "username": True, "usergroup": True,
                "displaygroup": True, "postnum": True, "awards": True,
                "myps": True, "threadnum": True, "avatar": True,
                "usertitle": True, "reputation": True, "referrals": True,
            }),
        }
        return self

    def users(self, uids: list[int], fields: dict | None = None) -> "HFBatch":
        existing = self._asks.get("users", {})
        all_uids = existing.get("_uid", []) + list(uids)
        self._asks["users"] = {
            "_uid": all_uids,
            **(fields or {
                "uid": True, "username": True, "usergroup": True,
                "displaygroup": True, "postnum": True, "awards": True,
                "myps": True, "threadnum": True, "avatar": True,
                "usertitle": True, "reputation": True, "referrals": True,
            }),
        }
        return self

    def posts(
        self,
        pids: list[int] | None = None,
        tid: int | None = None,
        uid: int | None = None,
        page: int = 1,
        perpage: int = 20,
        fields: dict | None = None,
    ) -> "HFBatch":
        ask: dict = fields or {
            "pid": True, "tid": True, "uid": True, "fid": True,
            "dateline": True, "message": True, "subject": True,
            "edituid": True, "edittime": True, "editreason": True,
        }
        if pids:
            ask["_pid"] = pids
        elif tid:
            ask["_tid"]     = [tid]
            ask["_page"]    = page
            ask["_perpage"] = perpage
        elif uid:
            ask["_uid"]     = [uid]
            ask["_page"]    = page
            ask["_perpage"] = perpage
        self._asks["posts"] = ask
        return self

    def threads(
        self,
        tids: list[int] | None = None,
        fid: int | None = None,
        uid: int | None = None,
        page: int = 1,
        perpage: int = 20,
        fields: dict | None = None,
    ) -> "HFBatch":
        ask: dict = fields or {
            "tid": True, "uid": True, "fid": True, "subject": True,
            "closed": True, "numreplies": True, "views": True,
            "dateline": True, "firstpost": True, "lastpost": True,
            "lastposter": True, "lastposteruid": True, "username": True,
            "sticky": True,
        }
        if tids:
            ask["_tid"] = tids
        elif fid:
            ask["_fid"] = [fid]
        elif uid:
            ask["_uid"]     = [uid]
            ask["_page"]    = page
            ask["_perpage"] = perpage
        self._asks["threads"] = ask
        return self

    def forums(self, fids: list[int], fields: dict | None = None) -> "HFBatch":
        self._asks["forums"] = {
            "_fid": fids,
            **(fields or {
                "fid": True, "name": True, "description": True, "type": True,
            }),
        }
        return self

    def bytes_received(
        self,
        uid: int,
        page: int = 1,
        perpage: int = 20,
        include_post: bool = False,
        fields: dict | None = None,
    ) -> "HFBatch":
        """
        Include bytes received by a user.

        Bug #5 fix: Raises ValueError if bytes_sent() was already called on
        this batch. The HF API only supports one "bytes" key per request —
        batching both directions is not possible in a single call.
        Use two separate HFBatch.fetch() calls instead.
        """
        if self._bytes_direction == "sent":
            raise ValueError(
                "Cannot batch both bytes_received() and bytes_sent() in one request — "
                "the HF API only supports one 'bytes' key per call. "
                "Use two separate batch.fetch() calls."
            )
        self._bytes_direction = "received"

        ask: dict = fields or {
            "id": True, "amount": True, "dateline": True,
            "type": True, "reason": True, "from": True, "to": True,
        }
        if include_post:
            ask["post"] = True
        ask["_to"]      = [uid]
        ask["_page"]    = page
        ask["_perpage"] = perpage
        self._asks["bytes"] = ask
        return self

    def bytes_sent(
        self,
        uid: int,
        page: int = 1,
        perpage: int = 20,
        fields: dict | None = None,
    ) -> "HFBatch":
        """
        Include bytes sent by a user.

        Bug #5 fix: Raises ValueError if bytes_received() was already called on
        this batch. Use two separate batch.fetch() calls to get both directions.
        """
        if self._bytes_direction == "received":
            raise ValueError(
                "Cannot batch both bytes_sent() and bytes_received() in one request — "
                "the HF API only supports one 'bytes' key per call. "
                "Use two separate batch.fetch() calls."
            )
        self._bytes_direction = "sent"

        ask: dict = fields or {
            "id": True, "amount": True, "dateline": True,
            "type": True, "reason": True, "from": True, "to": True,
        }
        ask["_from"]    = [uid]
        ask["_page"]    = page
        ask["_perpage"] = perpage
        self._asks["bytes"] = ask
        return self

    def contracts(
        self,
        uid: int | None = None,
        cids: list[int] | None = None,
        page: int = 1,
        perpage: int = 30,
        fields: dict | None = None,
    ) -> "HFBatch":
        ask: dict = fields or {
            "cid": True, "dateline": True, "otherdateline": True,
            "public": True, "status": True, "istatus": True, "ostatus": True,
            "cancelstatus": True, "type": True, "tid": True,
            "inituid": True, "otheruid": True, "muid": True,
            "iprice": True, "oprice": True, "iproduct": True, "oproduct": True,
            "icurrency": True, "ocurrency": True, "terms": True,
        }
        if uid:
            ask["_uid"]     = [uid]
            ask["_page"]    = page
            ask["_perpage"] = perpage
        elif cids:
            ask["_cid"] = cids
        self._asks["contracts"] = ask
        return self

    def bratings(
        self,
        uid: int | None = None,
        from_uid: int | None = None,
        to_uid: int | None = None,
        crids: list[int] | None = None,
        page: int = 1,
        perpage: int = 30,
        fields: dict | None = None,
    ) -> "HFBatch":
        ask: dict = fields or {
            "crid": True, "contractid": True, "fromid": True, "toid": True,
            "dateline": True, "amount": True, "message": True,
        }
        if crids:
            ask["_crid"] = crids
        elif to_uid:
            ask["_to"]      = [to_uid]
            ask["_page"]    = page
            ask["_perpage"] = perpage
        elif from_uid:
            ask["_from"]    = [from_uid]
            ask["_page"]    = page
            ask["_perpage"] = perpage
        elif uid:
            ask["_uid"]     = [uid]
            ask["_page"]    = page
            ask["_perpage"] = perpage
        self._asks["bratings"] = ask
        return self

    def disputes(
        self,
        cids: list[int] | None = None,
        cdids: list[int] | None = None,
        fields: dict | None = None,
    ) -> "HFBatch":
        ask: dict = fields or {
            "cdid": True, "contractid": True, "claimantuid": True,
            "defendantuid": True, "dateline": True, "status": True,
            "dispute_tid": True, "claimantnotes": True, "defendantnotes": True,
        }
        if cids:
            ask["_cid"] = cids
        elif cdids:
            ask["_cdid"] = cdids
        self._asks["disputes"] = ask
        return self

    # ── Fetch ──────────────────────────────────────────────────────────────────

    async def fetch(self) -> HFBatchResult:
        """
        Execute the batch request — fires a single /read POST with all accumulated asks.
        Resets the builder after fetching so it can be reused.
        """
        if not self._asks:
            return HFBatchResult({})

        asks = dict(self._asks)
        self._reset()

        raw = await self._client.read(asks)
        return HFBatchResult(raw or {})

    def fetch_sync(self) -> HFBatchResult:
        """Synchronous version of fetch() for non-async contexts."""
        return asyncio.run(self.fetch())

    async def __aenter__(self) -> "HFBatch":
        return self

    async def __aexit__(self, *_) -> None:
        self._reset()
