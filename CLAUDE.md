# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

The repository contains requirements and test fixtures only. There is no application code, package manifest, build, lint, or test tooling yet. Do not assume commands exist; check for them before running anything.

- `docs/one-pager.md`: requirements. Amended during the interview (PII rule removed for v1; SQLite-only wording).
- `docs/SPEC.md`: the v1 specification. Section 22 is the decisions log. Treat it as the source of truth where the one-pager differs.
- `tests/cloudmetrics/`: sample fixtures (`cloudmetrics.db`, `cloudmetrics.yaml`, `cloudmetrics_eval.yaml`). Do not modify these without asking; they were supplied by the user.

## Commands

No build, lint, or test commands exist yet. The SPEC names one planned command: `uv run pytest tests/validation` (on-demand evaluation harness, Section 17.4). It requires a `pyproject.toml` and a `tests/validation/` package that have not been created. The eval file header refers to `config/databases/` and `config/validation/` paths that also do not exist yet.

Inspect the fixtures with `sqlite3 tests/cloudmetrics/cloudmetrics.db` (read-only use only).

## Planned architecture (from SPEC.md)

Python + FastAPI backend, React frontend, Anthropic Claude API for SQL generation and explanation. Read `docs/SPEC.md` before designing any module, since most of the behavior is cross-cutting.

The request path is the main thing to understand:

1. A question arrives in a conversation bound to one database (switching databases starts a new conversation).
2. The prompt is built from the database's `description` verbatim, all `tables` rendered as `CREATE TABLE` DDL with column descriptions as comments, the dialect, today's date, and the conversation's prior questions, SQL, and explanations (SPEC §5, §6).
3. The model returns SQL plus an ambiguity flag and assumptions. An ambiguous question stops here and asks the user in chat; no SQL runs.
4. SQL passes a three-layer read-only check (SPEC §8): the SQLite file opens `mode=ro` with `PRAGMA query_only`, a parser allows exactly one `SELECT`, and each query runs in a transaction that is always rolled back. Also 60s timeout and a 500-row display cap.
5. On a database error, the error goes back to the model once for repair.
6. The explanation step gets rows up to a token budget. Results with text values get a second Claude call that checks the explanation for injection or out-of-scope content (SPEC §14). A failed check shows the table with a notice instead of the explanation.
7. Every answer is written to the audit log in the app DB, including result rows, kept 30 days and readable only by support (SPEC §10).

Two separate SQLite databases: the configured data DB (read-only) and the app DB (accounts, conversations, messages, audit log).

## Configuration model

Config is YAML and is data, not code. Two kinds of file, both loaded at startup:

- One file per database (format in SPEC §16.1; example in `tests/cloudmetrics/cloudmetrics.yaml`). Schema descriptions and business rules live in its `description` field and are the only place metric definitions should go. The app is database-agnostic: nothing in app code may depend on the cloudmetrics names or data.
- App settings (SPEC §16.2): model names, row cap, timeout, token budget, audit retention.

Secrets are never in YAML. The config references environment variable names instead. Startup checks disable a database that fails validation without stopping the others (SPEC §16.3).

## Evaluation set

`tests/cloudmetrics/cloudmetrics_eval.yaml` defines the format (SPEC §17.2). Each case is either an `expected_sql` whose result set must match the generated SQL's result set, or an `expected_outcome` of `clarification` or `declined` that must produce that outcome with no SQL run. The pass bar is 90%, and silent wrong answers fail regardless of rate. The eval file is never loaded at app startup or sent to the model.
