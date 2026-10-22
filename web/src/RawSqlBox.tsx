// Temporary test UI for the safe SQL runner. Removed in slice 4.
import { FormEvent, useState } from "react";

type QueryResponse = {
  columns: string[];
  rows: unknown[][];
  total: number;
  truncated: boolean;
};

type Props = { database: string };

export function RawSqlBox({ database }: Props) {
  const [sql, setSql] = useState("SELECT plan_name, monthly_price FROM plans");
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setResult(null);
    const res = await fetch("/api/dev/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ database, sql }),
    });
    const body = await res.json();
    if (!res.ok) {
      setError(typeof body.detail === "string" ? body.detail : `HTTP ${res.status}`);
      return;
    }
    setResult(body as QueryResponse);
  }

  return (
    <section>
      <form onSubmit={run}>
        <textarea rows={5} value={sql} onChange={(e) => setSql(e.target.value)} />
        <button type="submit">Run</button>
      </form>
      {error && <p role="alert">{error}</p>}
      {result && (
        <>
          <p>
            {result.total} row(s){result.truncated ? `, showing first ${result.rows.length}` : ""}
          </p>
          <table>
            <thead>
              <tr>
                {result.columns.map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row, i) => (
                <tr key={i}>
                  {row.map((v, j) => (
                    <td key={j}>{String(v ?? "NULL")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
