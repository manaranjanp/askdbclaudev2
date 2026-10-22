# Natural-Language Database Query App: v1 Specification

Source: [docs/one-pager.md](docs/one-pager.md). Where this spec and the one-pager differ, the decisions recorded here were made during the requirements interview and the one-pager has been amended to match.

## 1. Summary

A local web app where business analysts ask questions of a SQLite database in plain English. The app generates SQL with Claude, runs it read-only, and returns a plain-English explanation plus a table of results. Users never need to see or write SQL, though they can view it.

v1 targets fewer than 10 users on a single laptop.

## 2. Goals and Non-Goals

**Goals**
- Answer totals/trends, rankings/top-N, filtered record lists, and segment comparisons.
- Never change data. Never give a wrong answer silently.
- Keep a private, long-lived history of each user's conversations.
- Be configured per database through YAML that support maintains, either as files or in the admin screen.

**Non-goals (v1)**
- Multi-database questions, scheduled reports, alerts, write-back, forecasting.
- Role-based or regional access control.
- Personal-data masking or blocking (see Section 13).
- Searching history.
- Engines other than SQLite.
- Rate limits and LLM spend caps.

## 3. Users

- **Primary:** business analysts. Comfortable with numbers, no SQL.
- **Secondary:** support staff. Manage database configuration, create accounts, reset passwords, and review the audit log.

## 4. Architecture

| Layer | Choice |
|---|---|
| Backend | Python, FastAPI |
| Frontend | React |
| LLM | Anthropic Claude API, model `claude-sonnet-5-5` (set in app settings, Section 16.2; separate models for SQL generation and explanation) |
| Data DB | SQLite, path set in the database YAML config |
| App DB | SQLite, holds accounts, conversations, messages, and audit log |
| Config | YAML: one file per database, managed from the admin screen or as files; one app settings file loaded at startup |
| Secrets | Referenced by environment-variable name in YAML, never stored in the file |
| Hosting | Single process on a local laptop |

### 4.1 Database adapter
v1 is SQLite-only. Code that touches the database goes through a thin adapter (connect, introspect, execute, dialect hints) with one SQLite implementation. The interface exists so a second engine can be added later, but no other engine is built or tested in v1. The SQL generator's prompt includes the dialect name from the adapter.

## 5. Interaction Model

- Chat-style conversation. The user selects one database before asking questions. Each question runs against that one database.
- Switching databases starts a new conversation.
- **Follow-up context:** the model receives the prior user questions, the SQL generated for them, and the plain-English explanations, for the current conversation only. It does not receive prior result rows, so follow-ups can edit a previous query ("now filter that by region").
- **Loading state:** a spinner, then the full answer. No streaming.

## 6. Answer Pipeline

For each question:

1. **Build prompt.** System prompt contains the schema description verbatim, the full set of table definitions rendered as `CREATE TABLE` DDL with column descriptions as comments (no retrieval or selection), the dialect, today's date, and instructions to report ambiguity and assumptions. The user's question and the conversation's prior questions, SQL, and explanations are added.
2. **Generate.** The model returns SQL, a flag for ambiguity, and a list of assumptions.
3. **Ambiguity gate.** If the model flags ambiguity, no SQL runs. The app asks a clarifying question in the chat and waits for the user's next message (Section 7.2).
4. **Validate and run.** SQL goes through the read-only checks in Section 8. It runs with a 60-second timeout and a row cap (Section 9).
5. **Execution error.** If the database returns an error, the error text goes back to the model once for one repair attempt. If the repaired SQL also fails, the user sees the error and is asked to rephrase.
6. **Explain.** The model gets the question, SQL, assumptions, total row count, and the result rows up to the token budget (Section 9.2). It produces the plain-English explanation.
7. **Respond.** The user sees the explanation, the table (capped), the assumptions, a collapsed "Show query" toggle, and the CSV export button.

Every answer is logged to the audit log (Section 10).

## 7. Interaction Rules

