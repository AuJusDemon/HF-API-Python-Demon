"""
HFPaginator — automatic pagination for HF API endpoints that support paging.

BUG FIX #7: The _paginate() core loop had a broken partial-page detection:

    if len(items) < 1:
        break  # ← WRONG — this is identical to `if not items` above it,
               #   so this line was dead code that never fired.

A real partial-page signal is: the page returned fewer items than we asked for,
meaning there are no more pages. The fix passes perpage into _paginate() and
checks `len(items) < perpage` to detect the last page correctly. This prevents
the paginator from always making one unnecessary extra API call (the empty final
page that was previously needed to terminate the loop).
"""

import time
import logging

log = logging.getLogger("hfapi.paginator")

DEFAULT_PERPAGE   = 20
DEFAULT_MAX_PAGES = 50
PAGE_DELAY        = 0.3


class HFPaginator:
    """Auto-pagination utility for HF API endpoints. All methods are static."""

    @staticmethod
    def get_all_posts_by_user(
        posts_api,
        uid: int,
        perpage: int = DEFAULT_PERPAGE,
        max_pages: int = DEFAULT_MAX_PAGES,
        stop_at_pid: int = 0,
    ) -> list[dict]:
        """Get all posts by a user across all pages."""
        return HFPaginator._paginate(
            fetch_fn=lambda page: posts_api.get_by_user(uid, page=page, perpage=perpage),
            max_pages=max_pages,
            perpage=perpage,
            stop_condition=lambda item: stop_at_pid and str(item.get("pid")) == str(stop_at_pid),
        )

    @staticmethod
    def get_all_posts_by_thread(
        posts_api,
        tid: int,
        perpage: int = DEFAULT_PERPAGE,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> list[dict]:
        """Get all posts in a thread across all pages."""
        return HFPaginator._paginate(
            fetch_fn=lambda page: posts_api.get_by_thread(tid, page=page, perpage=perpage),
            max_pages=max_pages,
            perpage=perpage,
        )

    @staticmethod
    def get_all_threads_by_user(
        threads_api,
        uid: int,
        perpage: int = DEFAULT_PERPAGE,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> list[dict]:
        """Get all threads created by a user."""
        return HFPaginator._paginate(
            fetch_fn=lambda page: threads_api.get_by_user(uid, page=page, perpage=perpage),
            max_pages=max_pages,
            perpage=perpage,
        )

    @staticmethod
    def get_all_bytes_received(
        bytes_api,
        uid: int,
        perpage: int = DEFAULT_PERPAGE,
        max_pages: int = DEFAULT_MAX_PAGES,
        stop_at_id: int = 0,
    ) -> list[dict]:
        """Get all bytes transactions received by a user."""
        return HFPaginator._paginate(
            fetch_fn=lambda page: bytes_api.get_received(uid, page=page, perpage=perpage),
            max_pages=max_pages,
            perpage=perpage,
            stop_condition=lambda item: stop_at_id and str(item.get("id")) == str(stop_at_id),
        )

    @staticmethod
    def get_all_bytes_sent(
        bytes_api,
        uid: int,
        perpage: int = DEFAULT_PERPAGE,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> list[dict]:
        """Get all bytes transactions sent by a user."""
        return HFPaginator._paginate(
            fetch_fn=lambda page: bytes_api.get_sent(uid, page=page, perpage=perpage),
            max_pages=max_pages,
            perpage=perpage,
        )

    @staticmethod
    def get_all_contracts_by_user(
        contracts_api,
        uid: int,
        perpage: int = 30,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> list[dict]:
        """Get all contracts for a user."""
        return HFPaginator._paginate(
            fetch_fn=lambda page: contracts_api.get_by_user(uid, page=page, perpage=perpage),
            max_pages=max_pages,
            perpage=perpage,
        )

    @staticmethod
    def get_all_bratings_received(
        bratings_api,
        uid: int,
        perpage: int = 30,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> list[dict]:
        """Get all b-ratings received by a user."""
        return HFPaginator._paginate(
            fetch_fn=lambda page: bratings_api.get_received(uid, page=page, perpage=perpage),
            max_pages=max_pages,
            perpage=perpage,
        )

    @staticmethod
    def get_all_bratings_given(
        bratings_api,
        uid: int,
        perpage: int = 30,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> list[dict]:
        """Get all b-ratings given by a user."""
        return HFPaginator._paginate(
            fetch_fn=lambda page: bratings_api.get_given(uid, page=page, perpage=perpage),
            max_pages=max_pages,
            perpage=perpage,
        )

    # ── Core pagination engine ─────────────────────────────────────────────────

    @staticmethod
    def _paginate(
        fetch_fn,
        max_pages: int = DEFAULT_MAX_PAGES,
        perpage: int = DEFAULT_PERPAGE,
        stop_condition=None,
        delay: float = PAGE_DELAY,
    ) -> list[dict]:
        """
        Generic pagination loop.

        BUG #7 FIX: Added perpage parameter. The loop now correctly detects the
        last page by checking `len(items) < perpage` (a partial page means no
        more data). The old check `if len(items) < 1` was dead code — it was
        identical to the `if not items` guard above it and never fired, causing
        the paginator to always make one extra API call to confirm the empty page.

        Stops when:
          - Page returns 0 items (no more data)
          - Page returns fewer items than perpage (partial page = last page)
          - max_pages reached
          - stop_condition(item) returns True

        Args:
            fetch_fn:       Callable(page: int) -> list[dict]
            max_pages:      Maximum pages to fetch.
            perpage:        Expected items per full page (for partial-page detection).
            stop_condition: Optional callable(item) -> bool. Stops on True.
            delay:          Seconds to sleep between pages (default 0.3).

        Returns:
            Accumulated list of all collected items.
        """
        all_items = []
        for page in range(1, max_pages + 1):
            if page > 1 and delay > 0:
                time.sleep(delay)

            items = fetch_fn(page)
            if not items:
                log.debug(f"Paginator: empty page {page}, stopping")
                break

            stop = False
            for item in items:
                if stop_condition and stop_condition(item):
                    log.debug(f"Paginator: stop condition hit on page {page}")
                    stop = True
                    break
                all_items.append(item)

            if stop:
                break

            # BUG #7 FIX: Partial page means we've reached the last page.
            # No need to make another API call just to get an empty response.
            if len(items) < perpage:
                log.debug(f"Paginator: partial page {page} ({len(items)}<{perpage}), stopping")
                break

            log.debug(f"Paginator: page {page} → {len(items)} items (total {len(all_items)})")

        return all_items
