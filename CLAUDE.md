# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

The repository has requirements, a plan, and test fixtures only. There is no application code, package manifest, or build, lint, or test tooling yet. Check that a command exists before running it.

- `docs/SPEC.md` is the source of truth for v1 behavior. Its decisions log takes precedence over `docs/one-pager.md`. Read it before designing any module.
- `docs/PLAN.md` is the slice-by-slice implementation checklist. Build in slice order.
- `tests/cloudmetrics/` holds user-supplied fixtures (`cloudmetrics.db`, `cloudmetrics.yaml`, `cloudmetrics_eval.yaml`). Do not modify them without asking.

## Commands

- Inspect the fixture database read-only: `sqlite3 tests/cloudmetrics/cloudmetrics.db`
- Planned, not yet runnable (needs `pyproject.toml` and `tests/validation/`): `uv run pytest tests/validation`

## Architecture

Python + FastAPI backend, React frontend, Anthropic Claude API for SQL generation and explanation. Two SQLite databases: the configured data database (read-only) and the app database (accounts, conversations, messages, audit log).

## Rules that are easy to break

- The app is database-agnostic. Nothing in app code may depend on the cloudmetrics names or data.
- Metric definitions and business rules belong only in a database config's `description` field.
- Secrets never go in YAML. Config names environment variables instead.
- The eval file is never loaded at app startup or sent to the model.
- Every SQL path must go through the read-only layers. Do not add a bypass.