### 7.1 Assumptions
Every answer lists the assumptions made, such as date ranges, definitions, or interpretations used. The one-pager requires that incomplete or ambiguous input is flagged, never answered silently. Assumptions are part of the answer, not a substitute for the ambiguity gate.

### 7.2 Clarification
Clarifying questions appear in the chat as the assistant's reply. The user answers in free text in the next message, and the app re-runs the pipeline with the clarified question. No suggested-option buttons in v1.

### 7.3 Relative dates
The app gives the model today's date. Relative periods are handled in this order:
1. If the period is vague in itself ("recently", "lately"), the model asks via the clarification flow in Section 7.2.
2. If the period is clear but resolves to a range outside the data coverage stated in the schema description, the model asks. Example: "last month" with today as 2026-10-21 resolves to September 2026, and the sample data ends in November 2025.
3. Otherwise the model uses the schema's calendar convention, and the answer states the period it used.

### 7.4 Questions the database cannot answer
- **Non-data requests** (e.g. "write me a poem", "delete customer 5"): the app declines and says it answers data questions about this database only. No SQL is generated.
- **Data questions the schema cannot answer** (e.g. "churn by NPS" with no NPS column): the app says the data is not in this database and lists the kinds of questions it can answer. No SQL is attempted.

### 7.5 Empty results
A query that runs and returns zero rows shows an explicit empty state: "No rows matched," with the filters applied and the SQL. It is not presented as an error and the explanation does not speculate about why.

## 8. Read-Only Enforcement (layered)

All three layers must hold; any one failing blocks writes.

1. **Database role:** the SQLite file is opened read-only (`mode=ro` URI), and the connection sets `PRAGMA query_only = ON`.
2. **SQL validation:** a parser allows exactly one statement and it must be a `SELECT` (CTEs allowed when the final statement is a `SELECT`). Anything else is rejected before execution.
3. **Transaction guard:** each query runs inside a transaction that is always rolled back.

Rejected SQL is logged to the audit log as a blocked attempt and the user is told the question could not be run safely.

## 9. Result Limits

### 9.1 Display and export
- Screen shows up to **500 rows**, paged, with the total count stated.
- CSV export returns the same 500-row capped result. A note says when the result was truncated.

### 9.2 Model token budget
- The explanation step receives rows up to a fixed token budget set in app settings (Section 16.2), chosen during build from measured row sizes.
- If the result exceeds the budget, the model sees the first N rows that fit. The explanation states that it covers only those rows, with the true total.

### 9.3 Query timeout
- 60-second hard timeout per query. Timed-out queries are cancelled and the user is told, with a suggestion to narrow the question.

## 10. Audit Log

- Stored in the app DB. Support-only read access, through an admin screen.
- **Retention:** 30 days, then purged.
- **Contents per entry:** user ID, database, timestamp, question, generated SQL, assumptions, ambiguity flag, row count, timing, error or blocked-attempt status, and the **result rows**.
- Users cannot view audit records, including their own.

The audit log holds result rows, so it is sensitive data. Access and retention are the controls. Row-level data masking is not implemented in v1 (Section 13).

## 11. Conversation History

- Each user has a private history, kept indefinitely unless the user deletes it.
- Users can delete their own conversations. Deletion removes the conversation and its messages from the app DB; it does not affect the audit log, which has its own retention.
- Sidebar: conversations grouped by database, newest first. Users scroll; no search.

## 12. Accounts and Access

- **Authentication:** built-in username and password accounts.
- **Account creation:** admin-created only. No self-registration.
- **Password reset:** done by support through the admin screen. No email.
- **Access control:** none in v1. Every authenticated user can query every configured database and see every database in the selector.
- Passwords are stored hashed (bcrypt or argon2).

## 13. Personal Data

Personal-data masking, blocking, or tagging is **out of scope for v1**. The one-pager's must-never-happen list has been amended accordingly.

