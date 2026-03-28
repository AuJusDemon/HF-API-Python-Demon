"""
HFTypes — TypedDicts for HackForums API response shapes.

Provides IDE autocompletion and type checking for all API responses.
Every dict returned by the wrapper matches one of these types.

Usage:
    from HFTypes import HFPost, HFThread, HFUser, HFContract

    post: HFPost = posts_api.get([pid])[0]
    print(post["message"])   # IDE autocompletes 'message'

All fields are strings (HF API returns everything as strings, even numbers).
Use int(post["pid"]) or float(tx["amount"]) when you need numeric types.

BYTES AMOUNT WARNING:
    bytes.amount is a float string (e.g. "430.43"). Use int(float(x)), never
    int(x) directly. See parse_amount() in HFBytes.py.

Optional fields are marked with NotRequired — they're only present when
you explicitly requested them in your asks dict (nested objects like
inituser, escrow, ibrating, etc.)
"""

from typing import TypedDict, NotRequired


# ── Bytes transaction type codes (confirmed live, 290+ transactions) ───────────
#
# Use these constants when filtering tx["type"] instead of raw string literals.
# The 'don' code is the only one that appears on both sides — all real peer-to-peer
# byte transfers (including contract payments) use 'don'. To isolate contract
# payments specifically: type == BYTES_TYPE_TRANSFER and reason == "Contract".

BYTES_TYPE_TRANSFER       = "att"  # OUT: Manual bytes send to another user
BYTES_TYPE_BLACKJACK      = "bla"  # IN:  Blackjack winner
BYTES_TYPE_BONUS          = "bon"  # IN:  Bonus (event award, quick love bonus)
BYTES_TYPE_BUMP           = "bum"  # OUT: Thread bump fee (~50 bytes via Stanley)
BYTES_TYPE_COINFLIP_LOSS  = "cfl"  # OUT: Coin flips loser
BYTES_TYPE_COINFLIP_WIN   = "cfw"  # IN:  Coin flips winner
BYTES_TYPE_CRYPTO_BUY     = "cgp"  # OUT: Crypto game coin purchase
BYTES_TYPE_CRYPTO_SELL    = "cgs"  # IN:  Crypto game coin sell
BYTES_TYPE_CONVO_RAIN     = "cvr"  # IN:  Convo rain
BYTES_TYPE_PEER           = "don"  # IN/OUT: Peer-to-peer transfer; contract payments use this + reason="Contract"
BYTES_TYPE_GAME_CASH      = "gce"  # OUT: Bytes to game cash exchange
BYTES_TYPE_LOTTERY        = "ltb"  # OUT: Lottery ticket purchase
BYTES_TYPE_QUICKLOVE_CONV = "qlc"  # IN:  Quick love convo
BYTES_TYPE_QUICKLOVE_POST = "qlp"  # IN/OUT: Quick love post
BYTES_TYPE_SPORTSBOOK_WIN = "sbs"  # IN:  Sportsbook winner
BYTES_TYPE_SPORTSBOOK_BET = "sbw"  # OUT: Sportsbook wager
BYTES_TYPE_SPORTSBOOK_REF = "sbc"  # IN:  Sportsbook cancel/refund
BYTES_TYPE_SCRATCH        = "scp"  # OUT: Scratch card purchase
BYTES_TYPE_SLOTS          = "slo"  # IN:  Slots winner
BYTES_TYPE_UPGRADE_BONUS  = "ugb"  # IN:  Upgrade bonus

# Codes that indicate a gambling win (useful for bundling alerts)
BYTES_GAMBLING_WIN_TYPES = {
    BYTES_TYPE_SLOTS,
    BYTES_TYPE_BLACKJACK,
    BYTES_TYPE_SPORTSBOOK_WIN,
    BYTES_TYPE_CRYPTO_SELL,
    BYTES_TYPE_COINFLIP_WIN,
}

# ── Contract status codes (confirmed live) ─────────────────────────────────────
#
# The API always returns numeric strings — never text labels like "complete".
# Import these from HFContracts instead for full constants + label maps.

CONTRACT_STATUS_AWAITING  = "1"   # Awaiting Approval
CONTRACT_STATUS_CANCELLED = "2"   # Cancelled
CONTRACT_STATUS_ACTIVE    = "5"   # Active Deal
CONTRACT_STATUS_COMPLETE  = "6"   # Complete
CONTRACT_STATUS_DISPUTED  = "7"   # Disputed
CONTRACT_STATUS_EXPIRED   = "8"   # Expired

# ── Contract type codes (confirmed live) ───────────────────────────────────────

