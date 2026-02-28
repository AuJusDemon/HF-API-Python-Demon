"""
HF API CLI — installable command line interface for the HackForums API.

Install:
    pip install -e .

Usage:
    hf <command> [options]
    hf --help
"""

import json
import sys
import click

# ── Helpers ────────────────────────────────────────────────────────────────────

def get_token():
    from HFAuth import HFAuth
    token = HFAuth().get_access_token()
    if not token:
        click.echo("Not authenticated. Run: hf auth", err=True)
        sys.exit(1)
    return token


def print_table(rows, keys=None):
    if not rows:
        click.echo("No results.")
        return
    keys = keys or list(rows[0].keys())
    widths = {k: max(len(k), max((len(str(r.get(k, ""))) for r in rows), default=0)) for k in keys}
    click.echo("  ".join(k.ljust(widths[k]) for k in keys))
    click.echo("-" * sum(widths[k] + 2 for k in keys))
    for row in rows:
        click.echo("  ".join(str(row.get(k, "")).ljust(widths[k]) for k in keys))


def out(data, as_json=False, keys=None):
    if not data:
        click.echo("No result.")
        return
    if as_json:
        click.echo(json.dumps(data, indent=2))
        return
    if isinstance(data, list):
        print_table(data, keys)
    else:
        for k, v in data.items():
            click.echo(f"  {k:<22} {v}")


# ── Root ───────────────────────────────────────────────────────────────────────

@click.group()
def cli():
    """HackForums API CLI — full wrapper for the HF API v2."""
    pass


# ── Auth ───────────────────────────────────────────────────────────────────────

@cli.group()
def auth():
    """Manage authentication."""
    pass


@auth.command("start")
def auth_start():
    """Start OAuth flow — opens HF in your browser."""
    import webbrowser
    from HFAuth import HFAuth
    a = HFAuth()
    if a.is_authenticated():
        click.echo(f"Already authenticated as UID {a.get_uid()}.")
        return
    url = a.build_auth_url()
    click.echo(f"Opening: {url}")
    click.echo("Make sure server.py is running to receive the callback!")
    webbrowser.open(url)


@auth.command("status")
def auth_status():
    """Check if authenticated."""
    from HFAuth import HFAuth
    a = HFAuth()
    if a.is_authenticated():
        click.echo(f"Authenticated. UID: {a.get_uid()}")
    else:
        click.echo("Not authenticated. Run: hf auth start")


@auth.command("logout")
def auth_logout():
    """Clear stored token."""
    from HFAuth import HFAuth
    HFAuth().clear_token()
    click.echo("Logged out.")


@auth.command("uid")
def auth_uid():
    """Print your UID."""
    from HFAuth import HFAuth
    uid = HFAuth().get_uid()
    click.echo(uid or "Not authenticated.")


@cli.command("login")
def login():
    """Shortcut for `hf auth start`."""
    import webbrowser
    from HFAuth import HFAuth
    a = HFAuth()
    if a.is_authenticated():
        click.echo(f"Already authenticated as UID {a.get_uid()}.")
        return
    url = a.build_auth_url()
    click.echo(f"Opening: {url}")
    click.echo("Make sure server.py is running to receive the callback!")
    webbrowser.open(url)


# ── Me ─────────────────────────────────────────────────────────────────────────

@cli.group(invoke_without_command=True)
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON.")
@click.pass_context
def me(ctx, as_json):
    """Your profile. Run with no subcommand for full profile."""
    if ctx.invoked_subcommand is None:
        from HFMe import HFMe
        data = HFMe(get_token()).get()
        out(data, as_json)


@me.command("bytes")
def me_bytes():
    """Your bytes balance."""
    from HFMe import HFMe
    click.echo(HFMe(get_token()).get_bytes_balance())


@me.command("pms")
def me_pms():
    """Unread PM count."""
    from HFMe import HFMe
    click.echo(HFMe(get_token()).get_unread_pms())


