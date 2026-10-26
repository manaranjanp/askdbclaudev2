import { useEffect, useState } from "react";

type AuditEntry = {
  id: number;
  created_at: string;
  username: string | null;
  database: string;
  question: string;
  sql: string | null;
  outcome: string;
  error: string | null;
  row_count: number;
  duration_ms: number;
  result_rows: unknown[][];
};

const PAGE = 50;
const OUTCOMES = ["", "answer", "clarify", "declined", "no_data", "empty", "blocked", "timeout", "error"];

export function AuditPanel() {
  const [items, setItems] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [outcome, setOutcome] = useState("");
  const [database, setDatabase] = useState("");
  const [open, setOpen] = useState<number | null>(null);

  useEffect(() => {
    const params = new URLSearchParams({ limit: String(PAGE), offset: String(page * PAGE) });
    if (outcome) params.set("outcome", outcome);
    if (database) params.set("database", database);
    fetch(`/api/admin/audit?${params}`)
      .then((res) => (res.ok ? res.json() : { total: 0, items: [] }))
      .then((body) => {
        setTotal(body.total);
        setItems(body.items);
      })
      .catch(() => setItems([]));
  }, [page, outcome, database]);

  const pages = Math.max(1, Math.ceil(total / PAGE));

  return (
    <div className="panel">
      <h2>Audit log</h2>
      <p>Kept for 30 days. Result rows are sensitive: this page is for support only.</p>
      <div className="filters">
        <label htmlFor="audit-outcome">Outcome</label>
        <select
          id="audit-outcome"
          value={outcome}
          onChange={(e) => {
            setOutcome(e.target.value);
            setPage(0);
          }}
        >
          {OUTCOMES.map((o) => (
            <option key={o} value={o}>
              {o || "Any"}
            </option>
          ))}
        </select>
        <label htmlFor="audit-database">Database</label>
        <input
          id="audit-database"
          value={database}
          onChange={(e) => {
            setDatabase(e.target.value);
            setPage(0);
          }}
        />
      </div>
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>User</th>
            <th>Database</th>
            <th>Question</th>
            <th>Outcome</th>
            <th>Rows</th>
          </tr>
        </thead>
        <tbody>
          {items.map((e) => (
            <tr key={e.id} onClick={() => setOpen(open === e.id ? null : e.id)}>
              <td>{e.created_at}</td>
              <td>{e.username ?? "(deleted)"}</td>
              <td>{e.database}</td>
              <td>{e.question}</td>
              <td>{e.outcome}</td>
              <td>{e.row_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {open !== null && (() => {
        const entry = items.find((i) => i.id === open);
        if (!entry) return null;
        return (
          <div className="detail">
            <h3>Entry {entry.id}</h3>
            {entry.error && <p role="alert">{entry.error}</p>}
            {entry.sql && <pre>{entry.sql}</pre>}
            <p>
              {entry.duration_ms} ms, {entry.row_count} row(s)
            </p>
            <pre>{JSON.stringify(entry.result_rows.slice(0, 20), null, 1)}</pre>
          </div>
        );
      })()}
      <div className="pager">
        <button type="button" disabled={page === 0} onClick={() => setPage(page - 1)}>
          Previous
        </button>
        <span>
          Page {page + 1} of {pages}
        </span>
        <button type="button" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>
          Next
        </button>
      </div>
    </div>
  );
}