CONTRACT_TYPE_SELLING    = "1"
CONTRACT_TYPE_BUYING     = "2"
CONTRACT_TYPE_EXCHANGING = "3"
CONTRACT_TYPE_TRADING    = "4"
CONTRACT_TYPE_VOUCHCOPY  = "5"


# ── Me ─────────────────────────────────────────────────────────────────────────

class HFMe(TypedDict):
    """
    /read/me response. Requires 'Basic Info' scope.
    Advanced fields (unreadpms, invisible, totalpms, warningpoints, lastactive)
    require 'Advanced Info' scope.

    IMPORTANT — bytes vs myps:
        On the me endpoint, your byte balance is returned as the field "bytes".
        On the users endpoint, the same value is returned as "myps".
        These are two different field names for the same concept — do NOT
        use "myps" when reading from a me response, it will always be None.

        Correct:
            me_data = hf.read({"me": {"bytes": True}})
            balance = me_data["me"]["bytes"]   # ✅

        Wrong:
            balance = me_data["me"]["myps"]    # ❌ always None from me endpoint

    AVATAR NOTE:
        'avatar' is a relative path like "./uploads/avatars/avatar_761578.jpg".
        Use HFMe.normalize_avatar_url(avatar) or HFUsers.normalize_avatar_url(avatar)
        to get an absolute URL.
    """
    uid:              str
    username:         str
    usergroup:        str   # numeric group ID as string — "7"=exiled, "38"=banned
    displaygroup:     str
    additionalgroups: str
    postnum:          str   # total post count — useful for change-gating discovery calls
    awards:           str
    bytes:            str   # byte balance — NOTE: field is "bytes" here, NOT "myps"
    threadnum:        str   # total thread count — useful for change-gating own_tids sweep
    avatar:           str   # relative path — use normalize_avatar_url() for full URL
    avatardimensions: str   # pipe-separated "width|height" e.g. "120|120"
    avatartype:       str
    lastvisit:        str   # unix timestamp
    usertitle:        str
    website:          str
    timeonline:       str   # seconds online
    reputation:       str   # popularity score
    referrals:        str
    vault:            NotRequired[str]   # API client vault balance
    # Advanced Info scope required for fields below:
    lastactive:       NotRequired[str]   # unix timestamp of last activity
    unreadpms:        NotRequired[str]   # current unread PM count
    invisible:        NotRequired[str]   # "1" if browsing invisibly
    totalpms:         NotRequired[str]   # lifetime PM count
    warningpoints:    NotRequired[str]   # active warning points from moderators


# ── Users ──────────────────────────────────────────────────────────────────────

class HFUser(TypedDict):
    """
    /read/users response. Requires 'Users' scope.
    Note: byte balance is "myps" here (alias) — different from "bytes" in HFMe.

    AVATAR NOTE:
        'avatar' is a relative path like "./uploads/avatars/avatar_761578.jpg".
        Use HFUsers.normalize_avatar_url(avatar) to get an absolute URL.
    """
    uid:              str
    username:         str
    usergroup:        str
    displaygroup:     str
    additionalgroups: str
    postnum:          str   # alias: post count
    awards:           str
    myps:             str   # alias: bytes balance — NOTE: "myps" here, not "bytes"
    threadnum:        str   # alias: thread count
    avatar:           str   # relative path — use normalize_avatar_url() for full URL
    avatardimensions: str   # pipe-separated "width|height" e.g. "120|120"
    avatartype:       str
    usertitle:        str
    website:          str
    timeonline:       str
    reputation:       str   # alias: popularity
    referrals:        str


# ── Posts ──────────────────────────────────────────────────────────────────────

class HFPost(TypedDict):
    """
    /read/posts response. Requires 'Posts' scope.
    message field contains raw BBCode — use HFBBCode.to_text() to strip.

    username is a free inline field — request it via "username": True in your
    asks dict and it comes back at zero extra cost, eliminating a follow-up
    users _uid call just to get the poster's display name.
    """
    pid:        str
    tid:        str
    uid:        str
    fid:        str
    dateline:   str   # unix timestamp
    message:    str   # raw BBCode content
    subject:    str   # post subject / thread title
    edituid:    str   # UID of last editor (empty if never edited)
    edittime:   str   # unix timestamp of last edit
    editreason: str   # reason for last edit
    # Optional fields — present when explicitly requested:
    username:   NotRequired[str]   # poster's username — free inline field, no extra API cost
    author:     NotRequired["HFUser"]


class HFPostWriteResult(TypedDict):
    """Response from /write/posts."""
    pid:     str
    tid:     str
    uid:     str
    message: str


