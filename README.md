# DBZ Pilot Board

A one-page board for sharing / "piloting" a set of Cabal accounts.

Per account:
- **Status bar** – green = someone is piloting it now, grey = free.
- **Pilot name** text box + **WAR TIME** dropdown (12 / 3 / 6 / 9 AM/PM).
- **Notes** box – e.g. "I will keep this account until the 6PM war" even if 3PM is picked as war time.
- **Start piloting** to take it, **Log off** to release it when you finish.

**Pilot log** – shown at the bottom of the board and on its own page at `/log`.
It lists every start / log-off with time, pilot, war time, notes and session
length. The log is **always public** (even if the site password is set) so the
owner can check who last used an account if something goes missing.

No account credentials are stored anywhere in this app – the pilots already
have them.

## Files

```
api/index.py              app logic (Flask)
api/templates/board.html   the board page
api/templates/log.html     the standalone log page
api/templates/login.html   optional password page
api/templates/_logtable.html   shared log table
api/static/style.css       styling
api/static/board.js        auto-refresh
vercel.json
requirements.txt
```

## Deploy to Vercel

1. Push this folder to a Git repo.
2. In Vercel, **Add New… → Project** and import the repo. No build settings needed.
3. Add persistent storage so status + log survive restarts:
   - Vercel dashboard → **Storage** → create a **KV** (Upstash Redis) store → **Connect** it to this project.
   - That auto-adds `KV_REST_API_URL` and `KV_REST_API_TOKEN`, which the app uses automatically.
4. **Redeploy.**

Without a KV store the app still works, but state resets on every cold start.

## Optional environment variables

| Variable | Purpose |
|---|---|
| `SITE_PASSWORD` | If set, the board asks for this password. The `/log` page stays public. |
| `SECRET_KEY` | Random string for signing the login cookie (set one if you use `SITE_PASSWORD`). |
| `TIMEZONE` | e.g. `Asia/Manila`. Timestamps in the log use this. Default `UTC`. |
| `ACCOUNTS_JSON` | Full accounts list as JSON, if you would rather not edit the file. |

## Edit the account list

Change the `ACCOUNTS` list near the top of `api/index.py` (or set `ACCOUNTS_JSON`). Each entry:

```python
{"id": "unique-slug", "server": "FB", "name": "[DBZ]-Broly"}
```

## Run locally

```bash
pip install -r requirements.txt
python api/index.py      # http://127.0.0.1:5000
```
