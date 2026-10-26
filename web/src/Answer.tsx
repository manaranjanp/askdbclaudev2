import { downloadCsv } from "./CsvExport";
import { ResultTable } from "./ResultTable";
import { ShowQuery } from "./ShowQuery";

// Tokens the model used for this question. Absent on answers saved before usage was recorded.
export type Usage = { input_tokens: number; output_tokens: number };

export type AskResponse = {
  status: "answer" | "clarify" | "declined" | "no_data" | "empty" | "blocked" | "timeout" | "error";
  message: string | null;
  sql: string | null;
  assumptions: string[];
  explanation: string | null;
  columns: string[];
  rows: unknown[][];
  total: number;
  truncated: boolean;
  csv: string | null;
  notice: string | null;
  usage?: Usage;
};

type Props = { response: AskResponse; question: string };

// Statuses where the user is asked something or told why nothing ran. Not failures.
const NOTICE = new Set(["clarify", "declined", "no_data"]);

export function Answer({ response, question }: Props) {
  if (NOTICE.has(response.status)) {
    return (
      <p role="status" className={`notice ${response.status}`}>
        {response.message}
      </p>
    );
  }

  if (response.status === "empty") {
    return (
      <div className="answer">
        <p role="status" className="empty">
          {response.message}
        </p>
        {response.sql && <ShowQuery sql={response.sql} />}
      </div>
    );
  }

  if (response.status !== "answer") {
    return <p role="alert">{response.message}</p>;
  }

  return (
    <div className="answer">
      {response.explanation && <p className="explanation">{response.explanation}</p>}
      {response.notice && (
        <p role="status" className="notice">
          {response.notice}
        </p>
      )}
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