# ── Threads ────────────────────────────────────────────────────────────────────

class HFFirstPost(TypedDict):
    """
    Inline OP post object returned when firstpost:True is requested in a threads ask.
    This is NOT a post ID — it is a small dict containing the OP's pid and raw BBCode message.

    DEFENSIVE HANDLING REQUIRED:
        The API occasionally returns firstpost as a single-element list instead of a plain
        dict. Always unwrap defensively before accessing fields:

            fp = thread.get("firstpost") or {}
            if isinstance(fp, list):
                fp = fp[0] if fp else {}
            pid     = fp.get("pid", "")
            snippet = HFBBCode.to_text(fp.get("message", ""))
    """
    pid:     str
    message: str   # raw BBCode — use HFBBCode.to_text() to strip


class HFThread(TypedDict):
    """
    /read/threads response. Requires 'Posts' scope.

    lastpost   — unix timestamp of the most recent reply (NOT a post ID).
    firstpost  — when requested via firstpost:True, returns an HFFirstPost dict
                 {pid, message} containing the OP's post ID and raw BBCode content.
                 It is NOT just a post ID string. Omitted entirely if not requested.
                 NOTE: can come back as a single-element list — always unwrap defensively.

    numreplies NOTE:
        numreplies from threads._uid is known to be unreliable — the value can
        lag or be stale. Do not use it for critical logic such as deciding
        whether a new post has arrived. HFWatcher uses it as a change-gate
        but may occasionally miss a reply as a result.
    """
    tid:           str
    uid:           str   # OP user ID
    fid:           str   # forum ID
    subject:       str
    closed:        str   # "1" if closed
    numreplies:    str   # WARNING: may be stale when fetched via threads._uid
    views:         str
    dateline:      str   # unix timestamp of thread creation
    lastpost:      str   # unix timestamp of last reply — NOT a post ID
    lastposter:    str   # username of last poster (free field — no extra cost)
    lastposteruid: str
    prefix:        str
    icon:          str
    poll:          str   # "1" if has poll
    username:      str   # OP username
    sticky:        str   # "1" if sticky
    bestpid:       str   # best post ID (if voted, "0" if none)
    firstpost:     NotRequired["HFFirstPost"]


class HFThreadWriteResult(TypedDict):
    """Response from /write/threads."""
    tid:       str
    uid:       str
    subject:   str
    dateline:  str
    firstpost: "HFPostWriteResult"


# ── Forums ─────────────────────────────────────────────────────────────────────

class HFForum(TypedDict):
    """
    /read/forums response. Requires 'Posts' scope.
    type: "f" = forum (has threads), "c" = category (container only, no threads)
    Never use type="c" forums as _fid inputs — they will always return empty.
    """
    fid:         str
    name:        str
    description: str
    type:        str   # "f" = forum, "c" = category


# ── Bytes ──────────────────────────────────────────────────────────────────────

class HFBytesTx(TypedDict):
    """
    /read/bytes response. Requires 'Bytes' scope.

    type: one of the BYTES_TYPE_* constants defined in this module.
    The 'don' type (BYTES_TYPE_PEER) is used for all real peer-to-peer transfers.
    To isolate contract payments: type == "don" and reason == "Contract".

    AMOUNT CAST WARNING:
        amount is a float string (e.g. "430.43"). Always cast via
        int(float(tx["amount"])) — never int(tx["amount"]) directly.
        int("430.43") raises ValueError. Use HFBytes.parse_amount() for safety.
    """
    id:       str   # transaction ID
    amount:   str   # float string e.g. "430.43" — use int(float(x)) to cast
    dateline: str   # unix timestamp
    type:     str   # transaction type code — see BYTES_TYPE_* constants above
    reason:   str   # optional reason
    # Optional nested objects:
    from_:    NotRequired["HFUser"]   # sender (key is "from" in API)
    to:       NotRequired["HFUser"]   # recipient
    post:     NotRequired["HFPost"]   # linked post (if donation was linked to a post)


class HFBytesWriteResult(TypedDict):
    """Response from /write/bytes (send)."""
    id: str   # transaction ID


# ── Contracts ──────────────────────────────────────────────────────────────────

class HFContractDispute(TypedDict):
    """Inline dispute nested in a contract response."""
    cdid:          str
    status:        str
    claimantuid:   str
    defendantuid:  str
    claimantnotes: NotRequired[str]


class HFContractBrating(TypedDict):
    """Inline b-rating nested in a contract response."""
    crid:      str
    amount:    str   # "+1" or "-1"
    message:   str
    fromid:    str
    dateline:  NotRequired[str]


