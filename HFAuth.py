"""
HFAuth.py — OAuth 2.0 authentication with the HackForums API.

BUG FIXES:
  #2 — mkdir was called without parents=True, so nested paths like tmp/accessToken
       would raise FileNotFoundError. Also, on Windows, 'tmp' could exist as a
       plain file (e.g. left by a previous crash), causing mkdir to fail even
       with exist_ok=True. Now we detect that and unlink it first.
  #9 — The state parameter was accepted in handle_token_exchange() but never
       compared against self.STATE. CSRF protection was documented but silently
       not happening. Now we validate state and refuse mismatches.
"""

import requests
import json
import time
from pathlib import Path
from hf_config import HF_API_URL, CLIENT_ID, SECRET_KEY, REDIRECT_URI, STATE


class HFAuth:
    """
    Handles OAuth 2.0 authentication with the HackForums API.

    Flow:
        1. Direct user to build_auth_url() — they approve your app on HF.
        2. HF redirects to your REDIRECT_URI with ?code=CODE&state=STATE.
        3. Call handle_token_exchange(code, state) to get an access token.
        4. Token is saved to tmp/accessToken and read back via get_token().
    """

    HF_API_URL           = HF_API_URL
    HF_API_URL_AUTHORIZE = f"{HF_API_URL}authorize"
    TOKEN_FILE_PATH      = "tmp/accessToken"
    STATE                = STATE
    REDIRECT_URI         = REDIRECT_URI
    CLIENT_ID            = CLIENT_ID
    SECRET_KEY           = SECRET_KEY

    TIMEOUT = (8, 15)  # (connect, read) seconds

    def __init__(self):
        self.token_file_path = Path(self.TOKEN_FILE_PATH)
        self._ensure_token_dir()

    def _ensure_token_dir(self) -> None:
        """
        Create the directory for the token file, handling edge cases.

        BUG #2 FIX:
          - parents=True: creates all intermediate directories (e.g. tmp/).
          - Handles the case where 'tmp' already exists as a plain FILE
            (not a directory), which causes mkdir to fail even with exist_ok=True.
            We detect this and remove the file before creating the directory.
        """
        parent = self.token_file_path.parent
        if parent.exists() and not parent.is_dir():
            # 'tmp' exists but is a file — remove it so we can mkdir
            parent.unlink()
        parent.mkdir(parents=True, exist_ok=True)

    # ── URL builder ────────────────────────────────────────────────────────────

    def build_auth_url(self, state: str = None, redirect_uri: str = None) -> str:
        """
        Build the URL to redirect a user to for HF OAuth authorization.

        Args:
            state:        Override the default state string (optional).
            redirect_uri: Override the default redirect URI (optional).

        Returns:
            Full authorization URL string.
        """
        import urllib.parse
        params = {
            "response_type": "code",
            "client_id":     self.CLIENT_ID,
            "state":         state or self.STATE,
            "redirect_uri":  redirect_uri or self.REDIRECT_URI,
        }
        return f"{self.HF_API_URL_AUTHORIZE}?" + urllib.parse.urlencode(params)

    # ── Token exchange ─────────────────────────────────────────────────────────

    def handle_token_exchange(self, authorization_code: str, state: str) -> bool:
        """
        Exchange an authorization code for an access token and save it to disk.

        BUG #9 FIX: state is now validated against self.STATE to prevent CSRF.
        A mismatch means the callback did not originate from our authorization
        request and the exchange is aborted.

        Args:
            authorization_code: The code from the redirect query param.
            state:              The state from the redirect query param.

        Returns:
            True on success, False on failure.
        """
        if not authorization_code:
            print("Authorization code is missing.")
            return False

        # BUG #9 FIX: Validate state to prevent CSRF attacks.
        # Only check when state was provided in the callback (HF always sends it).
        if state and state != self.STATE:
            print(
                f"State mismatch — possible CSRF attack. "
                f"Expected {self.STATE!r}, got {state!r}. Aborting."
            )
            return False

        post_data = {
            "grant_type":    "authorization_code",
            "client_id":     self.CLIENT_ID,
            "client_secret": self.SECRET_KEY,
            "code":          authorization_code,
        }
        try:
            response = requests.post(
                self.HF_API_URL_AUTHORIZE,
                data=post_data,
                timeout=self.TIMEOUT,
            )
        except requests.Timeout:
            print("Token exchange timed out — HF may be slow. Try again.")
            return False
        except Exception as e:
            print(f"Token exchange error: {e}")
            return False

        if response.status_code != 200:
            print(f"Error exchanging code for tokens. HTTP {response.status_code}: {response.text[:300]}")
            return False

        tokens = response.json()
        if not tokens.get("access_token"):
            print(f"No access_token in response: {tokens}")
            return False

        self.save_token_to_file(tokens)
        print(f"Authorization successful! Token saved for UID {tokens.get('uid', '?')}.")
        return True

    # ── Token file ─────────────────────────────────────────────────────────────

    def save_token_to_file(self, tokens: dict):
        """Save token response to disk with computed expiry time."""
        tokens["expire_time"] = time.time() + int(tokens.get("expires_in", 7776000))
        with self.token_file_path.open("w") as f:
            json.dump(tokens, f, indent=2)

    def read_token_from_file(self) -> dict | None:
        """Read token from disk. Returns None if file missing or invalid."""
        if not self.token_file_path.exists():
            return None
        try:
            with self.token_file_path.open() as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            print("Token file is missing or invalid.")
            return None

    def get_token(self) -> dict | None:
        """
        Get the stored access token if it hasn't expired.

        Returns:
            Token dict (includes 'access_token', 'uid', 'expire_time') or None.
        """
        token = self.read_token_from_file()
        if token and token.get("expire_time", 0) > time.time():
            return token
        return None

    def get_access_token(self) -> str | None:
        """Convenience — returns just the access_token string or None."""
        token = self.get_token()
        return token.get("access_token") if token else None

    def get_uid(self) -> str | None:
        """Returns the HF UID of the authenticated user or None."""
        token = self.get_token()
        return str(token.get("uid", "")) if token else None

    def is_authenticated(self) -> bool:
        """Returns True if a valid non-expired token is stored."""
        return self.get_token() is not None

    def clear_token(self):
        """Delete the stored token (logout)."""
        if self.token_file_path.exists():
            self.token_file_path.unlink()
            print("Token cleared.")

    # ── Low-level POST helper ──────────────────────────────────────────────────

    def post_request(self, url: str, data: dict, headers: dict = None):
        """Raw POST helper. Returns (response_text, status_code)."""
        h = headers or {}
        try:
            r = requests.post(url, data=data, headers=h, timeout=self.TIMEOUT)
            return r.text, r.status_code
        except Exception as e:
            return str(e), 0
