# AskDB

Ask questions of a SQLite database in plain English. See `docs/SPEC.md` for behavior.

## Setup

Requires Python 3.10+, [uv](https://docs.astral.sh/uv/), and Node.js 18+.

```sh
uv sync
cd web && npm install
```

## Configuration

Config is read at startup from `ASKDB_CONFIG_DIR` (default `config/`):

- `config/databases/*.yaml`: one file per database (format in `docs/SPEC.md` §16.1).
- `config/settings.yaml`: optional app settings (SPEC §16.2). Missing means defaults.

Database paths may reference environment variables with `${NAME}`. The sample
`tests/cloudmetrics/cloudmetrics.yaml` uses `${CLOUDMETRICS_DB_PATH}`:

```sh
export CLOUDMETRICS_DB_PATH=/absolute/path/to/tests/cloudmetrics/cloudmetrics.db
mkdir -p config/databases
cp tests/cloudmetrics/cloudmetrics.yaml config/databases/
```

A database that fails its startup checks is disabled and logged. The others still load.

## Run

```sh
uv run uvicorn askdb.main:app --reload    # API on http://127.0.0.1:8000
cd web && npm run dev                     # UI on http://localhost:5173
```

## Test

```sh
uv run pytest
```