class HFContractThread(TypedDict):
    """Inline thread nested in a contract response."""
    tid:     str
    subject: str


class HFContract(TypedDict):
    """
    /read/contracts response. Requires 'Contracts' scope.

    OWNER-SCOPED: contracts _uid only returns contracts for the authenticated
    token's own user. You cannot read another user's contracts with your token.

    STATUS — numeric strings (not text labels):
        "1" = Awaiting Approval   "2" = Cancelled
        "5" = Active Deal         "6" = Complete
        "7" = Disputed            "8" = Expired
        Use CONTRACT_STATUS_* constants or HFContracts.CONTRACT_STATUS_* for comparisons.

    TYPE — numeric strings (not text labels):
        "1" = Selling   "2" = Buying   "3" = Exchanging
        "4" = Trading   "5" = Vouch Copy
        Use CONTRACT_TYPE_* constants or HFContracts.CONTRACT_TYPE_* for comparisons.

    APPROVAL FLAGS:
        istatus / ostatus: "0" = not yet approved, "1" = approved
        These are per-party flags, independent of overall status.

    muid: non-empty string = middleman/escrow contract
    """
    cid:           str
    dateline:      str   # contract start unix timestamp
    otherdateline: str   # contract end unix timestamp
    public:        str   # "1" if public
    timeout_days:  str
    timeout:       str   # unix timestamp of timeout
    status:        str   # numeric status code — see CONTRACT_STATUS_* constants
    istatus:       str   # initiator approval: "0"=pending, "1"=approved
    ostatus:       str   # other party approval: "0"=pending, "1"=approved
    cancelstatus:  str   # cancellation request status
    type:          str   # numeric type code — see CONTRACT_TYPE_* constants
    tid:           str   # linked thread ID
    inituid:       str   # initiator UID
    otheruid:      str   # other party UID
    muid:          str   # middleman UID (empty string = no middleman)
    iprice:        str   # initiator's price
    oprice:        str   # other party's price
    iproduct:      str   # initiator's product description
    oproduct:      str   # other party's product description
    icurrency:     str   # initiator's currency (bytes, usd, btc, other, etc.)
    ocurrency:     str   # other party's currency
    terms:         str   # contract terms text
    iaddress:      str   # initiator's payment address
    oaddress:      str   # other party's payment address
    template_id:   NotRequired[str]
    # Optional nested objects:
    inituser:      NotRequired["HFUser"]
    otheruser:     NotRequired["HFUser"]
    escrow:        NotRequired["HFUser"]          # middleman user object
    thread:        NotRequired["HFContractThread"]
    idispute:      NotRequired["HFContractDispute"]
    odispute:      NotRequired["HFContractDispute"]
    ibrating:      NotRequired["HFContractBrating"]
    obrating:      NotRequired["HFContractBrating"]


# ── B-Ratings ──────────────────────────────────────────────────────────────────

class HFBrating(TypedDict):
    """
    /read/bratings response. Requires 'Contracts' scope.
    OWNER-SCOPED: _uid only returns ratings for the authenticated token's user.
    amount: "+1" or "-1"
    """
    crid:       str   # b-rating ID
    contractid: str
    fromid:     str   # rater's UID
    toid:       str   # rated user's UID
    dateline:   str   # unix timestamp
    amount:     str   # "+1" or "-1"
    message:    str   # optional review text
    # Optional nested objects:
    contract:   NotRequired["HFContract"]
    from_:      NotRequired["HFUser"]
    to:         NotRequired["HFUser"]


# ── Disputes ───────────────────────────────────────────────────────────────────

class HFDispute(TypedDict):
    """
    /read/disputes response. Requires 'Contracts' scope.

    IMPORTANT: Query by _cid or _cdid only — _uid returns 503.
    Disputes can be opened on ANY contract status including complete and
    cancelled — do not filter by contract status before querying disputes.
    dispute_tid is the thread where the dispute is being handled.
    """
    cdid:           str   # dispute ID
    contractid:     str
    claimantuid:    str   # who opened the dispute
    defendantuid:   str   # who is being disputed against
    dateline:       str   # unix timestamp
    status:         str   # dispute status
    dispute_tid:    str   # thread ID for the dispute discussion
    claimantnotes:  str
    defendantnotes: str
    # Optional nested objects:
    contract:       NotRequired["HFContract"]
    claimant:       NotRequired["HFUser"]
    defendant:      NotRequired["HFUser"]
    dispute_thread: NotRequired["HFThread"]


# ── Sigmarket ──────────────────────────────────────────────────────────────────

