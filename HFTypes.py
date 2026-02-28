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

Optional fields are marked with NotRequired — they're only present when
you explicitly requested them in your asks dict (nested objects like
inituser, escrow, ibrating, etc.)
"""

from typing import TypedDict, NotRequired


# ── Me ─────────────────────────────────────────────────────────────────────────

class HFMe(TypedDict):
    """
    /read/me response. Requires 'Basic Info' scope.
    Advanced fields require 'Advanced Info' scope.
    """
    uid:              str
    username:         str
    usergroup:        str
    displaygroup:     str
    additionalgroups: str
    postnum:          str   # post count
    awards:           str
    bytes:            str   # bytes balance
    threadnum:        str   # thread count
    avatar:           str   # avatar URL
    avatardimensions: str
    avatartype:       str
    lastvisit:        str   # unix timestamp
    usertitle:        str
    website:          str
    timeonline:       str   # seconds
    reputation:       str   # popularity score
    referrals:        str
    vault:            NotRequired[str]  # API client vault balance
    # Advanced Info scope required:
    lastactive:       NotRequired[str]
    unreadpms:        NotRequired[str]
    invisible:        NotRequired[str]
    totalpms:         NotRequired[str]
    warningpoints:    NotRequired[str]


# ── Users ──────────────────────────────────────────────────────────────────────

class HFUser(TypedDict):
    """
    /read/users response. Requires 'Users' scope.
    Note: 'myps' is the bytes balance alias in the users endpoint.
    """
    uid:              str
    username:         str
    usergroup:        str
    displaygroup:     str
    additionalgroups: str
    postnum:          str   # alias: post count
    awards:           str
    myps:             str   # alias: bytes balance
    threadnum:        str   # alias: thread count
    avatar:           str
    avatardimensions: str
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
    # Optional nested objects (requested via author field):
    author:     NotRequired["HFUser"]


class HFPostWriteResult(TypedDict):
    """Response from /write/posts."""
    pid:     str
    tid:     str
    uid:     str
    message: str


# ── Threads ────────────────────────────────────────────────────────────────────

class HFThread(TypedDict):
    """
    /read/threads response. Requires 'Posts' scope.
    lastpost is a unix timestamp (not a post ID).
    firstpost IS a post ID (the OP's pid).
    """
    tid:           str
    uid:           str   # OP user ID
    fid:           str   # forum ID
    subject:       str
    closed:        str   # "1" if closed
    numreplies:    str
    views:         str
    dateline:      str   # unix timestamp of thread creation
    firstpost:     str   # post ID of the OP
    lastpost:      str   # unix timestamp of last reply
    lastposter:    str   # username of last poster
    lastposteruid: str
    prefix:        str
    icon:          str
    poll:          str   # "1" if has poll
    username:      str   # OP username
    sticky:        str   # "1" if sticky
    bestpid:       str   # best post ID (if voted)


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
    type: "f" = forum, "c" = category, "l" = link
    """
    fid:         str
    name:        str
    description: str
    type:        str   # "f", "c", or "l"


# ── Bytes ──────────────────────────────────────────────────────────────────────

class HFBytesTx(TypedDict):
    """
    /read/bytes response. Requires 'Bytes' scope.
    type: "send", "deposit", "withdraw", "bump", etc.
    """
    id:       str   # transaction ID
    amount:   str   # positive = received, negative = sent
    dateline: str   # unix timestamp
    type:     str   # transaction type
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

    Type field reflects the initiator's position:
        buying, selling, exchanging, trading, vouch_copy

    Status field values:
        active, complete, incomplete, cancelled

    istatus / ostatus: "pending" | "approved" | "denied"
    muid: non-empty = middleman/escrow contract
    """
    cid:           str
    dateline:      str   # contract start unix timestamp
    otherdateline: str   # contract end unix timestamp
    public:        str   # "1" if public
    timeout_days:  str
    timeout:       str   # unix timestamp of timeout
    status:        str   # overall status
    istatus:       str   # initiator status
    ostatus:       str   # other party status
    cancelstatus:  str   # cancellation request status
    type:          str   # contract type
    tid:           str   # linked thread ID
    inituid:       str   # initiator UID
    otheruid:      str   # other party UID
    muid:          str   # middleman UID (empty = no middleman)
    iprice:        str   # initiator's price
    oprice:        str   # other party's price
    iproduct:      str   # initiator's product description
    oproduct:      str   # other party's product description
    icurrency:     str   # initiator's currency (bytes, usd, btc, etc.)
    ocurrency:     str   # other party's currency
    terms:         str   # contract terms text
    iaddress:      str   # initiator's payment address
    oaddress:      str   # other party's payment address
    template_id:   NotRequired[str]
    # Optional nested objects:
    inituser:      NotRequired["HFUser"]
    otheruser:     NotRequired["HFUser"]
    escrow:        NotRequired["HFUser"]    # middleman user object
    thread:        NotRequired["HFContractThread"]
    idispute:      NotRequired["HFContractDispute"]
    odispute:      NotRequired["HFContractDispute"]
    ibrating:      NotRequired["HFContractBrating"]
    obrating:      NotRequired["HFContractBrating"]


# ── B-Ratings ──────────────────────────────────────────────────────────────────

class HFBrating(TypedDict):
    """
    /read/bratings response. Requires 'Contracts' scope.
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
    event:    str   # "thread_reply"
    tid:      int
    pid:      int | None
    uid:      str
    subject:  str
    snippet:  str   # first 200 chars, BBCode stripped
    dateline: int


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
    by_status:            dict[str, int]
    by_type:              dict[str, int]
    middleman:            int
    disputed:             int
    cancellation_pending: int
