# HF API Python

Full Python library for the HackForums API v2. Covers every endpoint — auth, posts, threads, forums, users, bytes, contracts, b-ratings, disputes, and sigmarket. Includes auto-pagination, a BBCode parser, a web UI, an installable CLI, an async HTTP client, a polling watcher, and Discord/webhook support.

---

## Setup

### 1. Edit `hf_config.py`
```python
CLIENT_ID    = "hf_clientid_your_id_here"
SECRET_KEY   = "hf_secret_your_secret_here"
REDIRECT_URI = "http://YOUR_SERVER_IP:8001/callback"
```

- Get your Client ID and Secret from the [HF Developer Panel](https://hackforums.net/devapi.php)
- Add your server IP to the whitelist in your HF app settings
- `REDIRECT_URI` must match what you set in your HF app

### 2. Install
```
pip install -e .
```

This installs all dependencies (`httpx`, `flask`, `click`) and registers the `hf` command globally so you can run it from anywhere.

### 3. Run the server
```
python server.py
```

The server handles the OAuth callback. It must be running when you authenticate.

### 4. Authenticate
```
hf auth start
```

This opens HackForums in your browser. Approve the app, get redirected back to your server, and the token is saved automatically to `tmp/accessToken`.

Verify it worked:
```
hf auth status
```

---

## File Overview

| File | Description |
|------|-------------|
| `hf_config.py` | Your Client ID, Secret, redirect URI |
| `setup.py` | Install config — registers the `hf` CLI command |
| `HFClient.py` | Async HTTP client built on httpx — shared connection pool, rate limit tracking, proxy support |
| `HFAuth.py` | OAuth flow, token storage |
| `HFMe.py` | Current user profile |
| `HFUsers.py` | Look up any user by UID |
| `HFPosts.py` | Read posts, reply to threads |
| `HFThreads.py` | Read threads, create threads |
| `HFForums.py` | Forum info |
| `HFBytes.py` | Send, deposit, withdraw, bump, and read bytes |
| `HFContracts.py` | Read contracts |
| `HFBratings.py` | Read b-ratings |
| `HFDisputes.py` | Read disputes |
| `HFSigmarket.py` | Sigmarket listings and orders |
| `HFPaginator.py` | Auto-pagination for all paged endpoints |
| `HFBBCode.py` | BBCode parser — strip, convert, extract |
| `HFWatcher.py` | Polling watcher — fire async callbacks on new threads, replies, bytes, keywords |
| `HFWebhook.py` | Send watcher events to Discord or any HTTP endpoint |
| `HFBatch.py` | **NEW** — Batch multiple resource types into a single `/read` API call |
| `HFEventStore.py` | **NEW** — SQLite-backed persistent event deduplication (watcher events survive restarts) |
| `HFCache.py` | **NEW** — TTL cache + `CachedHFUsers`, `CachedHFForums`, `CachedHFMe` drop-in wrappers |
| `HFExceptions.py` | **NEW** — Custom exception hierarchy: `HFAuthError`, `HFRateLimitError`, `HFPermissionError`, etc. |
| `HFTypes.py` | **NEW** — TypedDicts for all API response shapes (IDE autocomplete) |
| `HFBBCodeBuilder.py` | **NEW** — Programmatic BBCode generation via fluent builder API |
| `server.py` | Flask server — OAuth callback + web UI |
| `cli.py` | Click-based CLI — now includes `batch fetch` and `build` BBCode commands |

---

## Async Client

`HFClient` uses `httpx.AsyncClient` instead of `requests`. All API methods are coroutines.

- Shared connection pool across all instances — no new socket per call
- `asyncio.wait_for` cancellation — hung requests don't leak threads
- Per-token rate limit tracking — auto-backoff when `MAX_HOURLY_CALLS` is hit
- Optional proxy support — required when running from a VPS (Cloudflare blocks datacenter IPs)

```python
import asyncio
from HFClient import HFClient

async def main():
    hf   = HFClient("your_token")
    data = await hf.read({"me": {"uid": True, "username": True}})
    print(data["me"]["username"])

    # Check rate limit state at any time
    print(hf.rate_limit_remaining)   # calls left this hour
    print(hf.is_rate_limited)        # True if in backoff window

asyncio.run(main())
```

```python
# With proxy (required on VPS — Cloudflare blocks datacenter IPs)
hf = HFClient("your_token", proxy="http://user:pass@host:port")
```

```python
# Exchange OAuth code for token
from HFClient import exchange_code_for_token

token, expires, uid = await exchange_code_for_token(
    code, client_id, client_secret
)
```

---

## Watcher

`HFWatcher` polls the API on a timer and fires async callbacks when something new happens. Each watch type runs as its own asyncio task — a slow poll on one type doesn't delay the others.

On the first poll, existing state is seeded silently so you don't get spammed with old events on startup.

```python
import asyncio
from HFClient  import HFClient
from HFWatcher import HFWatcher

hf      = HFClient("your_token")
watcher = HFWatcher(hf)

async def on_reply(event):
    print(f"New reply in {event['subject']} — {event['snippet']}")

async def on_thread(event):
    print(f"New thread: {event['subject']} (tid={event['tid']})")

async def on_bytes(event):
    print(f"{event['amount']} bytes from {event['from_user']}: {event['reason']}")

watcher.watch_thread(tid=6083735, callback=on_reply, interval=60)
watcher.watch_forum(fid=25, callback=on_thread, interval=120)
watcher.watch_bytes(callback=on_bytes, interval=60)

asyncio.run(watcher.start())
```

### Watch types

#### `watch_thread(tid, callback, interval=60)`
Fires when a new reply is posted in a thread.

```python
# Event dict:
{
  "event":    "thread_reply",
  "tid":      int,
  "pid":      int,
  "uid":      str,
  "subject":  str,
  "snippet":  str,   # first 200 chars, BBCode stripped
  "dateline": int,
}
```

#### `watch_forum(fid, callback, interval=120)`
Fires when a new thread is created in a forum.

```python
# Event dict:
{
  "event":    "new_thread",
  "fid":      int,
  "tid":      int,
  "uid":      str,
  "subject":  str,
  "dateline": int,
}
```

#### `watch_user(uid, callback, interval=120, mode="threads")`
Fires when a user creates a new thread. Set `mode="all"` to also fire on every new post.

```python
# New thread event:
{
  "event":    "user_thread",
  "uid":      int,
  "tid":      int,
  "subject":  str,
  "dateline": int,
}

# New post event (mode="all" only):
{
  "event":    "user_post",
  "uid":      int,
  "tid":      int,
  "pid":      int,
  "subject":  str,
  "snippet":  str,
  "dateline": int,
}
```

#### `watch_keyword(keyword, callback, interval=120, fids=[], case_sensitive=False)`
Fires when a post or thread subject matches a keyword or regex. Requires at least one `fid` to limit the search scope.

```python
watcher.watch_keyword("selling vpn", callback=on_match, fids=[25, 100])
watcher.watch_keyword(r"WTS.*lifetime", callback=on_match, fids=[25])  # regex works too

# Event dict:
{
  "event":    "keyword_match",
  "keyword":  str,
  "fid":      int,
  "tid":      int,
  "pid":      int | None,
  "subject":  str,
  "snippet":  str,
  "dateline": int,
}
```

#### `watch_bytes(callback, interval=60)`
Fires when the authenticated user receives bytes.

```python
# Event dict:
{
  "event":     "bytes_received",
  "id":        str,
  "amount":    float,
  "reason":    str,
  "from_user": str,
  "dateline":  int,
}
```

### Chaining

All `watch_*` methods return the watcher instance so you can chain:

```python
watcher = (
    HFWatcher(hf)
    .watch_thread(tid=6083735, callback=on_reply)
    .watch_forum(fid=25, callback=on_thread)
    .watch_bytes(callback=on_bytes)
)
asyncio.run(watcher.start())
```

### Error handling

Pass `on_error` to handle poll failures without crashing the whole watcher:

```python
async def on_error(watch_type: str, exc: Exception):
    print(f"Watcher error in {watch_type}: {exc}")

watcher = HFWatcher(hf, on_error=on_error)
```

---

## Webhooks

`HFWebhook` bridges watcher callbacks to outbound HTTP — Discord or any generic JSON endpoint.

### Discord

Posts rich embeds with colors per event type.

```python
from HFWebhook import HFWebhook

webhook = HFWebhook.discord("https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN")

watcher.watch_thread(tid=6083735, callback=webhook.callback)
watcher.watch_forum(fid=25, callback=webhook.callback)
watcher.watch_bytes(callback=webhook.callback)
```

Custom bot username in Discord:
```python
webhook = HFWebhook.discord("https://discord.com/api/webhooks/...", username="HF Bot")
```

### Generic JSON

POSTs the raw event dict as JSON to any URL. Works with custom servers, n8n, Make, Zapier, etc.

```python
webhook = HFWebhook.generic("https://myserver.com/hf-events")

# With auth headers:
webhook = HFWebhook.generic(
    "https://myserver.com/hf-events",
    headers={"Authorization": "Bearer my-secret"}
)
```

### Multiple targets

Send the same event to more than one destination:

```python
discord = HFWebhook.discord("https://discord.com/api/webhooks/...")
server  = HFWebhook.generic("https://myserver.com/hf-events")

async def multi(event):
    await discord.callback(event)
    await server.callback(event)

watcher.watch_forum(fid=25, callback=multi)
```

### Custom formatter

Return a dict to send, or `None` to suppress the event entirely:

```python
async def my_format(event: dict) -> dict | None:
    if event["event"] != "thread_reply":
        return None   # ignore everything except replies
    return {
        "content": f"New reply in **{event['subject']}**\n{event['snippet']}"
    }

webhook = HFWebhook("https://discord.com/api/webhooks/...", formatter=my_format)
watcher.watch_thread(tid=6083735, callback=webhook.callback)
```

---

## CLI

After running `pip install -e .` you get the `hf` command globally. Every command has `--help`.

```
hf --help
hf me --help
hf user --help
```

### Auth
```bash
hf auth start           # open HF in browser to approve your app
hf auth status          # check if you're authenticated
hf auth logout          # clear stored token
hf auth uid             # print your UID
hf login                # shortcut for `hf auth start`
```

### Me
```bash
hf me                   # your full profile
hf me bytes             # your bytes balance
hf me pms               # unread PM count
hf me rep               # your reputation
hf me --json            # full profile as raw JSON
```

### Users
```bash
hf user 761578                        # look up a user
hf user 761578 posts                  # their recent posts
hf user 761578 posts --all            # all posts (auto-paginate)
hf user 761578 posts --all --max-pages 10
hf user 761578 threads                # their threads
hf user 761578 bytes                  # bytes they received
hf user 761578 contracts              # their contracts
hf user 761578 bratings               # b-ratings they received
hf user 761578 score                  # their b-rating score
hf user 761578 --json                 # raw JSON
```

### Posts
```bash
hf posts 59852445                     # get a post by ID
hf posts thread 6083735               # posts in a thread (page 1)
hf posts thread 6083735 2             # page 2
hf posts thread 6083735 --all         # all pages
hf posts thread 6083735 --all --max-pages 5
hf posts thread 6083735 --json
```

### Threads
```bash
hf thread 6083735                     # thread info
hf thread 6083735 posts               # posts in thread
hf thread 6083735 --json
```

### Forums
```bash
hf forum 25                           # threads in a forum
hf forum 25 info                      # forum name/description/type
hf forum 25 --json
```

### Bytes
```bash
hf send 1337 5                        # send 5 bytes to UID 1337
hf send 1337 5 "thanks for the deal"  # with a reason
hf bytes received 761578              # bytes received by a user
hf bytes received 761578 --all        # all pages
hf bytes sent 761578                  # bytes sent by a user
hf deposit 100                        # deposit bytes into your API vault
hf withdraw 50                        # withdraw bytes from vault
hf bump 6083735                       # bump a thread with bytes
```

### Contracts
```bash
hf contracts 761578                   # all contracts for a user
hf contracts 761578 --active          # active contracts only
hf contracts 761578 --all             # auto-paginate all contracts
hf contract 279461                    # single contract by ID
hf contracts 761578 --json
```

### B-Ratings
```bash
hf bratings 761578                    # b-ratings received
hf bratings 761578 --given            # b-ratings given
hf bratings 761578 --all              # all pages
hf brating score 761578               # total score
hf bratings 761578 --json
```

### Disputes
```bash
hf disputes 84                        # dispute by ID
hf disputes contracts 409675 409610   # disputes for contract IDs
hf disputes contracts 409675 --json
```

### BBCode
```bash
hf bbcode strip "[b]hello[/b]"
hf bbcode html "[b]hello[/b]"
hf bbcode mentions "[mention]Stan[/mention] check this"
hf bbcode quotes "[quote='Stan']old msg[/quote] new reply"
hf bbcode links "[url=https://x.com]x[/url]"
hf bbcode preview "[b]long post content here...[/b]"
hf bbcode preview "[b]long post[/b]" --length 60
```

---

## Code Examples

### Send bytes
```python
from HFAuth import HFAuth
from HFBytes import HFBytes

token     = HFAuth().get_access_token()
bytes_api = HFBytes(token)
txid      = bytes_api.send(to_uid=1337, amount=5, reason="Thanks!")
print(txid)
```

### Deposit / withdraw / bump
```python
from HFBytes import HFBytes

bytes_api = HFBytes(token)

# Deposit bytes from your account into your API client vault
bytes_api.deposit(100)

# Withdraw bytes from vault back to your account
bytes_api.withdraw(50)

# Bump a thread with bytes (cost determined by HF)
bytes_api.bump(tid=6083735)
```

### Get your profile
```python
from HFMe import HFMe

me = HFMe(token).get()
print(me["username"], me["bytes"], me["unreadpms"])
```

### Get all posts by a user (auto-paginate)
```python
from HFPosts import HFPosts

posts = HFPosts(token).get_all_by_user(uid=761578, max_pages=10)
print(f"{len(posts)} posts found")
```

### Only new posts since last check
```python
# Stops when it hits a post you've already seen
posts = HFPosts(token).get_all_by_user(uid=761578, stop_at_pid=last_known_pid)
```

### Get all threads by a user
```python
from HFThreads import HFThreads

threads = HFThreads(token).get_all_by_user(uid=761578)
```

### Get all threads a user has participated in

`threads _uid` only returns threads where the user is the OP. To find threads they replied to but didn't create, pull their posts instead:

```python
from HFThreads import HFThreads
from HFPosts   import HFPosts

posts = HFPosts(token).get_by_user(uid=761578)
participated_tids = list({int(p["tid"]) for p in posts})
threads = HFThreads(token).get_many(participated_tids)
```

### Lightweight thread poll — lastposter is a free field

`poll_lastpost()` is a cheap batched call for checking activity across many threads at once. `lastposter` (the replier's username) comes back on every thread response for free — no follow-up `users _uid` call needed:

```python
from HFThreads import HFThreads

rows = HFThreads(token).poll_lastpost([6083735, 6084000, 6085000])

for t in rows:
    print(t["tid"], t["lastposter"], t["lastpost"])
    # lastposter is the username string — already there, no extra call needed
```

### Parse BBCode from a post
```python
from HFBBCode import HFBBCode

raw      = '[b]Hello[/b] [quote=\'Stan\']old msg[/quote] [url=https://x.com]link[/url]'
text     = HFBBCode.to_text(raw)       # "Hello old msg link"
html     = HFBBCode.to_html(raw)       # "<b>Hello</b> <blockquote>...</blockquote> ..."
preview  = HFBBCode.preview(raw, 80)   # short plain text, no quotes
mentions = HFBBCode.extract_mentions(raw)
quotes   = HFBBCode.extract_quotes(raw)
is_reply = HFBBCode.is_reply_to(raw, "stan")  # True
```

### Get all bytes received (auto-paginate)
```python
from HFBytes import HFBytes

all_tx = HFBytes(token).get_all_received(uid=761578, max_pages=20)
total  = sum(float(t["amount"]) for t in all_tx)
print(f"Total received: {total}")
```

### Get contracts
```python
from HFContracts import HFContracts

contracts = HFContracts(token).get_by_user(uid=761578)
active    = HFContracts(token).get_active(uid=761578)
```

### Get b-ratings and score
```python
from HFBratings import HFBratings

ratings = HFBratings(token).get_received(uid=761578)
score   = HFBratings(token).get_score(uid=761578)
print(f"Score: {score:+d}")
```

### Check disputes for contracts
```python
from HFDisputes import HFDisputes

# Always query by contract IDs — _uid returns 503
disputes = HFDisputes(token).get_by_contracts([409675, 409610])
for d in disputes:
    print(d["cdid"], d["status"])
```

### Post a reply
```python
from HFPosts import HFPosts

post = HFPosts(token).reply(tid=6083735, message="Hello from the API!")
print(post["pid"])
```

### Create a thread
```python
from HFThreads import HFThreads

thread = HFThreads(token).create(fid=375, subject="Test", message="Hello!")
print(thread["tid"])
```

---

## Web UI (server.py)

| Route | Description |
|-------|-------------|
| `/install` | Start OAuth flow |
| `/me` | Your profile |
| `/send-bytes` | Send bytes form |
| `/user/<uid>` | Any user's profile |
| `/posts/<uid>` | User's recent posts |
| `/threads/<uid>` | User's recent threads |
| `/contracts/<uid>` | User's contracts |
| `/bratings/<uid>` | User's b-ratings |
| `/api/me` | JSON |
| `/api/user/<uid>` | JSON |
| `/api/posts/user/<uid>` | JSON |
| `/api/posts/thread/<tid>` | JSON |
| `/api/contracts/user/<uid>` | JSON |
| `/api/bratings/user/<uid>` | JSON |

---

## Auto-Pagination

Every paged endpoint has a `get_all_*` method.

```python
# Instead of manually looping pages:
page1 = api.get_by_user(uid, page=1)
page2 = api.get_by_user(uid, page=2)
# ...

# Just do:
all_results = api.get_all_by_user(uid, max_pages=50)
```

Available on: `HFPosts`, `HFThreads`, `HFBytes`, `HFContracts`, `HFBratings`

---

## Notes

- **Rate limit** — HF enforces a rolling hourly call limit and returns `MAX_HOURLY_CALLS_EXCEEDED` in the response body when you hit it. The remaining call count comes back in the `x-rate-limit-remaining` header on every response.
- **Proxy** — Cloudflare sometimes blocks datacenter and VPS IPs. 
- **Disputes** — Querying disputes by `_uid` consistently returns 503. The only reliable filters are `_cid` (contract ID) and `_cdid` (dispute ID).
- **Thread batches** — When fetching multiple TIDs in one request, a single private or deleted thread will cause the whole batch to fail. Bisect the list to find the bad TID.
- **Token expiry** — Tokens last around 90 days. Once expired the API returns 401 on every call. Re-auth via `hf auth start`.
- **Scopes** — Permissions are configured per-app on the HF Developer Panel. If an endpoint returns nothing or 403, check that your app has the required scope. Each class docstring lists what it needs.
- **BBCode** — Every `message` field from the API is raw BBCode. Run it through `HFBBCode.to_text()` before displaying, searching, or logging anything.
- **Response types** — The API returns everything as strings, including numeric fields like `pid`, `uid`, and `amount`. Cast them yourself: `int(post["pid"])`, `float(tx["amount"])`.
- **`threads _uid` is OP-only** — This endpoint only returns threads where the user is the original poster. Threads they replied to but didn't create are invisible here. Use `posts _uid` (`HFPosts.get_by_user()`) to find all threads a user has participated in.
- **`lastposter` is a free field** — Every thread response includes `lastposter` (the replier's username string) at no extra cost. You don't need a follow-up `users _uid` call just to get a display name for whoever last posted. `poll_lastpost()` requests it by default.
- **Users batching and 503s** — Similar 503 behaviour to disputes can occur with `users _uid` in certain contexts. If you're doing regular status checks on a list of users, make one call per user rather than batching them all together.
- **Forum watching and poll overhead** — `watch_forum()` tracks every thread it sees in `_seen_tids`. If you only want new thread alerts (not replies to every thread in the forum), don't funnel discovered TIDs into `watch_thread()` — let `posts _uid` discovery handle threads you actually reply to. Otherwise you end up polling hundreds of threads you don't care about.
- **Hot/cold polling** — `watch_thread()` polls all registered threads at the same fixed interval. If you're tracking many threads, threads with recent activity (hot) are worth polling frequently; threads with no posts in 30+ minutes (cold) aren't. Managing your own poll loop with two different intervals cuts call volume significantly without missing anything.

---

## Batch Requests

`HFBatch` packs multiple resource types into a **single `/read` POST** — one round trip instead of N API calls.

```python
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

print(result.me["username"])           # your username
print(result.users[0]["myps"])         # first user's bytes
print(result.threads[0]["subject"])    # first thread subject
print(len(result.posts))               # number of posts returned
```

Via CLI (fires one API call):
```bash
hf batch fetch --me --user 761578 --thread 6083735
hf batch fetch --me --forum 25 --json
```

`fetch()` resets the builder so you can reuse the same `HFBatch` instance:
```python
batch = HFBatch(hf)
r1 = await batch.me().user(1).fetch()
r2 = await batch.me().user(2).fetch()
```

---

## Persistent Event Deduplication (HFEventStore)

By default, `HFWatcher` deduplicates in memory — on restart, all events since the last poll re-fire. `HFEventStore` persists seen IDs to SQLite so restarts are safe.

```python
from HFWatcher   import HFWatcher
from HFEventStore import HFEventStore

store   = HFEventStore("events.db")
watcher = HFWatcher(hf, event_store=store)

# Seen IDs now survive restarts — no duplicate callbacks
watcher.watch_thread(tid=6083735, callback=on_reply)
asyncio.run(watcher.start())
```

Standalone usage:
```python
store = HFEventStore("events.db")

# Atomic check-and-record — returns True only if it was new
if store.add_if_new("thread_replies", f"tid_{tid}", pid):
    await on_reply(event)

# Filter a batch to only new IDs
new_pids = store.filter_new("thread_replies", f"tid_{tid}", all_pids)

# Seed on first poll (don't fire for existing events)
store.add_many("forum_threads", f"fid_{fid}", existing_tids)

# Maintenance
store.prune("thread_replies", f"tid_{tid}", keep=500)   # keep last 500 per thread
store.purge_old(days=7)                                  # delete events > 7 days old
store.stats()   # {"thread_replies": 1240, "bytes_received": 30, ...}

store.close()
```

---

## Response Caching (HFCache)

Slowly-changing data (user profiles, forum names) doesn't need a fresh API call every time.

```python
from HFCache import CachedHFUsers, CachedHFForums, CachedHFMe

# Drop-in replacements with built-in caching:
users  = CachedHFUsers(token, ttl=300)    # 5-minute cache
forums = CachedHFForums(token, ttl=3600)  # 1-hour cache
me_api = CachedHFMe(token, ttl=60)        # 1-minute cache

user  = users.get(761578)    # API call (miss)
user  = users.get(761578)    # from cache (hit) — no API call
names = users.get_usernames_map([1, 2, 3, 761578])   # cached+chunked

users.cache_stats
# {"entries": 4, "hits": 3, "misses": 1, "hit_rate": 0.75, "ttl": 300}
```

Manual cache for anything:
```python
from HFCache import HFCache

cache = HFCache(ttl=300)

# Manual get/set
contract = cache.get("contract", cid)
if contract is None:
    contract = contracts_api.get([cid])[0]
    cache.set("contract", cid, contract)

# Or use get_or_fetch():
contract = cache.get_or_fetch("contract", cid, lambda: contracts_api.get([cid])[0])

# Bust cache
cache.delete("contract", cid)    # specific entry
cache.invalidate("contract")     # entire namespace
cache.purge_expired()            # remove dead entries
```

TTL tuning guide:
- User profiles: `300s` (rarely change mid-session)
- Forum names: `3600s` (almost never change)
- Me profile: `60s` (bytes/unreadpms update often)
- Contracts: `120s` (status can change)

---

## BBCode Builder

`HFBBCodeBuilder` generates BBCode programmatically via a fluent chain API. Forget manual string concatenation and unclosed tags.

```python
from HFBBCodeBuilder import BBCode

post = (
    BBCode()
    .header("Service Thread", color="#5865F2")
    .newline()
    .section("Requirements", BBCode().list_items(["18+", "US only", "Vouches required"]).build())
    .hr()
    .bold("Price: ").price_tag(500, "bytes").newline()
    .text("Reply or DM ").mention("AuJusDemon").text(" to order.")
    .newline(2)
    .spoiler("Previous vouches", "...")
    .build()
)

# Post it:
HFPosts(token).reply(tid=6083735, message=post)
```

All formatting methods:
```python
BBCode().bold("text").build()                     # [b]text[/b]
BBCode().italic("text").build()                   # [i]text[/i]
BBCode().underline("text").build()                # [u]text[/u]
BBCode().strikethrough("text").build()            # [s]text[/s]
BBCode().color("text", "red").build()             # [color=red]text[/color]
BBCode().color("text", "#0070f3").build()         # hex color
BBCode().size("text", 20).build()                 # [size=20]text[/size]
BBCode().font("text", "Times New Roman").build()  # [font=Times New Roman]text[/font]
BBCode().left("text").build()                     # [align=left]text[/align]
BBCode().center("text").build()                   # [align=center]text[/align]
BBCode().right("text").build()                    # [align=right]text[/align]
BBCode().justify("text").build()                  # [align=justify]text[/align]
BBCode().url("https://hf.net", "HF").build()      # [url=...]HF[/url]
BBCode().thread_link(6083735, "API thread").build()
BBCode().profile_link(761578, "AuJusDemon").build()
BBCode().image("https://example.com/img.png").build()
BBCode().mention("AuJusDemon").build()            # [mention]AuJusDemon[/mention]
BBCode().quote("Stan", "msg", pid=12345).build()  # [quote='Stan' pid='12345']msg[/quote]
BBCode().code("python", "print('hi')").build()    # [code=python]...[/code]
BBCode().spoiler("Click", "Secret!").build()      # [spoiler=Click]Secret![/spoiler]
BBCode().hide("Reply to view").build()            # [hide]Reply to view[/hide]
BBCode().list_items(["A", "B", "C"]).build()      # [list][*]A...[/list]
BBCode().ordered_list(["1st", "2nd"]).build()     # [list=1][*]1st...[/list]
BBCode().hr().build()                             # [hr]
BBCode().newline(2).build()                       # \n\n
```

Class-level shortcuts (no chaining needed):
```python
BBCode.make_quote("Stan", "original msg", pid=12345)
BBCode.make_url("https://hackforums.net", "HF")
BBCode.make_mention("AuJusDemon")
BBCode.make_code("print('hello')", "python")
```

CLI:
```bash
hf build quote "Stan" "I think this deal is sketchy"
hf build url "https://hackforums.net" "HF"
hf build mention "AuJusDemon"
hf build code "print('hello')" --lang python
hf build spoiler "Secret content!" --label "Click to reveal"
hf build list "First item" "Second item" "Third item"
hf build list "Step one" "Step two" --ordered
```

---

## Type Hints

`HFTypes.py` exports TypedDicts for every API response shape, giving IDEs full autocomplete.

```python
from HFTypes import HFPost, HFThread, HFUser, HFContract, HFMe

post: HFPost = posts_api.get([pid])[0]
post["message"]   # IDE autocompletes — knows this is a str

user: HFUser = users_api.get(uid)
user["myps"]      # bytes balance

contract: HFContract = contracts_api.get([cid])[0]
contract["muid"]  # middleman UID — "" if no middleman
```

All types are in `HFTypes.py`:
- `HFMe`, `HFUser`, `HFPost`, `HFThread`, `HFForum`
- `HFBytesTx`, `HFBytesWriteResult`
- `HFContract`, `HFBrating`, `HFDispute`
- `HFSigmarketListing`, `HFSigmarketOrder`
- `HFContractSummary`, `HFBatchResult`
- Watcher event types: `HFEventThreadReply`, `HFEventNewThread`, `HFEventBytesReceived`, etc.

---

## Exceptions

`HFExceptions.py` provides a custom hierarchy. All exceptions are subclasses of `HFError`.

```python
from HFExceptions import (
    HFError,            # catch-all base
    HFAuthError,        # 401 — token expired or revoked
    HFRateLimitError,   # MAX_HOURLY_CALLS_EXCEEDED
    HFPermissionError,  # 403/503 — missing scope or Cloudflare block
    HFNotFoundError,    # empty result for a specific ID lookup
    HFServerError,      # unexpected 5xx
    HFParseError,       # non-JSON response
    HFTimeoutError,     # request timed out
    HFProxyError,       # proxy connection failed
)
```

Note: By default the wrapper returns `None`/`[]` on failure (original behaviour).
Exceptions are raised when your app explicitly handles them. Check individual module docs.

---

## Watch PMs

`HFMe.watch_pms()` fires when the authenticated user's unread PM count increases.
Uses the watcher + `unreadpms` polling — there's no dedicated PM endpoint in the API.

```python
from HFMe import HFMe

me_api = HFMe(token)

async def on_pm(event):
    print(f"You have {event['unread_count']} unread PMs "
          f"({event['new_since_last']} new)")

watcher = me_api.watch_pms(callback=on_pm, interval=60)
asyncio.run(watcher.start())
```

Requires 'Advanced Info' scope.

---
