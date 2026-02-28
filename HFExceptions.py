"""
HFExceptions — custom exceptions for the HackForums API wrapper.

Instead of silently returning None on failure, methods that raise
will give callers precise information about what went wrong.

Usage:
    from HFExceptions import HFAuthError, HFRateLimitError, HFPermissionError

    try:
        posts = HFPosts(token).get([pid])
    except HFAuthError:
        # Token expired — re-authenticate
        ...
    except HFRateLimitError as e:
        # Back off — e.retry_after tells you when to resume
        time.sleep(e.retry_after)
    except HFPermissionError:
        # Missing scope on your HF app
        ...
    except HFError:
        # Catch-all for any HF API error
        ...

All exceptions are subclasses of HFError so you can catch everything
with a single except clause if you prefer.

Raise mode vs silent mode:
    By default the wrapper returns None / [] on failure (silent mode),
    matching the original behaviour. To opt into exceptions, pass
    raise_errors=True to HFClient:

        hf = HFClient(token, raise_errors=True)
"""


class HFError(Exception):
    """
    Base class for all HackForums API errors.

    Attributes:
        message:     Human-readable description.
        status_code: HTTP status that triggered this error (0 if unknown).
        raw:         Raw response body bytes (may be empty).
    """

    def __init__(self, message: str, status_code: int = 0, raw: bytes = b""):
        super().__init__(message)
        self.message     = message
        self.status_code = status_code
        self.raw         = raw

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.message!r}, status={self.status_code})"


class HFAuthError(HFError):
    """
    Raised on HTTP 401 — token is missing, expired, or revoked.

    Fix: re-authenticate via HFAuth.build_auth_url() / hf auth start.

    Example:
        except HFAuthError:
            token = re_authenticate()
            hf    = HFClient(token)
    """


class HFRateLimitError(HFError):
    """
    Raised when the API returns MAX_HOURLY_CALLS_EXCEEDED.

    Attributes:
        retry_after: Seconds to wait before retrying (default 600 = 10 min).

    Example:
        except HFRateLimitError as e:
            await asyncio.sleep(e.retry_after)
    """

    def __init__(self, message: str = "HF hourly rate limit exceeded", retry_after: int = 600, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class HFPermissionError(HFError):
    """
    Raised on HTTP 403 or HTTP 503 caused by missing scope or Cloudflare block.

    Common causes:
    - Your HF app is missing the required scope (e.g. 'Contracts Permissions').
    - You're running from a VPS and Cloudflare is blocking datacenter IPs.
      Fix: pass proxy="http://user:pass@host:port" to HFClient.
    - The specific endpoint doesn't support the query you made (e.g. _uid on disputes).

    Example:
        except HFPermissionError as e:
            if "503" in str(e):
                # Try adding a proxy
                ...
    """


class HFNotFoundError(HFError):
    """
    Raised when the API returns an empty result set for a specific ID lookup.

    This is raised only when a caller explicitly requested one resource by ID
    and got nothing back. Paginated list calls return [] instead.

    Example:
        try:
            user = HFUsers(token, raise_errors=True).get(999999999)
        except HFNotFoundError:
            print("User does not exist")
    """


class HFServerError(HFError):
    """
    Raised on unexpected HTTP 5xx responses that aren't rate limits or permission errors.

    Attributes:
        status_code: The actual HTTP status (500, 502, 504, etc.)

    Example:
        except HFServerError as e:
            print(f"HF server error: HTTP {e.status_code}")
    """


class HFParseError(HFError):
    """
    Raised when the API returns a non-JSON or malformed response body.

    This usually means HF is returning an HTML error page or is down.

    Attributes:
        raw: The raw response bytes for debugging.

    Example:
        except HFParseError as e:
            print(f"Bad response: {e.raw[:200]}")
    """


class HFTimeoutError(HFError):
    """
    Raised when a request times out (asyncio.TimeoutError internally).

    Attributes:
        timeout: The timeout value in seconds that was exceeded.

    Example:
        except HFTimeoutError as e:
            print(f"Request timed out after {e.timeout}s")
    """

    def __init__(self, message: str = "HF API request timed out", timeout: float = 0, **kwargs):
        super().__init__(message, **kwargs)
        self.timeout = timeout


class HFProxyError(HFError):
    """
    Raised when the proxy connection fails.

    Fix: Check your proxy URL format and credentials.
    Format: http://user:pass@host:port

    Example:
        except HFProxyError:
            print("Proxy is down or misconfigured")
    """
