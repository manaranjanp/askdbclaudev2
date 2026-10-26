# Manual checklist: SPEC §18 error states

Run against the live app with a real `ANTHROPIC_API_KEY`, using the CloudMetrics fixture.
For each row, check the message the user sees in the chat, and that the outcome is recorded in the audit log (`audit_log` table in the app DB).

Setup:

```sh
export ANTHROPIC_API_KEY=...        # never commit this
export CLOUDMETRICS_DB_PATH=/absolute/path/to/tests/cloudmetrics/cloudmetrics.db
uv run uvicorn askdb.main:app --reload
cd web && npm run dev
```

| # | Ask this | Expect | Check |
|---|---|---|---|
| 1 | "Show me the sales pipeline" | Clarifying question in the chat, or a data-not-in-schema notice | No table, no SQL run |
| 2 | "Write me a poem about invoices" | Declined, with the kinds of data questions allowed | No SQL run |
| 3 | "Churn by NPS score" | Says the data is not in this database and lists what it can answer | No SQL run |
| 4 | "Show the top 5 plans by price" | Table with explanation and assumptions | Show query works, CSV downloads |
| 5 | "Customers in Antarctica" | "No rows matched." with the SQL, no explanation | Not shown as an error |
| 6 | "Delete all customers" | Could not be run safely | Blocked row in the audit log; the DB is unchanged |
| 7 | A recursive CTE with no end (ask for "every integer") | Timed out, with a suggestion to narrow the question | Timeout row in the audit log |
| 8 | "Average invoice amount last month" | Assumption states the period used, or asks for clarification | Period in the answer matches SPEC §7.3 |
| 9 | Stop the network, then ask any question | "The AI service did not respond. Please try again." | No answer shown; error row in the audit log |
| 10 | Unset `ANTHROPIC_API_KEY`, restart, then ask | A clear configuration message, not a stack trace | No answer shown |
| 11 | Ask a question with a column name that does not exist (for example "by loyalty tier") | A rephrase request after one repair attempt | The repair attempt is visible in the audit log only as one error row |

After the checklist, confirm that `SELECT COUNT(*) FROM customers` on the fixture still returns 200.
