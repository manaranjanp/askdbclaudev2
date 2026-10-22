# Local deployment guide

This guide runs AskDB on one laptop for a small team (SPEC §1, §20). It covers installing, configuring, starting, creating the first support account, connecting a database, and backing up.

## What runs

| Process | Command | Port | Purpose |
|---|---|---|---|
| API | `uv run uvicorn askdb.main:app` | 8000 | FastAPI backend. Reads config, runs queries, calls Claude. |
| Web | `npm run dev` in `web/` | 5173 | React UI. Forwards `/api` requests to port 8000. |

Both processes must run at the same time, from the repository root (the API) and from `web/` (the UI).

> **Limitation.** The backend does not serve the built UI, and `npm run preview` does not forward `/api`. Until a production static-serving step is added, use `npm run dev` for the UI. Do not expose these ports beyond the laptop.

## 1. Prerequisites

- macOS or Linux with a terminal.
- Python 3.10 or newer, managed by [uv](https://docs.astral.sh/uv/) (`brew install uv`, or the installer on the uv site).
- Node.js 18 or newer and npm.
- An Anthropic API key, with access to `claude-sonnet-5-5`.
- A copy of the data you want to query, as a SQLite file.

## 2. Install

From the repository root:

```sh
uv sync
cd web && npm install && cd ..
```

Check the install:

```sh
uv run pytest -q          # expect all tests to pass; 3 are skipped without an API key
cd web && npm run build && cd ..
```

## 3. Configure

### 3.1 Environment variables

The app reads secrets only from environment variables (SPEC §16). It does not load a `.env` file, so export the variables in each terminal that starts the API:

```sh
export ANTHROPIC_API_KEY="sk-ant-..."   # your key; never put it in a YAML file or in git
export ASKDB_CONFIG_DIR="$PWD/config"   # optional; this is the default when started from the repo root
```

To keep the key out of shell history, put the `export` line in a file outside the repository, such as `~/.askdb_env`, and run `source ~/.askdb_env` before starting the API.

### 3.2 App settings

`config/settings.yaml` holds the app settings. It ships with working defaults:

```yaml
app_db_path: data/app.db          # accounts, conversations, audit log (created on first start)
llm:
  sql_model: claude-sonnet-5-5
  explain_model: claude-sonnet-5-5
  api_key_env: ANTHROPIC_API_KEY  # the variable name, not the key
limits:
  display_rows: 500
  explain_token_budget: 4000
  query_timeout_seconds: 60
  audit_retention_days: 30
```

`app_db_path` is relative to the directory the API starts in, so start the API from the repository root. Changes to this file take effect on restart.

### 3.3 Adding databases

The normal way is the admin screen (SPEC §16.4). Sign in as support, open **Admin**, then **Databases**, then **Add database**:

1. Enter the database file path. It is read by the server, so it must be a path the server process can open, such as `/Users/you/data/sales.db`. An environment variable is written `${NAME}`, and the variable must be set in the terminal that starts the API.
2. Paste the schema YAML, or choose a `.yaml` file. Use the format of `tests/cloudmetrics/cloudmetrics.yaml`. The schema's `name` is the database's identity and cannot change later.
3. Click **Validate** to check without saving. **Save** runs the same checks and refuses the save, with the list of errors, if any check fails. Nothing is written on a refusal.

A saved database appears in the analysts' selector at once, with no restart. **Edit** changes the path or schema, **Re-check** runs the checks again on the saved file (useful after moving or repairing a database file), and **Remove** deletes the database. Existing conversations stay readable, but new questions to a removed database fail.

Each saved database is a YAML file in `config/databases/`, written in canonical form. Comments are not kept in files the admin screen writes.

You can still place YAML files in `config/databases/` by hand. They load at startup, and a file that fails its checks is disabled, with its errors shown under **Databases**.

The sample database, by hand:

```sh
mkdir -p config/databases
cp tests/cloudmetrics/cloudmetrics.yaml config/databases/
export CLOUDMETRICS_DB_PATH="$PWD/tests/cloudmetrics/cloudmetrics.db"
```

The app opens every database read-only, so the database file is never changed. Support chooses which files are configured, since the server can open any SQLite file it can read (SPEC §13).

## 4. Start

Terminal 1, from the repository root (the API):

```sh
uv run uvicorn askdb.main:app --host 127.0.0.1 --port 8000
```

Terminal 2 (the UI):

```sh
cd web && npm run dev
```

Open http://localhost:5173.

Check the API directly, without the UI:

```sh
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/databases   # expect 401 before sign-in
```

On the first start the app creates `data/app.db` and its tables.

## 5. Create the first support account

There are no accounts until you create one. Use the command line, which asks for the password twice (SPEC §12):

```sh
uv run python -m askdb.cli create-user --username your.name --role support
```

Use `--role analyst` for analyst accounts. Once signed in, a support user creates other accounts and resets passwords from the **Admin** screen. Account creation is admin-only; there is no self-registration.

## 6. First-use check

1. Open http://localhost:5173 and sign in.
2. Choose the database in the sidebar.
3. Ask: "How many active customers?" for the sample database. You should see an explanation, the SQL under **Show query**, and a table.
4. Sign out, and sign back in. The conversation is still listed.
5. As support, open **Admin**: the database appears under **Database status**, and the question appears in the **Audit log**.

For the full error-state walkthrough, see `docs/manual-checklist.md`.

## 7. Backups

Everything the app stores is in two places:

- `data/app.db`: accounts, sessions, conversations, and the audit log (which includes result rows). Treat it as sensitive.
- `config/` and the database files you configured: these are the source of your settings and data.

To back up while the API is stopped:

```sh
mkdir -p backups/$(date +%Y%m%d)
cp data/app.db backups/$(date +%Y%m%d)/
cp -R config backups/$(date +%Y%m%d)/
```

Keep backups on an encrypted disk. The audit log is purged after 30 days (SPEC §10), so older entries are not in later backups.

## 8. Updating

```sh
git pull
uv sync
cd web && npm install && cd ..
uv run pytest -q
```

Restart the API after pulling. The app creates missing tables at startup, but it has no migrations: if a release changes an existing table, back up `data/app.db` first and read the release notes.

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| UI shows "Could not load databases: HTTP 401" | Not signed in, or the session expired (12 hours) | Sign in again |
| Sign-in fails with "Invalid username or password" | Wrong credentials | Ask support to reset the password |
| A database is missing from the selector | Its startup check failed | Open **Admin → Database status** and read the errors; fix the file or the YAML and restart |
| "environment variable X is not set" in the database status | A `${NAME}` path has no value | Export the variable and restart the API |
| "The AI service is not configured: ANTHROPIC_API_KEY is not set" | Key not exported in the API's terminal | Export the key and restart the API |
| "The AI service did not respond" | Network or API outage | Check connectivity; the app already retried once |
| UI loads but questions fail with a network error | API not running on port 8000 | Start the API in terminal 1 |
| Port 8000 in use | Another process | Use `--port 8001` and change the `proxy` target in `web/vite.config.ts` to match |

Logs are written to the terminal running the API. Database startup failures are logged at error level there. Routine audit-retention runs are logged at info level, which the API does not display by default.
