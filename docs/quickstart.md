# Quickstart

Get from a fresh clone to an admin logged into the AgentLabX browser shell in about five minutes. This walkthrough exercises Stage A1: **auth, credentials, sessions, admin, audit log**. No LLM keys are needed — research stages arrive in Layer B.

## Prerequisites

- **Python 3.12+** with [`uv`](https://docs.astral.sh/uv/) on your `PATH` (`uv --version`)
- **Node.js 20+** and **npm 10+** (`node --version`)
- A recent git checkout of this repo

## 1. Install Python + frontend dependencies

```bash
git clone https://github.com/whats2000/AgentLabX.git
cd AgentLabX
uv sync --extra dev
(cd web && npm install)
```

`uv sync --extra dev` creates `.venv/`, installs the `agentlabx` package in editable mode, and pulls dev deps (pytest, ruff, mypy, httpx). `npm install` pulls the React shell's deps. First-time install takes 1–2 minutes total.

## 2. Bootstrap the Owner identity

The first user registered on an install becomes the **Owner** — an immutable admin that no one else can delete or demote. Create this Owner from the CLI so the server has someone to log in as on first boot:

```bash
uv run agentlabx bootstrap-admin --display-name "Alice" --email alice@example.com
# prompts for a passphrase, twice
# → Registered identity id=<uuid> (admin)
```

This creates the SQLite DB at `~/.agentlabx/agentlabx.db`, records the schema version, and stores an argon2-hashed passphrase. The Fernet master key is generated and stored in your OS keyring (Windows Credential Manager, macOS Keychain, or Secret Service).

> You can also register the first user via the browser on a fresh install — `bootstrap-admin` is just the non-interactive path.

## 3. Start the backend

```bash
uv run agentlabx serve --bind loopback --port 8765
```

The server binds `http://127.0.0.1:8765`. Leave it running. On LAN bind (`--bind lan`) you must also pass `--tls-cert` and `--tls-key` — loopback bind is TLS-free.

Visit **http://127.0.0.1:8765/api/health** to sanity-check — you should see `{"status": "ok"}`.

## 4. Start the Vite dev server

In a second terminal:

```bash
cd web
npm run dev
# → open http://127.0.0.1:5173
```

Vite proxies `/api` to the backend on `:8765`, so the UI talks to your running server out of the box.

## 5. Log in

Visit **http://127.0.0.1:5173**. Because the install already has a user (the one `bootstrap-admin` created), the login page defaults to **Log in** mode.

- **Email:** `alice@example.com`
- **Passphrase:** whatever you typed at the CLI prompt

You should land on `/runs` (empty placeholder — Layer B will populate this with actual runs later). From here:

- **Sidebar top-left:** *AgentLabX* branding + flask icon.
- **Primary nav:** Runs / Admin Users / Activity (admin-gated).
- **Sidebar bottom:** your avatar + name + email → click to open a popover with Profile, Credentials, and Log out.

## 6. Try the A1 surface

**Profile** (`/profile`):

- Change your display name (no passphrase needed).
- Rename your email (requires current passphrase — cannot collide with another user).
- Rotate your passphrase (requires old + new + confirm; all sessions + tokens revoke on success).
- **Personal API tokens:** issue one, copy the plaintext from the amber reveal banner (shown **once**), then use it:

  ```bash
  curl -H "Authorization: Bearer ax_..." http://127.0.0.1:8765/api/auth/me
  ```
- **Active sessions:** see every device you're logged in from; revoke individually. Revoking your current session logs you out immediately.

**Credentials** (`/settings`):

- Add an encrypted slot (e.g. `anthropic` → `sk-ant-test-1`). Value is Fernet-encrypted at rest; only the OS keyring holds the master key.
- Click **Reveal** to see the decrypted value on demand. **Delete** wipes the slot with a confirm dialog.
- The stored value is scoped to your identity — a second user on the same install cannot see or access it.

**Admin Users** (admin-only, `/admin`):

- Create a second user: display name + email + initial passphrase. The second user lands as a non-admin non-owner.
- Grant them `admin` — they can now see the Admin Users + Activity panels.
- Try to revoke the **Owner**'s admin → 400 *"cannot revoke admin from the owner"*.
- Try to delete the Owner → 400 *"cannot delete the owner identity"*.
- Delete the second user (confirm dialog) — cascades clean up their configs / tokens / sessions automatically via SQLite FK `ON DELETE CASCADE`.

**Audit log** (admin-only, `/admin/activity`):

- Every register / login / logout / profile update / admin action / credential CRUD emits a structured event. Newest 200 rows shown by default (selectable up to 1000).
- **Clear log** archives the current `audit.jsonl` to `audit.<timestamp>.cleared.jsonl` under `~/.agentlabx/events/` — the history is preserved on disk, only hidden from the UI. The clearing action itself is recorded as the first row of the new log.

## 7. Simulate forgotten passphrase

Stop the backend (`Ctrl+C`), then:

```bash
uv run agentlabx reset-passphrase --email alice@example.com
# prompts for new passphrase, twice
# → Passphrase reset for alice@example.com (id=<uuid>); all sessions and tokens revoked.
```

Restart the server and log in with the new passphrase. This CLI flow is the escape hatch for the Owner specifically — since no other admin can reset them.

## Reset everything

To start from an empty state:

```bash
rm -rf ~/.agentlabx
# the Fernet master key stays in your OS keyring; delete it too:
# Windows: search "Credential Manager" → delete entries under "agentlabx"
# macOS:   Keychain Access → search "agentlabx" → delete
# Linux:   secret-tool clear service agentlabx
```

Next `bootstrap-admin` call writes a fresh DB + generates a fresh master key.

## Verify gates locally

```bash
# Python: 91 tests + strict typing
uv run pytest -v
uv run ruff check agentlabx tests
uv run mypy agentlabx tests

# TypeScript: strict + production build
(cd web && npm run lint && npm run build)
```

All five commands should exit 0. See [`README.md`](../README.md) for the full tech-stack breakdown.

## Troubleshooting

**Port 8765 is already in use.** Either stop the other service, or pass `--port 8766` to `agentlabx serve` (and the Vite proxy in `web/vite.config.ts` will need matching adjustment).

**"database schema_version=X is newer than code..."** You ran a newer version of the app, then downgraded. In-place forward migrations work (v1→v2→v3), but downgrades don't. Either upgrade back or delete the DB.

**"cannot decrypt" after deleting `~/.agentlabx` but not the keyring.** The DB was wiped but the old Fernet master key remained. Delete the `agentlabx/master_key` entry from your OS keyring and bootstrap-admin again.

**Login keeps showing "too many failed attempts".** The per-email rate limiter locks you out for 15 minutes after 5 failures in 5 minutes. Wait, or restart the server (the counter is process-local and resets).

**`(cd web && npm install)` fails on a peer-dep conflict.** React 19 + shadcn/ui combinations can occasionally clash. Try `npm install --legacy-peer-deps`.

## Where to look next

- 🎯 [**Vision**](superpowers/specs/2026-04-15-agentlabx-vision.md) — north-star principles
- 📐 [**SRS**](superpowers/specs/2026-04-15-agentlabx-srs.md) — full system requirements, architecture, build roadmap (Layer A / B / C)
- 📋 [**Stage A1 plan**](superpowers/plans/2026-04-15-stageA1-foundation-infrastructure.md) — the 29-task implementation plan that delivered A1
- 🧪 [**Backend tests**](../tests/) — 91 tests (75 unit, 16 integration)
- 🧵 **API docs** — live at `http://127.0.0.1:8765/docs` when the server is running (FastAPI auto-generated)
