"""
HF API Python — Flask server
Handles OAuth callback and provides a web UI for common actions.

Bug #3 fix: The send-bytes POST handler referenced bytes_api.last_error,
which does not exist on HFBytes or HFClient. This caused an AttributeError
whenever bytes sending failed — exactly when the error message was needed.
Replaced with a plain failure message; the underlying error is already
logged by HFClient at the WARNING level.

Run:
    python server.py
"""

from flask import Flask, request, redirect, render_template_string, jsonify
from HFAuth import HFAuth
from HFBytes import HFBytes
from HFMe import HFMe
from HFUsers import HFUsers
from HFPosts import HFPosts
from HFThreads import HFThreads
from HFForums import HFForums
from HFContracts import HFContracts
from HFBratings import HFBratings
from HFDisputes import HFDisputes

app = Flask(__name__)


def get_token() -> str | None:
    auth = HFAuth()
    return auth.get_access_token()


def require_auth():
    token = get_token()
    if not token:
        return None, redirect("/install")
    return token, None


# ── Auth ───────────────────────────────────────────────────────────────────────

@app.route("/install")
def install():
    auth = HFAuth()
    if auth.is_authenticated():
        return redirect("/success")
    return redirect(auth.build_auth_url())


@app.route("/callback")
def callback():
    auth_code = request.args.get("code")
    state     = request.args.get("state")

    if not auth_code:
        return "Error: No authorization code received.", 400

    auth = HFAuth()
    ok   = auth.handle_token_exchange(auth_code, state)
    if ok:
        return redirect("/success")
    return "Authorization failed. The link may have expired (10 min limit). <a href='/install'>Try again</a>.", 400


@app.route("/success")
def success():
    token = get_token()
    if not token:
        return redirect("/install")
    me_api = HFMe(token)
    me     = me_api.get()
    name   = me.get("username", "?") if me else "?"
    return f"""
    <h2>✅ Connected as <b>{name}</b></h2>
    <ul>
        <li><a href='/me'>My Profile</a></li>
        <li><a href='/send-bytes'>Send Bytes</a></li>
        <li><a href='/contracts/{me.get("uid", "") if me else ""}'>My Contracts</a></li>
        <li><a href='/bratings/{me.get("uid", "") if me else ""}'>My B-Ratings</a></li>
    </ul>
    """


@app.route("/logout")
def logout():
    HFAuth().clear_token()
    return redirect("/install")


# ── Me ─────────────────────────────────────────────────────────────────────────

@app.route("/me")
def me():
    token, err = require_auth()
    if err: return err
    data = HFMe(token).get()
    if not data:
        return "Failed to fetch profile.", 500
    rows = "".join(f"<tr><td><b>{k}</b></td><td>{v}</td></tr>" for k, v in data.items())
    return f"<h2>My Profile</h2><table border=1>{rows}</table>"


# ── Bytes ──────────────────────────────────────────────────────────────────────

SEND_BYTES_FORM = """
<!DOCTYPE html><html><head><title>Send Bytes</title></head><body>
<h2>Send Bytes</h2>
<form method="post">
    To UID: <input type="number" name="uid" required><br><br>
    Amount: <input type="number" name="amount" required><br><br>
    Reason: <input type="text" name="reason"><br><br>
    Post ID (optional): <input type="number" name="pid"><br><br>
    <input type="submit" value="Send Bytes">
</form>
{% if message %}<p><b>{{ message }}</b></p>{% endif %}
</body></html>
"""

@app.route("/send-bytes", methods=["GET"])
def send_bytes_form():
    return render_template_string(SEND_BYTES_FORM, message="")


@app.route("/send-bytes", methods=["POST"])
def send_bytes_submit():
    token, err = require_auth()
    if err: return err

    uid    = request.form.get("uid", "")
    amount = request.form.get("amount", "")
    reason = request.form.get("reason", "")
    pid    = request.form.get("pid", 0)

    if not uid or not amount:
        return render_template_string(SEND_BYTES_FORM, message="UID and amount are required.")

    bytes_api = HFBytes(token)
    txid      = bytes_api.send(int(uid), int(amount), reason, int(pid) if pid else 0)

    if txid:
        msg = f"✅ Sent {amount} bytes to UID {uid}. Transaction ID: {txid}"
    else:
        # Bug #3 fix: bytes_api.last_error does not exist on HFBytes/HFClient.
        # HFClient already logs the error at WARNING level. Show a plain message.
        msg = f"❌ Failed to send bytes to UID {uid}. Check the server log for details."

    return render_template_string(SEND_BYTES_FORM, message=msg)


# ── Users ──────────────────────────────────────────────────────────────────────

@app.route("/user/<int:uid>")
def user_profile(uid):
    token, err = require_auth()
    if err: return err
    user = HFUsers(token).get(uid)
    if not user:
        return f"User {uid} not found.", 404
    rows = "".join(f"<tr><td><b>{k}</b></td><td>{v}</td></tr>" for k, v in user.items())
    return f"<h2>User {uid}</h2><table border=1>{rows}</table>"


# ── Posts ──────────────────────────────────────────────────────────────────────

