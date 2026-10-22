# AskDB: local deployment runbook

Follow the steps in order. Each step gives the command to run and what you should see. Run every command from the repository root unless a step says otherwise.

You will run two processes in two terminals:

| Terminal | Process | Address |
|---|---|---|
| A | API server (FastAPI) | http://127.0.0.1:8000 |
| B | Web UI (React dev server) | http://localhost:5173 |

Do not expose these ports beyond this laptop.

---

## Step 1. Open the repository

```sh
cd /Users/manaranjanp/Documents/Work/Consulting/Intuit/Claude/project/askdb
```

Check that you are in the right place:

```sh
ls pyproject.toml web/package.json config/settings.yaml
```

Expected: all three paths are listed with no error.

---

## Step 2. Check the dependencies

Run each command. Each must print a version at or above the minimum.

| Tool | Command | Minimum |
|---|---|---|
| uv (manages Python) | `uv --version` | any recent version |
| Node.js | `node --version` | v18 |
| npm | `npm --version` | any |

If uv is missing, install it with `brew install uv`, or use the installer at https://docs.astral.sh/uv/. If Node is missing, install Node 18 or newer from https://nodejs.org.

uv installs Python 3.10 or newer for you on the first `uv sync`. You do not need to install Python yourself.

---

## Step 3. Install the Python packages

```sh
uv sync
```

Expected: the last lines read `Installed N packages` or `Audited N packages`, with no error.

## Step 4. Install the web packages

```sh
cd web
npm install
cd ..
```

Expected: npm finishes with `added N packages`. A warning about a newer npm is harmless.

## Step 5. Check that the build works

```sh
uv run pytest -q
cd web && npm run build && cd ..
```

Expected:
- pytest ends with `154 passed, 3 skipped` (or a higher pass count). The 3 skipped tests need an API key, so skipping them is correct.
- The build ends with `✓ built in` and no errors.

If pytest fails, stop here and fix the failure before continuing.

---

## Step 6. Set the environment variables

Set these in **terminal A**. Replace the placeholder values.

```sh
export ANTHROPIC_API_KEY="sk-ant-REPLACE_WITH_YOUR_KEY"
export ANTHROPIC_WORKSPACE_ID="wrkspc_REPLACE_WITH_YOUR_WORKSPACE_ID"   # only if your key is not scoped to a workspace
export ASKDB_CONFIG_DIR="$PWD/config"
```

Only if you use the sample database (Step 7), also set:

```sh
export CLOUDMETRICS_DB_PATH="$PWD/tests/cloudmetrics/cloudmetrics.db"
```

Rules for these variables:
- `ANTHROPIC_WORKSPACE_ID` is optional. Set it when Anthropic reports that the key is not scoped to a workspace. Leave it unset for a workspace-scoped key.
- `ANTHROPIC_API_KEY` is required to answer questions. Without it the app starts, but every question shows a configuration message. Never put the key in a file in this repository.
- The app does not read a `.env` file. Set the variables in every terminal that runs the API, before starting it.
- To keep the key out of your shell history, put the two `export` lines in a file outside the repository (for example `~/askdb_env.sh`), then run `source ~/askdb_env.sh` in terminal A.

Check:

```sh
echo "$ASKDB_CONFIG_DIR"
```

Expected: the full path to `config`, ending in `/config`.

---

## Step 7. Add a database (optional here)

You can add a database in the browser later (Step 13), which is the usual way. To start with the sample database, copy its config into place:

```sh
mkdir -p config/databases
cp tests/cloudmetrics/cloudmetrics.yaml config/databases/
```

Expected: `config/databases/cloudmetrics.yaml` exists. The sample needs `CLOUDMETRICS_DB_PATH` from Step 6.

---

## Step 8. Create the first support account

```sh
uv run python -m askdb.cli create-user --username your.name --role support
```

You will be asked for a password twice. It must be at least 8 characters.

Expected: `Created support account your.name.`

Notes:
- This is the only way to create the first account. Later accounts are created from the Admin screen.
- Use `--role analyst` for an analyst account.
- Run it once for each account. Running it again with the same name fails with "already exists".

---

## Step 9. Start the API server (terminal A)

Make sure terminal A has the variables from Step 6 and that you are in the repository root.

```sh
uv run uvicorn askdb.main:app --host 127.0.0.1 --port 8000
```

Expected output, ending with:

```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

Leave this terminal running. Startup logs appear here. A database whose startup checks fail is logged here as `database <name> disabled: ...`.

The first start creates `data/app.db`.

---

## Step 10. Start the web UI (terminal B)

Open a **second** terminal and go to the repository:

```sh
cd /Users/manaranjanp/Documents/Work/Consulting/Intuit/Claude/project/askdb/web
npm run dev
```

Expected output, ending with:

```
  VITE v5.x.x  ready in ... ms
  ➜  Local:   http://localhost:5173/
