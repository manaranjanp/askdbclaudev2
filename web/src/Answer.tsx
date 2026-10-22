import { downloadCsv } from "./CsvExport";
import { ResultTable } from "./ResultTable";
import { ShowQuery } from "./ShowQuery";

export type AskResponse = {
  status: "answer" | "clarify" | "blocked" | "timeout" | "error";
  message: string | null;
  sql: string | null;
  assumptions: string[];
  explanation: string | null;
  columns: string[];
  rows: unknown[][];
  total: number;
  truncated: boolean;
  csv: string | null;
};

type Props = { response: AskResponse; question: string };

export function Answer({ response, question }: Props) {
  if (response.status !== "answer") {
    const role = response.status === "clarify" ? "status" : "alert";
    return <p role={role}>{response.message}</p>;
  }

  return (
    <div className="answer">
      <p className="explanation">{response.explanation}</p>
      {response.assumptions.length > 0 && (
        <div className="assumptions">
          <strong>Assumptions</strong>
          <ul>
            {response.assumptions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </div>
      )}
      <ResultTable columns={response.columns} rows={response.rows} />
      {response.truncated && (
        <p className="note">
          Showing the first {response.rows.length} of {response.total} rows.
        </p>
      )}
      <div className="actions">
        {response.sql && <ShowQuery sql={response.sql} />}
        {response.csv && (
          <button type="button" onClick={() => downloadCsv(response.csv!, question)}>
            Export CSV
          </button>
        )}
      </div>
    </div>
  );
}