@app.route("/posts/<int:uid>")
def user_posts(uid):
    token, err = require_auth()
    if err: return err
    posts = HFPosts(token).get_by_user(uid, page=1, perpage=20)
    if not posts:
        return f"No posts found for UID {uid}."
    rows = "".join(
        f"<tr><td>{p.get('pid')}</td><td>tid:{p.get('tid')}</td>"
        f"<td>{p.get('subject','')}</td><td><small>{p.get('message','')[:100]}</small></td></tr>"
        for p in posts
    )
    return f"<h2>Posts by UID {uid}</h2><table border=1><tr><th>PID</th><th>Thread</th><th>Subject</th><th>Message</th></tr>{rows}</table>"


# ── Threads ────────────────────────────────────────────────────────────────────

@app.route("/threads/<int:uid>")
def user_threads(uid):
    token, err = require_auth()
    if err: return err
    threads = HFThreads(token).get_by_user(uid, page=1, perpage=20)
    if not threads:
        return f"No threads found for UID {uid}."
    rows = "".join(
        f"<tr><td><a href='https://hackforums.net/showthread.php?tid={t.get('tid')}' target='_blank'>"
        f"{t.get('tid')}</a></td><td>{t.get('subject','')}</td>"
        f"<td>{t.get('numreplies','0')} replies</td></tr>"
        for t in threads
    )
    return f"<h2>Threads by UID {uid}</h2><table border=1><tr><th>TID</th><th>Subject</th><th>Replies</th></tr>{rows}</table>"


# ── Contracts ──────────────────────────────────────────────────────────────────

@app.route("/contracts/<int:uid>")
def user_contracts(uid):
    token, err = require_auth()
    if err: return err
    contracts = HFContracts(token).get_by_user(uid)
    if not contracts:
        return f"No contracts found for UID {uid}."
    rows = "".join(
        f"<tr><td><a href='https://hackforums.net/contract.php?cid={c.get('cid')}' target='_blank'>"
        f"{c.get('cid')}</a></td><td>{c.get('iproduct','')}</td>"
        f"<td>{c.get('iprice','?')} {c.get('icurrency','bytes')}</td>"
        f"<td>{c.get('status','')}</td></tr>"
        for c in contracts
    )
    return f"<h2>Contracts for UID {uid}</h2><table border=1><tr><th>CID</th><th>Product</th><th>Price</th><th>Status</th></tr>{rows}</table>"


# ── B-Ratings ──────────────────────────────────────────────────────────────────

@app.route("/bratings/<int:uid>")
def user_bratings(uid):
    token, err = require_auth()
    if err: return err
    ratings = HFBratings(token).get_received(uid)
    if not ratings:
        return f"No b-ratings found for UID {uid}."
    score = sum(int(r.get("amount", 0)) for r in ratings)
    rows  = "".join(
        f"<tr><td>{r.get('crid')}</td><td>{r.get('contractid')}</td>"
        f"<td>{'👍 +1' if int(r.get('amount',0)) > 0 else '👎 -1'}</td>"
        f"<td>From UID {r.get('fromid')}</td><td>{r.get('message','')}</td></tr>"
        for r in ratings
    )
    return (
        f"<h2>B-Ratings for UID {uid} — Score: {score:+d}</h2>"
        f"<table border=1><tr><th>CRID</th><th>Contract</th><th>Rating</th><th>From</th><th>Message</th></tr>{rows}</table>"
    )


# ── API endpoints (JSON) ───────────────────────────────────────────────────────

@app.route("/api/me")
def api_me():
    token, err = require_auth()
    if err: return jsonify({"error": "not authenticated"}), 401
    return jsonify(HFMe(token).get() or {})


@app.route("/api/user/<int:uid>")
def api_user(uid):
    token, err = require_auth()
    if err: return jsonify({"error": "not authenticated"}), 401
    return jsonify(HFUsers(token).get(uid) or {})


@app.route("/api/posts/user/<int:uid>")
def api_posts_user(uid):
    token, err = require_auth()
    if err: return jsonify({"error": "not authenticated"}), 401
    page    = int(request.args.get("page", 1))
    perpage = int(request.args.get("perpage", 20))
    return jsonify(HFPosts(token).get_by_user(uid, page, perpage))


@app.route("/api/posts/thread/<int:tid>")
def api_posts_thread(tid):
    token, err = require_auth()
    if err: return jsonify({"error": "not authenticated"}), 401
    page    = int(request.args.get("page", 1))
    perpage = int(request.args.get("perpage", 20))
    return jsonify(HFPosts(token).get_by_thread(tid, page, perpage))


@app.route("/api/threads/user/<int:uid>")
def api_threads_user(uid):
    token, err = require_auth()
    if err: return jsonify({"error": "not authenticated"}), 401
    return jsonify(HFThreads(token).get_by_user(uid))


@app.route("/api/contracts/user/<int:uid>")
def api_contracts_user(uid):
    token, err = require_auth()
    if err: return jsonify({"error": "not authenticated"}), 401
    return jsonify(HFContracts(token).get_by_user(uid))


@app.route("/api/bratings/user/<int:uid>")
def api_bratings_user(uid):
    token, err = require_auth()
    if err: return jsonify({"error": "not authenticated"}), 401
    return jsonify(HFBratings(token).get_received(uid))


if __name__ == "__main__":
    print("HF API Python server starting on http://127.0.0.1:8001")
    print("Go to http://127.0.0.1:8001/install to authenticate")
    app.run(port=8001, debug=False)
