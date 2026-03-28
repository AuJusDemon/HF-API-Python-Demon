"""
HFUsers — look up HackForums user profiles by UID.
Requires 'Users' scope.


AVATAR URL NOTE:
    The avatar field returns a relative path, e.g.:
        "./uploads/avatars/avatar_761578.jpg?dateline=1772301324"
    To build a usable URL: strip the leading "./" and prepend the HF base URL.
    Use normalize_avatar_url() for this — it handles the None/empty case too.
"""

from HFClient import HFClient

_HF_BASE = "https://hackforums.net"

_FIELDS = {
    "uid": True, "username": True, "usergroup": True,
    "displaygroup": True, "additionalgroups": True,
    "postnum": True, "awards": True, "myps": True,
    "threadnum": True, "avatar": True, "avatardimensions": True,
    "avatartype": True, "usertitle": True, "website": True,
    "timeonline": True, "reputation": True, "referrals": True,
}

_MAX_UIDS_PER_REQUEST = 20


def normalize_avatar_url(avatar: str | None) -> str | None:
    """
    Convert a relative HF avatar path to an absolute URL.

    The API returns relative paths like "./uploads/avatars/avatar_761578.jpg".
    This function strips the "./" prefix and prepends the HF base URL.

    Args:
        avatar: Raw avatar value from the API response (may be None or empty).

    Returns:
        Full absolute URL string, or None if avatar is absent/empty.

    Example:
        normalize_avatar_url("./uploads/avatars/avatar_761578.jpg?dateline=123")
        # "https://hackforums.net/uploads/avatars/avatar_761578.jpg?dateline=123"

        normalize_avatar_url(None)   # None
        normalize_avatar_url("")     # None
    """
    if not avatar:
        return None
    if avatar.startswith("./"):
        avatar = avatar[2:]
    if avatar.startswith("http"):
        return avatar
    return f"{_HF_BASE}/{avatar}"


class HFUsers(HFClient):
    """
    Look up user profiles by UID (/read/users endpoint).

    Note on avatar:
        The 'avatar' field is a relative path like "./uploads/avatars/...".
        Use normalize_avatar_url(user["avatar"]) to get an absolute URL.

    Note on byte balance:
        The field is 'myps' here (not 'bytes' as in the /me endpoint).
        These are two different field names for the same data.
    """

    # Expose as a static method for convenience
    normalize_avatar_url = staticmethod(normalize_avatar_url)

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
        """Returns byte balance (field is 'myps' from the users endpoint)."""
        user = self.get(uid)
        return float(user.get("myps", 0)) if user else 0.0

    def get_reputation(self, uid: int) -> int:
        user = self.get(uid)
        return int(float(user.get("reputation", 0))) if user else 0

    def get_avatar_url(self, uid: int) -> str | None:
        """
        Get a user's avatar as an absolute URL.

        Convenience method that calls get() and normalizes the avatar path.

        Returns:
            Absolute avatar URL or None if no avatar is set or user not found.
        """
        user = self.get(uid)
        if not user:
            return None
        return normalize_avatar_url(user.get("avatar"))

    def get_usernames_map(self, uids: list[int]) -> dict[int, str]:
        """Get a UID → username mapping for a list of UIDs."""
        users = self.get_many(uids)
        return {int(u["uid"]): u["username"] for u in users if u.get("uid") and u.get("username")}
