"""
DBZ Pilot Board
---------------
A tiny board for sharing / "piloting" a set of Cabal game accounts.

Per account it shows:
  * a status bar  -> green when someone is currently piloting it, grey when free
  * a text box for the pilot name + a WAR TIME dropdown (12 / 3 / 6 / 9 AM-PM)
  * a free-text "Notes" box (e.g. "playing until the 6PM war")
  * a "Start piloting" button, and a "Log off" button while it is in use

The "Pilot log" (bottom of the board, and the full page at /log) lists every
start / log-off with time, pilot, war time, notes and how long the session
lasted. It is always public so the owner can check who used an account if
something goes missing.

State is stored in Vercel KV (Upstash Redis) via its REST API when the
KV_REST_API_URL / KV_REST_API_TOKEN env vars are present. Without them the app
still runs but keeps state only in memory (fine for local testing, resets on
every serverless cold start).

Layout:
  api/index.py           this file (logic)
  api/templates/*.html    board / log / login pages
  api/static/style.css    styling
"""

import json
import os
import secrets
from datetime import datetime, timezone

import requests
from flask import Flask, redirect, render_template, request, session, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(16)

# ---------------------------------------------------------------------------
# Accounts  -  taken from the roster screenshot. Edit this list to add /
# remove accounts, or set an ACCOUNTS_JSON env var with the same shape.
# No credentials are stored here on purpose - the pilots already have them.
# ---------------------------------------------------------------------------
ACCOUNTS = [
    {"id": "fb-broly",     "server": "FB", "name": "[DBZ]-Broly"},
    {"id": "fb-android21", "server": "FB", "name": "[DBZ]-Android21"},
    {"id": "fb-videl",     "server": "FB", "name": "[DBZ]-Videl"},
    {"id": "wi-android17", "server": "WI", "name": "[DBZ]-Android17"},
    {"id": "dm-dabura",    "server": "DM", "name": "[DBZ]-Dabura"},
]

_env_accounts = os.environ.get("ACCOUNTS_JSON", "").strip()
if _env_accounts:
    try:
        ACCOUNTS = json.loads(_env_accounts)
    except ValueError:
        pass

ACCOUNTS_BY_ID = {a["id"]: a for a in ACCOUNTS}

WAR_TIMES = ["12 AM", "3 AM", "6 AM", "9 AM", "12 PM", "3 PM", "6 PM", "9 PM"]

SITE_PASSWORD = os.environ.get("SITE_PASSWORD", "").strip()
LOG_LIMIT = 100

try:
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo(os.environ.get("TIMEZONE", "UTC"))
except Exception:  # pragma: no cover - fallback when tz data is unavailable
    TZ = timezone.utc

# ---------------------------------------------------------------------------
# Storage (Vercel KV / Upstash Redis REST, with an in-memory fallback)
# ---------------------------------------------------------------------------
KV_URL = (
    os.environ.get("KV_REST_API_URL")
    or os.environ.get("UPSTASH_REDIS_REST_URL")
    or ""
).rstrip("/")
KV_TOKEN = (
    os.environ.get("KV_REST_API_TOKEN")
    or os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    or ""
)

_mem = {"statuses": {}, "pilot_log": []}


def _kv(*cmd):
    resp = requests.post(
        KV_URL,
        headers={"Authorization": f"Bearer {KV_TOKEN}"},
        json=list(cmd),
        timeout=5,
    )
    resp.raise_for_status()
    return resp.json().get("result")


def load_statuses():
    if KV_URL:
        raw = _kv("GET", "statuses")
        return json.loads(raw) if raw else {}
    return dict(_mem["statuses"])


def save_statuses(statuses):
    if KV_URL:
        _kv("SET", "statuses", json.dumps(statuses))
    else:
        _mem["statuses"] = statuses


def add_log(entry):
    line = json.dumps(entry)
    if KV_URL:
        _kv("LPUSH", "pilot_log", line)
        _kv("LTRIM", "pilot_log", 0, LOG_LIMIT - 1)
    else:
        _mem["pilot_log"].insert(0, line)
        del _mem["pilot_log"][LOG_LIMIT:]


def load_log():
    if KV_URL:
        rows = _kv("LRANGE", "pilot_log", 0, LOG_LIMIT - 1) or []
    else:
        rows = list(_mem["pilot_log"])
    out = []
    for r in rows:
        try:
            out.append(json.loads(r))
        except (TypeError, ValueError):
            pass
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def now_iso():
    return datetime.now(timezone.utc).isoformat()


def fmt(iso):
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).astimezone(TZ).strftime("%b %d, %H:%M")
    except (TypeError, ValueError):
        return ""


