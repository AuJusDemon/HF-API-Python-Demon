"""
HFUsers — look up HackForums user profiles by UID.
Requires 'Users' scope.

BUG FIX #1: self.read() changed to self.read_sync().
"""

from HFClient import HFClient

_FIELDS = {
    "uid": True, "username": True, "usergroup": True,
    "displaygroup": True, "additionalgroups": True,
    "postnum": True, "awards": True, "myps": True,
    "threadnum": True, "avatar": True, "avatardimensions": True,
    "avatartype": True, "usertitle": True, "website": True,
    "timeonline": True, "reputation": True, "referrals": True,
}

_MAX_UIDS_PER_REQUEST = 20


class HFUsers(HFClient):
    """Look up user profiles by UID (/read/users endpoint)."""

    def get(self, uid: int) -> dict | None:
        """Get a user's profile by UID."""
        users = self.get_many([uid])
        return users[0] if users else None

    def get_many(self, uids: list[int]) -> list[dict]:
        """
        Get profiles for multiple users. Auto-chunks lists > 20 UIDs
        (the API silently returns partial results above that limit).
        """
        if not uids:
            return []
        if len(uids) <= _MAX_UIDS_PER_REQUEST:
            data = self.read_sync({"users": {"_uid": uids, **_FIELDS}})
            return self._unwrap(data, "users")
        results = []
        for i in range(0, len(uids), _MAX_UIDS_PER_REQUEST):
            chunk = uids[i : i + _MAX_UIDS_PER_REQUEST]
            data  = self.read_sync({"users": {"_uid": chunk, **_FIELDS}})
            results.extend(self._unwrap(data, "users"))
        return results

    def get_username(self, uid: int) -> str | None:
        user = self.get(uid)
        return user.get("username") if user else None

    def get_bytes(self, uid: int) -> float:
        user = self.get(uid)
        return float(user.get("myps", 0)) if user else 0.0

    def get_reputation(self, uid: int) -> int:
        user = self.get(uid)
        return int(float(user.get("reputation", 0))) if user else 0

    def get_usernames_map(self, uids: list[int]) -> dict[int, str]:
        """Get a UID → username mapping for a list of UIDs."""
        users = self.get_many(uids)
        return {int(u["uid"]): u["username"] for u in users if u.get("uid") and u.get("username")}
