import { FormEvent, useState } from "react";
import { Answer, AskResponse } from "./Answer";

type Turn = { question: string; response: AskResponse | null; error: string | null };

type Props = { database: string };

export function Chat({ database }: Props) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);

  async function ask(event: FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || busy) return;

    setBusy(true);
    setQuestion("");
    setTurns((prev) => [...prev, { question: text, response: null, error: null }]);
    const index = turns.length;
    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ database, question: text }),
      });
      const body = await res.json();
      const error = res.ok ? null : (typeof body.detail === "string" ? body.detail : `HTTP ${res.status}`);
      setTurns((prev) =>
        prev.map((t, i) => (i === index ? { ...t, response: res.ok ? (body as AskResponse) : null, error } : t)),
      );
    } catch {
      setTurns((prev) =>
        prev.map((t, i) => (i === index ? { ...t, error: "Could not reach the server." } : t)),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="chat">
      <ol className="turns">
        {turns.map((turn, i) => (
          <li key={i} className="turn">
            <p className="question">{turn.question}</p>
            {turn.response && <Answer response={turn.response} question={turn.question} />}
            {turn.error && <p role="alert">{turn.error}</p>}
            {!turn.response && !turn.error && <p className="spinner">Working on it…</p>}
          </li>
        ))}
      </ol>
      <form className="composer" onSubmit={ask}>
        <input
          aria-label="Question"
          placeholder="Ask a question about this database"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={busy}
        />
        <button type="submit" disabled={busy || !question.trim()}>
          Ask
        </button>
      </form>
    </section>
  );
}