```

Leave this terminal running. Terminal B does not need the API variables.

---

## Step 11. Check that both processes respond

In a third terminal, run:

```sh
curl -s -o /dev/null -w "API without sign-in: %{http_code}\n" http://127.0.0.1:8000/api/databases
curl -s -o /dev/null -w "UI: %{http_code}\n" http://localhost:5173/
```

Expected:
- `API without sign-in: 401`. The API is up and requires a sign-in.
- `UI: 200`.

Any other result: see Troubleshooting below.

---

## Step 12. Sign in and check the first question

1. Open http://localhost:5173 in a browser.
2. Sign in with the support account from Step 8.
3. In the sidebar, choose the database from the **Database** selector. If it is empty, do Step 13 first.
4. Ask: `How many active customers?`

Expected: an explanation, a table, and a **Show query** button under the answer.

---

## Step 13. Add a database from the browser

Do this if you did not copy the sample in Step 7, or to add your own database.

1. As the support user, click **Admin** (top bar), then the **Databases** tab, then **Add database**.
2. Enter the **Database file path**. For the sample, use the full path to `tests/cloudmetrics/cloudmetrics.db`, or `${CLOUDMETRICS_DB_PATH}`.
3. Paste the schema YAML into the text box, or choose a `.yaml` file. For the sample, use `tests/cloudmetrics/cloudmetrics.yaml`.
4. Click **Validate**. Expected: "The configuration is valid. Nothing has been saved."
5. Click **Save**. Expected: "Saved cloudmetrics. It is available to analysts now."

The database appears in the selector at once. No restart is needed.

If Validate or Save shows errors, nothing was written. Fix each listed error and try again.

---

## Step 14. Check that analysts can use it

1. Click **Sign out**, then sign in as an analyst. Create the analyst first in **Admin → Users** if you have not already.
2. Choose the database and ask a question.

Expected: the same kind of answer as Step 12.

---

## Stopping the app

1. In terminal B, press `Ctrl+C`.
2. In terminal A, press `Ctrl+C`.

Expected: both processes stop. Your data stays in `data/app.db` and `config/`.

## Starting it again later

Repeat Steps 1, 6, 9 and 10. Steps 2 to 5 and 8 are needed only once, or after an update.

---

## Backups

Stop the API (terminal A, `Ctrl+C`), then run:

```sh
mkdir -p backups/$(date +%Y%m%d)
cp data/app.db backups/$(date +%Y%m%d)/
cp -R config backups/$(date +%Y%m%d)/
```

Expected: the folder `backups/<today>/` holds `app.db` and `config/`. Restart the API afterwards.

`data/app.db` holds accounts, conversations, and the audit log with result rows, so keep backups on an encrypted disk. The audit log is purged after 30 days.

## Updating

Stop both processes, then:

```sh
git pull
uv sync
cd web && npm install && cd ..
uv run pytest -q
```

Expected: pytest passes. Then start again from Step 9. The app creates new tables at startup. It has no migrations, so if a release changes an existing table, back up `data/app.db` first.

---

## Troubleshooting

| What you see | Cause | Fix |
|---|---|---|
| `uv: command not found` | uv not installed | Step 2 |
| `npm: command not found` or `npm run dev` fails at once | Node not installed, or you are not in `web/` | Step 2, and `cd web` first |
| `Address already in use` on port 8000 or 5173 | Another process is using the port | Stop it, or pick another port. For the API, change the `proxy` target in `web/vite.config.ts` to match |
| UI shows "Could not load databases: HTTP 401" | Not signed in, or the session expired (12 hours) | Sign in again |
| "Invalid username or password" | Wrong credentials | Ask a support user to reset the password in **Admin → Users** |
| A question says "The AI service is not configured: ANTHROPIC_API_KEY is not set" | Key not exported in terminal A | Run Step 6 in terminal A, then restart Step 9 |
| A question says "The AI service did not respond" | Network or API outage | Check your connection and try again |
| A database is missing from the selector | Its checks failed at startup, or it was never saved | **Admin → Databases** shows the errors. Fix them, then use **Re-check** or save again |
| "environment variable X is not set" on a database | Its path uses `${X}` and the variable is not set in terminal A | Export it in terminal A and restart Step 9 |
| Browser shows a blank page | UI not started, or the API is down | Check terminal B shows `ready`, then run Step 11 |

Logs appear in the terminal running each process.