Consequences the team accepts:
- Analysts can query any column, including personal data, and results show it.
- Result rows, including any personal data, are sent to the Claude API for explanation (Section 15).
- Result rows are stored in the audit log for 30 days (Section 10).

Support is responsible for choosing which databases are configured. Enforcement is a candidate for v2.

## 14. Prompt Injection

- Row values are untrusted. The explanation prompt wraps all row data in clearly marked data blocks and instructs the model to treat them as data only.
- When the result rows contain text values, the explanation is checked by a second Claude call. The judge receives the question and the explanation, and returns pass or fail on two criteria: the explanation stays within the result set, and it contains no instructions, SQL, or references to actions. A fail shows the table and a notice that the explanation could not be generated, instead of showing the explanation.
- Results with only numeric and date columns skip the check.
- Residual risk: a determined value can still influence the explanation wording. The DB is read-only, so the worst case is a misleading explanation with real values in the table. Documented as a known limitation.

## 15. LLM Data Handling

- Sent to the Claude API on every question: the schema description, all table definitions, the question, conversation context (prior questions, SQL, and explanations), the SQL, and result rows up to the token budget.
- Not sent: the database connection string, API keys, password hashes, audit log, or other conversations.
- Approved as designed (Section 22, item 1). No company data-governance sign-off is recorded in this spec.

## 16. Configuration

Two kinds of YAML file. Database files are loaded at startup and can also be added, changed and removed at runtime from the admin screen (§16.4). App settings are loaded at startup, and changes need a restart.

### 16.1 Database files
One file per database, in the configured config directory. The sample is `tests/cloudmetrics/cloudmetrics.yaml`.

Top-level keys:
- `name`: unique identifier. Used in the selector, the audit log, and the evaluation set's `database` field.
- `display_name`: label shown in the UI.
- `path`: SQLite file path, literal or `${NAME}` for an environment variable. Always opened read-only.
- `calendar.fiscal_year_start_month`: `1` for a calendar year.
- `description`: free-text schema description, sent to the model verbatim. Business rules and metric definitions live here and nowhere else.
- `tables`: list of tables. Each has `name`, `description`, and `columns`. Each column has `name`, `type`, and optionally `primary_key: true`, `references: table.column`, and `description`.

```yaml
name: cloudmetrics
display_name: CloudMetrics SaaS Analytics
path: /path/to/cloudmetrics.db    # opened read-only (mode=ro)
calendar:
  fiscal_year_start_month: 1
description: |
  CloudMetrics is a B2B project-management SaaS product. ...
  MRR = SUM(subscriptions.mrr) WHERE status = 'active'. ...
tables:
  - name: invoices
    description: Billing invoices generated for subscriptions.
    columns:
      - { name: invoice_id, type: INTEGER, primary_key: true, description: "Unique invoice identifier" }
      - { name: subscription_id, type: INTEGER, references: subscriptions.subscription_id }
      - { name: amount, type: REAL, description: "Invoice amount in USD" }
      - { name: status, type: TEXT, description: "paid, pending, overdue, refunded" }
```

### 16.2 App settings
Settings that are not tied to one database. Location: the app settings file (name to be chosen during build).

```yaml
llm:
  sql_model: claude-sonnet-5-5
  explain_model: claude-sonnet-5-5
  api_key_env: ANTHROPIC_API_KEY    # name of the env var, never the key
limits:
  display_rows: 500
  explain_token_budget: TBD         # set during build; Section 22, item 3
  query_timeout_seconds: 60
  audit_retention_days: 30
```

Secrets never appear in any YAML file. Secret values are read from environment variables named in the file.

### 16.3 Database checks
The checks run at startup for each configured file, and again on every save or re-check from the admin screen (§16.4). For each database:
- Confirm the file exists and opens read-only.
- Confirm each configured table and column exists with the stated type, and that each `references` target exists.
- At startup, a failed check disables that database. It is hidden from the selector and its error is shown in the admin screen. Other databases keep working. Failures are logged at startup.
- On a save from the admin screen, a failed check rejects the save and nothing is written. On a re-check, a failed check disables that database until it passes.