def human_dur(start_iso, end_iso):
    try:
        secs = int(
            (
                datetime.fromisoformat(end_iso) - datetime.fromisoformat(start_iso)
            ).total_seconds()
        )
    except (TypeError, ValueError):
        return ""
    secs = max(secs, 0)
    h, rem = divmod(secs, 3600)
    m, _ = divmod(rem, 60)
    return f"{h}h {m}m" if h else f"{m}m"


# ---------------------------------------------------------------------------
# Optional password gate (set SITE_PASSWORD to enable).
# The pilot log stays public even when the gate is on.
# ---------------------------------------------------------------------------
_PUBLIC_ENDPOINTS = {"login", "log", "static"}


@app.before_request
def _gate():
    if not SITE_PASSWORD:
        return None
    if request.endpoint in _PUBLIC_ENDPOINTS:
        return None
    if session.get("ok"):
        return None
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if not SITE_PASSWORD:
        return redirect(url_for("index"))
    error = ""
    if request.method == "POST":
        if request.form.get("password") == SITE_PASSWORD:
            session["ok"] = True
            session.permanent = True
            return redirect(url_for("index"))
        error = "Wrong password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login") if SITE_PASSWORD else url_for("index"))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    statuses = load_statuses()
    rows = []
    for a in ACCOUNTS:
        st = statuses.get(a["id"], {})
        rows.append(
            {
                **a,
                "active": bool(st.get("active")),
                "pilot": st.get("pilot", ""),
                "war_time": st.get("war_time", ""),
                "notes": st.get("notes", ""),
                "since_fmt": fmt(st.get("since", "")),
            }
        )
    log_rows = [dict(e, when=fmt(e.get("timestamp"))) for e in load_log()]
    return render_template(
        "board.html",
        rows=rows,
        log=log_rows,
        war_times=WAR_TIMES,
        active_count=sum(1 for r in rows if r["active"]),
        total=len(rows),
        gated=bool(SITE_PASSWORD),
    )


@app.route("/log")
def log():
    entries = [dict(e, when=fmt(e.get("timestamp"))) for e in load_log()]
    return render_template("log.html", log=entries)


@app.route("/start", methods=["POST"])
def start():
    aid = request.form.get("account_id", "")
    pilot = request.form.get("pilot", "").strip()
    war_time = request.form.get("war_time", "").strip()
    notes = request.form.get("notes", "").strip()[:200]
    acc = ACCOUNTS_BY_ID.get(aid)
    if not acc or not pilot:
        return redirect(url_for("index"))

    statuses = load_statuses()
    statuses[aid] = {
        "active": True,
        "pilot": pilot,
        "war_time": war_time,
        "notes": notes,
        "since": now_iso(),
    }
    save_statuses(statuses)
    add_log(
        {
            "timestamp": now_iso(),
            "account_id": aid,
            "account_name": acc["name"],
            "server": acc["server"],
            "pilot": pilot,
            "war_time": war_time,
            "notes": notes,
            "action": "started",
            "duration": "",
        }
    )
    return redirect(url_for("index"))


@app.route("/stop", methods=["POST"])
def stop():
    aid = request.form.get("account_id", "")
    acc = ACCOUNTS_BY_ID.get(aid)
    if not acc:
        return redirect(url_for("index"))

    statuses = load_statuses()
    st = statuses.get(aid, {})
    add_log(
        {
            "timestamp": now_iso(),
            "account_id": aid,
            "account_name": acc["name"],
            "server": acc["server"],
            "pilot": st.get("pilot", ""),
            "war_time": st.get("war_time", ""),
            "notes": st.get("notes", ""),
            "action": "logged off",
            "duration": human_dur(st.get("since", ""), now_iso()),
        }
    )
    statuses[aid] = {"active": False, "pilot": "", "war_time": "", "notes": "", "since": ""}
    save_statuses(statuses)
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# On Vercel the catch-all rewrite in vercel.json hands this function the
# destination path ("/api/index") instead of the URL the visitor asked for.
# Strip that prefix so Flask still routes "/", "/log", "/start", etc.
# ---------------------------------------------------------------------------
_VERCEL_PREFIXES = ("/api/index.py", "/api/index")


class _NormalizePath:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "") or ""
        for pref in _VERCEL_PREFIXES:
            if path == pref:
                environ["PATH_INFO"] = "/"
                break
            if path.startswith(pref + "/"):
                environ["PATH_INFO"] = path[len(pref):]
                break
        return self.wsgi_app(environ, start_response)


app.wsgi_app = _NormalizePath(app.wsgi_app)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