class HFSigmarketListing(TypedDict):
    """
    /read/sigmarket (type=market) response.
    ppd = price per day.
    """
    uid:       str   # seller UID
    price:     str   # total price
    duration:  str   # duration in days
    active:    str   # "1" if active
    sig:       str   # the signature BBCode content
    dateadded: str   # unix timestamp
    ppd:       str   # price per day
    user:      NotRequired["HFUser"]


class HFSigmarketOrder(TypedDict):
    """
    /read/sigmarket (type=order) response.
    smid = signature market order ID.
    """
    smid:      str   # order ID
    startdate: str   # unix timestamp
    enddate:   str   # unix timestamp
    price:     str
    duration:  str   # days
    active:    str   # "1" if active
    buyer:     NotRequired["HFUser"]
    seller:    NotRequired["HFUser"]


# ── Watcher events ─────────────────────────────────────────────────────────────

class HFEventThreadReply(TypedDict):
    """Fired by HFWatcher.watch_thread() on new reply."""
    event:    str        # "thread_reply"
    tid:      int
    pid:      int | None
    uid:      str
    username: str        # inline from posts fetch — no extra API call
    subject:  str
    snippet:  str        # first 200 chars, BBCode stripped
    dateline: int


class HFEventThreadBestAnswer(TypedDict):
    """
    Fired by HFWatcher.watch_thread() when a post is marked as the best answer.
    Zero extra API cost — bestpid is fetched as part of the standard thread poll.
    """
    event:   str   # "thread_best_answer"
    tid:     int
    pid:     str   # post ID marked as best
    subject: str


class HFEventThreadViewSpike(TypedDict):
    """
    Fired by HFWatcher.watch_thread() when views jump by 500+ in one poll cycle.
    Indicates a thread going viral or unusual attention (e.g. mod review).
    Zero extra API cost — views is fetched as part of the standard thread poll.
    Threshold configurable via _VIEW_SPIKE_THRESHOLD in HFWatcher.
    """
    event:   str   # "thread_view_spike"
    tid:     int
    subject: str
    spike:   int   # new views since last poll
    views:   int   # current total


class HFEventThreadClosed(TypedDict):
    """
    Fired by HFWatcher.watch_thread() when a thread transitions from open to closed.
    Zero extra API cost — closed is fetched as part of the standard thread poll.
    """
    event:   str   # "thread_closed"
    tid:     int
    subject: str


class HFEventNewThread(TypedDict):
    """Fired by HFWatcher.watch_forum() on new thread."""
    event:    str   # "new_thread"
    fid:      int
    tid:      int
    uid:      str
    subject:  str
    dateline: int


class HFEventUserThread(TypedDict):
    """Fired by HFWatcher.watch_user() on new thread (any mode)."""
    event:    str   # "user_thread"
    uid:      int
    tid:      int
    subject:  str
    dateline: int


class HFEventUserPost(TypedDict):
    """Fired by HFWatcher.watch_user(mode='all') on new post."""
    event:    str   # "user_post"
    uid:      int
    tid:      int
    pid:      int
    subject:  str
    snippet:  str
    dateline: int


class HFEventKeywordMatch(TypedDict):
    """Fired by HFWatcher.watch_keyword() on match."""
    event:    str   # "keyword_match"
    keyword:  str
    fid:      int
    tid:      int
    pid:      int | None
    subject:  str
    snippet:  str
    dateline: int


class HFEventBytesReceived(TypedDict):
    """Fired by HFWatcher.watch_bytes() on new bytes."""
    event:     str   # "bytes_received"
    id:        str
    amount:    float
    reason:    str
    from_user: str
    dateline:  int


# ── Batch result ───────────────────────────────────────────────────────────────

class HFBatchResult(TypedDict, total=False):
    """
    Result from HFBatch.fetch(). Keys present depend on what was requested.
    All values are lists except 'me' which is a single dict.
    """
    me:        HFMe
    users:     list[HFUser]
    posts:     list[HFPost]
    threads:   list[HFThread]
    forums:    list[HFForum]
    bytes:     list[HFBytesTx]
    contracts: list[HFContract]
    bratings:  list[HFBrating]
    disputes:  list[HFDispute]


# ── Contract summary ───────────────────────────────────────────────────────────

class HFContractSummary(TypedDict):
    """Return type from HFContracts.get_summary()."""
    total:                int
    by_status:            dict[str, int]   # keys are human-readable labels e.g. "Active Deal"
    by_type:              dict[str, int]   # keys are human-readable labels e.g. "Selling"
    middleman:            int
    disputed:             int
    cancellation_pending: int