### 16.4 Managing databases from the admin screen
Support can add, edit, re-check and remove databases in the browser. Each saved database is a YAML file in the configured config directory, in the format of §16.1.
- **Fields:** the database file path (literal or `${NAME}`), and the schema YAML (uploaded or pasted, at most 1 MB).
- **Validation on save:** the YAML must parse and match §16.1. `name` must be unique and use only letters, digits, `_` and `-`. The file must pass the §16.3 checks. A save that fails is refused with the list of errors, and nothing is written.
- **Stored form:** the server writes canonical YAML. Comments in a file written this way are not kept.
- **Name:** immutable after creation. Conversations and audit entries refer to it.
- **Effect:** a saved database takes effect at once, with no restart, and appears in the selector for analysts.
- **Edit** replaces the path and schema. **Re-check** runs the §16.3 checks again on the saved file. **Remove** deletes the file from the selector. Existing conversations stay readable, and a follow-up to a removed database gets "Database not found".
- **Access:** support only. The server can open any SQLite file its process can read, read-only, so support chooses which files are configured (see §13).
- Files already in the config directory at startup are still loaded from disk (§16.3).

## 17. Validation and Test Fixtures

### 17.1 Fixtures
`tests/cloudmetrics/` holds the v1 development fixtures:
- `cloudmetrics.db`: sample SQLite database (customers, plans, subscriptions, invoices, support_tickets; data March 2022 to November 2025).
- `cloudmetrics.yaml`: database config in the format of Section 16.1.
- `cloudmetrics_eval.yaml`: evaluation set (Section 17.2).

The fixtures are used by tests and the validation harness only. Nothing in the app code may depend on these names or on this data; the app is configured for any database by its YAML file. The evaluation set is never loaded at app startup and never sent to the model.