@me.command("rep")
def me_rep():
    """Your reputation."""
    from HFMe import HFMe
    click.echo(HFMe(get_token()).get_reputation())


# ── User ───────────────────────────────────────────────────────────────────────

@cli.group(invoke_without_command=True)
@click.argument("uid", type=int)
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON.")
@click.pass_context
def user(ctx, uid, as_json):
    """Look up a user. Add a subcommand to get their posts, threads, etc."""
    ctx.ensure_object(dict)
    ctx.obj["uid"]     = uid
    ctx.obj["as_json"] = as_json
    if ctx.invoked_subcommand is None:
        from HFUsers import HFUsers
        out(HFUsers(get_token()).get(uid), as_json)


@user.command("posts")
@click.option("--all", "fetch_all", is_flag=True, help="Fetch all pages.")
@click.option("--max-pages", default=50, show_default=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def user_posts(ctx, fetch_all, max_pages, as_json):
    """Their recent posts."""
    uid = ctx.obj["uid"]
    from HFPosts import HFPosts
    api  = HFPosts(get_token())
    rows = api.get_all_by_user(uid, max_pages=max_pages) if fetch_all else api.get_by_user(uid)
    out(rows, as_json or ctx.obj["as_json"], ["pid", "tid", "fid", "dateline", "subject"])


@user.command("threads")
@click.option("--all", "fetch_all", is_flag=True)
@click.option("--max-pages", default=50, show_default=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def user_threads(ctx, fetch_all, max_pages, as_json):
    """Their threads."""
    uid = ctx.obj["uid"]
    from HFThreads import HFThreads
    api  = HFThreads(get_token())
    rows = api.get_all_by_user(uid, max_pages=max_pages) if fetch_all else api.get_by_user(uid)
    out(rows, as_json or ctx.obj["as_json"], ["tid", "subject", "numreplies", "lastposter", "dateline"])


@user.command("bytes")
@click.option("--all", "fetch_all", is_flag=True)
@click.option("--max-pages", default=50, show_default=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def user_bytes(ctx, fetch_all, max_pages, as_json):
    """Bytes they received."""
    uid = ctx.obj["uid"]
    from HFBytes import HFBytes
    api  = HFBytes(get_token())
    rows = api.get_all_received(uid, max_pages=max_pages) if fetch_all else api.get_received(uid)
    out(rows, as_json or ctx.obj["as_json"], ["id", "amount", "dateline", "reason", "type"])


@user.command("contracts")
@click.option("--all", "fetch_all", is_flag=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def user_contracts(ctx, fetch_all, as_json):
    """Their contracts."""
    uid = ctx.obj["uid"]
    from HFContracts import HFContracts
    api  = HFContracts(get_token())
    rows = api.get_all_by_user(uid) if fetch_all else api.get_by_user(uid)
    out(rows, as_json or ctx.obj["as_json"], ["cid", "iproduct", "iprice", "icurrency", "status", "muid", "inituid", "otheruid"])


@user.command("bratings")
@click.option("--all", "fetch_all", is_flag=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def user_bratings(ctx, fetch_all, as_json):
    """B-ratings they received."""
    uid = ctx.obj["uid"]
    from HFBratings import HFBratings
    api  = HFBratings(get_token())
    rows = api.get_all_received(uid) if fetch_all else api.get_received(uid)
    out(rows, as_json or ctx.obj["as_json"], ["crid", "contractid", "amount", "fromid", "message"])


@user.command("score")
@click.pass_context
def user_score(ctx):
    """Their total b-rating score."""
    uid = ctx.obj["uid"]
    from HFBratings import HFBratings
    score = HFBratings(get_token()).get_score(uid)
    click.echo(f"B-Rating score for UID {uid}: {score:+d}")


# ── Posts ──────────────────────────────────────────────────────────────────────

@cli.group(invoke_without_command=True)
@click.argument("pid", type=int, required=False)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def posts(ctx, pid, as_json):
    """Get post(s) by ID, or use a subcommand to get posts by thread."""
    ctx.ensure_object(dict)
    ctx.obj["as_json"] = as_json
    if ctx.invoked_subcommand is None:
        if not pid:
            click.echo(ctx.get_help())
            return
        from HFPosts import HFPosts
        rows = HFPosts(get_token()).get([pid])
        out(rows, as_json, ["pid", "tid", "uid", "dateline", "subject"])


@posts.command("thread")
@click.argument("tid", type=int)
@click.argument("page", type=int, default=1)
@click.option("--all", "fetch_all", is_flag=True, help="Fetch all pages.")
@click.option("--max-pages", default=50, show_default=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def posts_thread(ctx, tid, page, fetch_all, max_pages, as_json):
    """Posts in a thread. Pass a page number or --all for every page."""
    from HFPosts import HFPosts
    api = HFPosts(get_token())
    if fetch_all:
        rows = api.get_all_by_thread(tid, max_pages=max_pages)
    else:
        rows = api.get_by_thread(tid, page=page)
    out(rows, as_json or ctx.obj.get("as_json"), ["pid", "uid", "dateline", "subject"])


# ── Threads ────────────────────────────────────────────────────────────────────

@cli.group(invoke_without_command=True)
@click.argument("tid", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def thread(ctx, tid, as_json):
    """Get thread info. Use `posts` subcommand to get its posts."""
    ctx.ensure_object(dict)
    ctx.obj["tid"]     = tid
    ctx.obj["as_json"] = as_json
    if ctx.invoked_subcommand is None:
        from HFThreads import HFThreads
        out(HFThreads(get_token()).get(tid), as_json)


@thread.command("posts")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def thread_posts(ctx, as_json):
    """Posts in this thread."""
    tid = ctx.obj["tid"]
    from HFPosts import HFPosts
    rows = HFPosts(get_token()).get_by_thread(tid)
    out(rows, as_json or ctx.obj["as_json"], ["pid", "uid", "dateline", "subject"])


# ── Forums ─────────────────────────────────────────────────────────────────────

@cli.group(invoke_without_command=True)
@click.argument("fid", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def forum(ctx, fid, as_json):
    """Get threads in a forum. Use `info` subcommand for forum details."""
    ctx.ensure_object(dict)
    ctx.obj["fid"]     = fid
    ctx.obj["as_json"] = as_json
    if ctx.invoked_subcommand is None:
        from HFThreads import HFThreads
        rows = HFThreads(get_token()).get_by_forum(fid)
        out(rows, as_json, ["tid", "subject", "username", "numreplies", "lastposter"])


@forum.command("info")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def forum_info(ctx, as_json):
    """Forum details (name, description, type)."""
    fid = ctx.obj["fid"]
    from HFForums import HFForums
    out(HFForums(get_token()).get(fid), as_json or ctx.obj["as_json"])


# ── Bytes ──────────────────────────────────────────────────────────────────────

@cli.command("send")
@click.argument("uid", type=int)
@click.argument("amount", type=int)
@click.argument("reason", default="")
def send(uid, amount, reason):
    """Send bytes to a user.

    \b
    Examples:
      hf send 1337 5
      hf send 1337 5 "thanks for the deal"
    """
    from HFBytes import HFBytes
    txid = HFBytes(get_token()).send(uid, amount, reason)
    if txid:
        click.echo(f"Sent {amount} bytes to UID {uid}. Transaction ID: {txid}")
    else:
        click.echo("Failed to send bytes.", err=True)
        sys.exit(1)


@cli.group()
def bytes():
    """Read bytes transaction history."""
    pass


@bytes.command("received")
@click.argument("uid", type=int)
@click.option("--all", "fetch_all", is_flag=True, help="Fetch all pages.")
@click.option("--max-pages", default=50, show_default=True)
@click.option("--json", "as_json", is_flag=True)
def bytes_received(uid, fetch_all, max_pages, as_json):
    """Bytes received by a user."""
    from HFBytes import HFBytes
    api  = HFBytes(get_token())
    rows = api.get_all_received(uid, max_pages=max_pages) if fetch_all else api.get_received(uid)
    out(rows, as_json, ["id", "amount", "dateline", "reason", "type"])


@bytes.command("sent")
@click.argument("uid", type=int)
@click.option("--all", "fetch_all", is_flag=True)
@click.option("--max-pages", default=50, show_default=True)
@click.option("--json", "as_json", is_flag=True)
def bytes_sent(uid, fetch_all, max_pages, as_json):
    """Bytes sent by a user."""
    from HFBytes import HFBytes
    api  = HFBytes(get_token())
    rows = api.get_all_sent(uid, max_pages=max_pages) if fetch_all else api.get_sent(uid)
    out(rows, as_json, ["id", "amount", "dateline", "reason", "type"])


@cli.command("deposit")
@click.argument("amount", type=int)
def deposit(amount):
    """Deposit bytes into your API client vault.

    \b
    Example:
      hf deposit 100
    """
    from HFBytes import HFBytes
    ok = HFBytes(get_token()).deposit(amount)
    click.echo(f"Deposited {amount} bytes into vault." if ok else "Failed to deposit.")
    if not ok:
        sys.exit(1)


@cli.command("withdraw")
@click.argument("amount", type=int)
def withdraw(amount):
    """Withdraw bytes from your API vault back to your account.

    \b
    Example:
      hf withdraw 50
    """
    from HFBytes import HFBytes
    ok = HFBytes(get_token()).withdraw(amount)
    click.echo(f"Withdrew {amount} bytes from vault." if ok else "Failed to withdraw.")
    if not ok:
        sys.exit(1)


@cli.command("bump")
@click.argument("tid", type=int)
def bump(tid):
    """Bump a thread with bytes.

    \b
    Example:
      hf bump 6083735
    """
    from HFBytes import HFBytes
    ok = HFBytes(get_token()).bump(tid)
    click.echo(f"Thread {tid} bumped." if ok else "Failed to bump thread.")
    if not ok:
        sys.exit(1)


# ── Contracts ──────────────────────────────────────────────────────────────────

@cli.group(invoke_without_command=True)
@click.argument("uid", type=int)
@click.option("--active",         is_flag=True, help="Active contracts only (not cancelled/complete/incomplete).")
@click.option("--pending",        is_flag=True, help="Pending approval from either party.")
@click.option("--complete",       is_flag=True, help="Completed contracts.")
@click.option("--incomplete",     is_flag=True, help="Timed-out / incomplete contracts.")
@click.option("--cancelled",      is_flag=True, help="Cancelled contracts.")
@click.option("--disputed",       is_flag=True, help="Contracts with an open dispute.")
@click.option("--cancel-pending", is_flag=True, help="Cancellation requested but not yet resolved.")
@click.option("--middleman",      is_flag=True, help="Contracts involving a middleman/escrow (muid set).")
@click.option("--type",           "ctype", default="", help="Filter by position type: buying/selling/exchanging/trading/vouch_copy.")
@click.option("--all",            "fetch_all", is_flag=True, help="Auto-paginate all pages.")
@click.option("--json",           "as_json", is_flag=True)
@click.pass_context
def contracts(ctx, uid, active, pending, complete, incomplete, cancelled,
              disputed, cancel_pending, middleman, ctype, fetch_all, as_json):
    """Contracts for a user.

    \b
    Examples:
      hf contracts 761578
      hf contracts 761578 --active
      hf contracts 761578 --pending
      hf contracts 761578 --disputed
      hf contracts 761578 --cancel-pending
      hf contracts 761578 --middleman
      hf contracts 761578 --type selling
      hf contracts 761578 --all
      hf contracts 761578 summary
    """
    ctx.ensure_object(dict)
    ctx.obj["uid"]     = uid
    ctx.obj["as_json"] = as_json
    if ctx.invoked_subcommand is not None:
        return

    from HFContracts import HFContracts
    api  = HFContracts(get_token())
    keys = ["cid", "iproduct", "iprice", "icurrency", "type", "status", "muid", "inituid", "otheruid"]

    if disputed:
        rows = api.get_disputed(uid)
    elif cancel_pending:
        rows = api.get_cancellation_requested(uid)
    elif middleman:
        rows = api.get_middleman_contracts(uid)
    elif active:
        rows = api.get_active(uid)
    elif pending:
        rows = api.get_pending(uid)
    elif complete:
        rows = api.get_complete(uid)
    elif incomplete:
        rows = api.get_incomplete(uid)
    elif cancelled:
        rows = api.get_cancelled(uid)
    elif ctype:
        rows = api.get_by_type(uid, ctype)
    elif fetch_all:
        rows = api.get_all_by_user(uid)
    else:
        rows = api.get_by_user(uid)

    out(rows, as_json, keys)


@contracts.command("summary")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def contracts_summary(ctx, as_json):
    """Dashboard breakdown — counts by status, type, middleman, dispute, etc.

    \b
    Example:
      hf contracts 761578 summary
    """
    uid = ctx.obj["uid"]
    from HFContracts import HFContracts
    summary = HFContracts(get_token()).get_summary(uid)
    out(summary, as_json)


@cli.command("contract")
@click.argument("cid", type=int)
@click.option("--full", is_flag=True, help="Include nested parties, escrow, thread, disputes, b-ratings.")
@click.option("--json", "as_json", is_flag=True)
def contract(cid, full, as_json):
    """Get a single contract by ID.

    \b
    Examples:
      hf contract 279461
      hf contract 279461 --full
      hf contract 279461 --full --json
    """
    from HFContracts import HFContracts
    api  = HFContracts(get_token())
    data = api.get_full(cid) if full else (api.get([cid]) or [None])[0]
    out(data, as_json)


# ── B-Ratings ──────────────────────────────────────────────────────────────────

@cli.group(invoke_without_command=True)
@click.argument("uid", type=int)
@click.option("--given", is_flag=True, help="Show b-ratings given instead of received.")
@click.option("--all", "fetch_all", is_flag=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def bratings(ctx, uid, given, fetch_all, as_json):
    """B-ratings for a user."""
    ctx.ensure_object(dict)
    ctx.obj["uid"]     = uid
    ctx.obj["as_json"] = as_json
    if ctx.invoked_subcommand is None:
        from HFBratings import HFBratings
        api = HFBratings(get_token())
        if given:
            rows = api.get_all_given(uid) if fetch_all else api.get_given(uid)
        else:
            rows = api.get_all_received(uid) if fetch_all else api.get_received(uid)
        out(rows, as_json, ["crid", "contractid", "amount", "fromid", "toid", "message"])


@cli.group()
def brating():
    """B-rating utilities."""
    pass


@brating.command("score")
@click.argument("uid", type=int)
def brating_score(uid):
    """Total b-rating score for a user."""
    from HFBratings import HFBratings
    score = HFBratings(get_token()).get_score(uid)
    click.echo(f"B-Rating score for UID {uid}: {score:+d}")


# ── Disputes ───────────────────────────────────────────────────────────────────

@cli.group(invoke_without_command=True)
@click.argument("cdid", type=int, required=False)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def disputes(ctx, cdid, as_json):
    """Get disputes by ID, or use `contracts` subcommand to get by contract."""
    ctx.ensure_object(dict)
    ctx.obj["as_json"] = as_json
    if ctx.invoked_subcommand is None:
        if not cdid:
            click.echo(ctx.get_help())
            return
        from HFDisputes import HFDisputes
        rows = HFDisputes(get_token()).get([cdid])
        out(rows, as_json, ["cdid", "contractid", "status", "claimantuid", "defendantuid"])


@disputes.command("contracts")
@click.argument("cids", type=int, nargs=-1, required=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def disputes_contracts(ctx, cids, as_json):
    """Get disputes for one or more contract IDs.

    \b
    Example:
      hf disputes contracts 409675 409610
    """
    from HFDisputes import HFDisputes
    rows = HFDisputes(get_token()).get_by_contracts(list(cids))
    out(rows, as_json or ctx.obj.get("as_json"), ["cdid", "contractid", "status", "claimantuid", "defendantuid"])


# ── BBCode ─────────────────────────────────────────────────────────────────────

@cli.group()
def bbcode():
    """Parse and convert BBCode from HF posts."""
    pass


@bbcode.command("strip")
@click.argument("text")
def bbcode_strip(text):
    """Strip all BBCode — output plain text."""
    from HFBBCode import HFBBCode
    click.echo(HFBBCode.to_text(text))


@bbcode.command("html")
@click.argument("text")
def bbcode_html(text):
    """Convert BBCode to HTML."""
    from HFBBCode import HFBBCode
    click.echo(HFBBCode.to_html(text))


@bbcode.command("mentions")
@click.argument("text")
def bbcode_mentions(text):
    """Extract all @mentions from a post."""
    from HFBBCode import HFBBCode
    click.echo(json.dumps(HFBBCode.extract_mentions(text), indent=2))


@bbcode.command("quotes")
@click.argument("text")
def bbcode_quotes(text):
    """Extract all quoted blocks from a post."""
    from HFBBCode import HFBBCode
    click.echo(json.dumps(HFBBCode.extract_quotes(text), indent=2))


@bbcode.command("links")
@click.argument("text")
def bbcode_links(text):
    """Extract all links from a post."""
    from HFBBCode import HFBBCode
    click.echo(json.dumps(HFBBCode.extract_links(text), indent=2))


@bbcode.command("preview")
@click.argument("text")
@click.option("--length", default=120, show_default=True, help="Max preview length.")
def bbcode_preview(text, length):
    """Short plain-text preview of a post."""
    from HFBBCode import HFBBCode
    click.echo(HFBBCode.preview(text, length))


# ── BBCode Builder ─────────────────────────────────────────────────────────────

@cli.group()
def build():
    """Build BBCode strings programmatically."""
    pass


@build.command("quote")
@click.argument("author")
@click.argument("content")
@click.option("--pid", type=int, default=0, help="Post ID for the quote anchor.")
def build_quote(author, content, pid):
    """Build a BBCode quote block.

    \b
    Examples:
      hf build quote "Stan" "I think this deal is sketchy"
      hf build quote "Stan" "original msg" --pid 59852445
    """
    from HFBBCodeBuilder import BBCode
    click.echo(BBCode.make_quote(author, content, pid or None))


@build.command("url")
@click.argument("href")
@click.argument("label", default="")
def build_url(href, label):
    """Build a BBCode hyperlink.

    \b
    Examples:
      hf build url "https://hackforums.net" "HF"
      hf build url "https://hackforums.net"
    """
    from HFBBCodeBuilder import BBCode
    click.echo(BBCode.make_url(href, label or None))


@build.command("mention")
@click.argument("username")
def build_mention(username):
    """Build a BBCode mention tag (triggers HF notification).

    \b
    Example:
      hf build mention "AuJusDemon"
    """
    from HFBBCodeBuilder import BBCode
    click.echo(BBCode.make_mention(username))


@build.command("code")
@click.argument("content")
@click.option("--lang", default="", help="Syntax highlighting language (python, php, etc.)")
def build_code(content, lang):
    """Build a BBCode code block.

    \b
    Examples:
      hf build code "print('hello')" --lang python
      hf build code "SELECT * FROM users"
    """
    from HFBBCodeBuilder import BBCode
    click.echo(BBCode.make_code(content, lang or None))


@build.command("spoiler")
@click.argument("content")
@click.option("--label", default="", help="Spoiler button label.")
def build_spoiler(content, label):
    """Build a BBCode spoiler block.

    \b
    Examples:
      hf build spoiler "Hidden content!"
      hf build spoiler "The answer is 42" --label "Click to reveal"
    """
    from HFBBCodeBuilder import BBCode
    click.echo(BBCode().spoiler(label or None, content).build())


@build.command("list")
@click.argument("items", nargs=-1, required=True)
@click.option("--ordered", is_flag=True, help="Numbered list instead of bullet list.")
def build_list(items, ordered):
    """Build a BBCode list.

    \b
    Examples:
      hf build list "First item" "Second item" "Third item"
      hf build list "Step one" "Step two" --ordered
    """
    from HFBBCodeBuilder import BBCode
    b = BBCode()
    if ordered:
        click.echo(b.ordered_list(list(items)).build())
    else:
        click.echo(b.list_items(list(items)).build())


# ── Batch ──────────────────────────────────────────────────────────────────────

@cli.group()
def batch():
    """Batch multiple API lookups into one call."""
    pass


@batch.command("fetch")
@click.option("--me",      is_flag=True, help="Include your profile.")
@click.option("--user",    "uids",  multiple=True, type=int, help="Include user(s) by UID.")
@click.option("--thread",  "tids",  multiple=True, type=int, help="Include thread(s) by TID.")
@click.option("--forum",   "fids",  multiple=True, type=int, help="Include forum(s) by FID.")
@click.option("--post",    "pids",  multiple=True, type=int, help="Include post(s) by PID.")
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON.")
def batch_fetch(me, uids, tids, fids, pids, as_json):
    """Fetch multiple resources in a single API call.

    \b
    Examples:
      hf batch fetch --me --user 761578 --thread 6083735
      hf batch fetch --me --forum 25 --json
      hf batch fetch --user 761578 --user 1337 --post 59852445
    """
    import asyncio
    from HFBatch import HFBatch
    from HFClient import HFClient

    token = get_token()

    async def run():
        hf = HFClient(token)
        b  = HFBatch(hf)
        if me:
            b.me()
        if uids:
            b.users(list(uids))
        if tids:
            b.threads(tids=list(tids))
        if fids:
            for fid in fids:
                b.threads(fid=fid)
        if pids:
            b.posts(pids=list(pids))
        return await b.fetch()

    result = asyncio.run(run())

    if as_json:
        click.echo(json.dumps(result._raw, indent=2))
        return

    if result.me:
        click.echo("\n[me]")
        for k, v in result.me.items():
            click.echo(f"  {k:<22} {v}")
    if result.users:
        click.echo("\n[users]")
        print_table(result.users, ["uid", "username", "usergroup", "myps", "reputation"])
    if result.threads:
        click.echo("\n[threads]")
        print_table(result.threads, ["tid", "subject", "numreplies", "lastposter"])
    if result.posts:
        click.echo("\n[posts]")
        print_table(result.posts, ["pid", "tid", "uid", "dateline", "subject"])


# ── Cache stats ─────────────────────────────────────────────────────────────────

@cli.command("cache-stats")
def cache_stats():
    """Show cache statistics (if using CachedHF* classes)."""
    click.echo("Cache stats are per-session — instantiate CachedHFUsers/CachedHFForums/CachedHFMe")
    click.echo("and call .cache_stats to see hit rate, entries, etc.")
    click.echo("")
    click.echo("Example:")
    click.echo("  from HFCache import CachedHFUsers")
    click.echo("  users = CachedHFUsers(token, ttl=300)")
    click.echo("  users.get(761578)  # miss")
    click.echo("  users.get(761578)  # hit")
    click.echo("  print(users.cache_stats)")
    click.echo("  # {'entries': 1, 'hits': 1, 'misses': 1, 'hit_rate': 0.5, 'ttl': 300}")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
