"""
HFMe — read info about the currently authenticated user.
Requires 'Basic Info' scope. Advanced fields require 'Advanced Info' scope.

BUG FIXES:
  #1 — self.read() changed to self.read_sync() in get().
  #8 — watch_pms() monkey-patched watcher.start() to only run the PM loop,
       silently killing any other watches registered on the same HFWatcher
       instance. Fixed: watch_pms() now returns a standalone HFWatcher that
       only has the PM poll task — it doesn't interfere with any other watcher.
       Users who want PMs + thread watching should use two separate watchers,
       or call watcher.watch_bytes() / watcher.watch_thread() directly and
       add a custom unreadpms poll on top.
"""

from HFClient import HFClient


class HFMe(HFClient):
    """Access info about the authenticated user (/read/me endpoint)."""

    def get(self, advanced: bool = True) -> dict | None:
        """
        Get the authenticated user's profile.

        Args:
            advanced: Include advanced fields (unreadpms, warningpoints, etc).
                      Requires 'Advanced Info' scope.

        Returns:
            Dict with user fields or None on failure.
        """
        ask = {
            "uid": True, "username": True, "usergroup": True,
            "displaygroup": True, "additionalgroups": True,
            "postnum": True, "awards": True, "bytes": True,
            "threadnum": True, "avatar": True, "avatardimensions": True,
            "avatartype": True, "lastvisit": True, "usertitle": True,
            "website": True, "timeonline": True, "reputation": True,
            "referrals": True, "vault": True,
        }
        if advanced:
            ask.update({
                "lastactive": True, "unreadpms": True,
                "invisible": True, "totalpms": True, "warningpoints": True,
            })
        data = self.read_sync({"me": ask})
        rows = self._unwrap(data, "me")
        return rows[0] if rows else None

    def get_unread_pms(self) -> int:
        """Returns number of unread PMs. Requires Advanced Info scope."""
        me = self.get(advanced=True)
        return int(me.get("unreadpms", 0)) if me else 0

    def get_bytes_balance(self) -> float:
        """Returns bytes balance."""
        me = self.get(advanced=False)
        return float(me.get("bytes", 0)) if me else 0.0

    def get_reputation(self) -> int:
        """Returns current reputation/popularity."""
        me = self.get(advanced=False)
        return int(float(me.get("reputation", 0))) if me else 0

    def watch_pms(
        self,
        callback,
        interval: int = 60,
    ):
        """
        Watch for new private messages by polling unreadpms.

        Fires the callback whenever the unread PM count increases.

        BUG #8 FIX: The original implementation monkey-patched watcher.start()
        to ONLY run the PM loop, silently killing any other registered watches
        on the same HFWatcher instance. E.g. if you did:
            watcher.watch_thread(...).watch_pms(...)
        only watch_pms would ever fire.

        Fix: watch_pms() now creates and returns a FRESH, isolated HFWatcher
        whose sole task is the PM poll loop. It does not touch any other watcher.
        If you want PM notifications alongside other watches, run them as
        separate asyncio tasks or use asyncio.gather():

            watcher  = HFWatcher(hf).watch_thread(tid=123, callback=on_reply)
            pm_watch = me_api.watch_pms(callback=on_pm)
            await asyncio.gather(watcher.start(), pm_watch.start())

        Args:
            callback: Async function called when PM count increases.
                      Signature: async def on_pm(event: dict)
            interval: Poll interval in seconds (default 60).

        Callback event dict:
            {
              "event":          "new_pms",
              "unread_count":   int,
              "new_since_last": int,
            }

        Returns:
            A standalone HFWatcher instance. Call .start() to begin polling.

        Requires 'Advanced Info' scope.
        """
        import asyncio as _asyncio
        from HFWatcher import HFWatcher

        me_client   = self
        _last_count: list[int] = [-1]  # mutable container for closure

        async def _poll_unread() -> None:
            current = me_client.get_unread_pms()
            last    = _last_count[0]
            if last == -1:
                _last_count[0] = current
                return
            if current > last:
                await callback({
                    "event":          "new_pms",
                    "unread_count":   current,
                    "new_since_last": current - last,
                })
            _last_count[0] = current

        # Build a standalone watcher with a single custom loop.
        # We subclass to inject the loop without touching HFWatcher internals.
        class _PMWatcher(HFWatcher):
            async def start(self) -> None:
                self._running = True
                async def _loop():
                    while self._running:
                        try:
                            await _poll_unread()
                        except Exception as e:
                            import logging
                            logging.getLogger("hfapi.me").warning(f"watch_pms error: {e}")
                            if self._on_error:
                                await self._on_error("pms", e)
                        await _asyncio.sleep(interval)
                await _asyncio.gather(_asyncio.create_task(_loop(), name="watch_pms"))

        return _PMWatcher(self)