### 17.2 Evaluation set format
Top-level keys: `database` (must match the database config's `name`) and `cases`.

Each case:
- `id`: unique identifier.
- `question`: the user's question.
- `category`: grouping label. The sample set uses `totals_trend`, `ranking`, `filter`, `comparison`, `clarification`, and `non_data`.
- `expected_sql`: SQL whose result set is the correct answer. Required unless `expected_outcome` is set. Every `expected_sql` in the sample set has been run against the sample database.
- `expected_outcome` (optional): `clarification` or `declined`. The case passes when the app returns that outcome and runs no SQL.
- `today` (optional): the date given to the model as today, for cases with relative periods.
- `conversation` (optional): prior turns, each with `question` and `sql`. The case question runs after these turns in the same conversation. See Section 5 and Section 22, item 2.
- `notes` (optional): reason for the expected answer, for human readers.

The sample set has 29 cases: 9 totals/trends, 5 rankings, 4 filters, 6 comparisons (one a follow-up), 2 clarifications, and 3 non-data requests.

### 17.3 Grading
- **SQL cases:** the generated SQL passes when its result set equals the `expected_sql` result set. Rows are compared as a multiset, so row order is ignored. Column order and aliases are ignored. Numeric values use a small relative tolerance.
- **Outcome cases:** pass when the app returns the `expected_outcome` and runs no SQL.

### 17.4 Pass bar and harness
- **Pass bar:** at least **90%** of cases pass. Every failure must either be flagged to the user during the run or be marked as a known failure with a reason. Silent wrong answers fail the bar regardless of pass rate.
- **Harness:** `uv run pytest tests/validation`, run on demand. It runs every case through the full pipeline with the LLM, against `tests/cloudmetrics/cloudmetrics.db`.
- Not a build gate in v1. Becomes a CI gate once CI exists.

## 18. Error Handling

| Condition | User sees |
|---|---|
| Ambiguous question | Clarifying question in chat |
| Non-data request | Declined, with the kinds of questions allowed |
| Data not in schema | Says data isn't in this database, lists what it can answer |
| Zero rows | Explicit empty state |
| SQL error after one repair | Error and a request to rephrase |
| Query timeout | Timed out, suggestion to narrow |
| Blocked (write or non-SELECT) | Could not run safely |
| LLM API error | Retry once, then a clear error. Nothing is shown as an answer. |
| Explanation failed injection check | Table plus notice that the explanation is unavailable |
| Token budget exceeded | Explanation states it covers the first N rows |

## 19. UI

- **Layout:** left sidebar (database selector, conversation list grouped by database, delete action), main panel (chat with answers).
- **Answer layout:** explanation text, assumptions, paged table (500-row cap), "Show query" toggle (collapsed), CSV export button.
- **Admin screen:** account creation and password reset, database management (add, edit, re-check, remove, with check errors), audit log viewer. Support role only.
- **Responsive:** not required. Desktop browser on a laptop.

## 20. Non-Functional

- **Scale:** under 10 users, one process.
- **Latency:** no target set. Spinner while working. Typical time is dominated by the LLM calls (two per question on a repair path, one otherwise).
- **Cost:** no per-user or global caps in v1. Usage is monitored through the Anthropic account dashboard.
- **Logging:** structured app log plus the audit log described in Section 10.

## 21. Testing

- Unit: SQL validator (accept one SELECT, reject writes, multi-statement, PRAGMA), row cap, token budget truncation, YAML validation, startup checks.
- Integration: the validation harness (Section 17.4) against `tests/cloudmetrics/cloudmetrics.db`.
- Integration: a database saved from the admin screen is validated before it is written, takes effect without a restart, and refuses path traversal in its file name or name (§16.4).
- Security: attempts to write through the chat (e.g., "delete all orders") must be blocked at each layer, tested by bypassing the validator to confirm the DB layer still rejects the write.
- Manual: checklist of error states from Section 18.

## 22. Decisions Log

All ten open items from the requirements interview are decided. The table records each decision and where it is applied.

| # | Item | Decision | Applied in |
|---|---|---|---|
| 1 | Result rows sent to the Claude API | Approved as designed | §15 |
| 2 | Prior SQL in follow-up context | Added to follow-up context now | §5, §6, §15 |
| 3 | Token budget for explanation rows | Fixed value in app settings, set during build | §9.2, §16.2 |
| 4 | Explanation injection check | Second Claude call, run only when results contain text values | §14 |
| 5 | Deleting one's own history | Users may delete their own conversations | §11 |
| 6 | Support roles | One role | §10, §12, §19 |
| 7 | Model choice | `claude-sonnet-5-5` for SQL and explanation | §4, §16.2 |
| 8 | Relative-period rule | Ask for vague periods, and for clear periods outside the data coverage; otherwise use the calendar convention and state the period | §7.3 |
| 9 | Path in database YAML | Literal path in the YAML | §16.1 |
| 10 | Managing database configuration | Support adds, edits, re-checks and removes databases in the admin screen. Each is a YAML file, validated on save and live without a restart. The name is immutable. | §16.3, §16.4, §19 |

### Follow-up actions
- **Item 1:** no company data-governance sign-off is recorded. Confirm it before connecting real data.
- **Item 3:** the token budget value is still open. It is set during build.
- **Item 9:** the supplied fixture `tests/cloudmetrics/cloudmetrics.yaml` still uses `${CLOUDMETRICS_DB_PATH}`. It was left unchanged because it is the supplied fixture. Change it to a literal path if you want the fixture to match this decision.

## 23. Out of Scope (v1)

- Multi-database questions
- Scheduled reports and alerts
- Writing data to any database
- Forecasting and predictions
- Access control by role, team, or region
- Searching user history
- Personal-data masking or blocking
- Engines other than SQLite
- LLM rate limits and spend caps
- SSO
- Streaming responses
- Suggested-option clarifications
- Uploading SQLite files through the browser
- Generating the schema from the database
