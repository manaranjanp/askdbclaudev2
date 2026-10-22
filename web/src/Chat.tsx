import { FormEvent, useEffect, useState } from "react";
import { Answer, AskResponse } from "./Answer";

type Turn = { question: string; response: AskResponse | null; error: string | null };

type Props = {
  database: string;
  conversationId: number | null;
  onSaved: (conversationId: number) => void;
};

export function Chat({ database, conversationId: initialId, onSaved }: Props) {
  const [conversationId, setConversationId] = useState<number | null>(initialId);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);

  // Opening a saved conversation loads its earlier turns from the server.
  useEffect(() => {
    if (initialId === null) return;
    fetch(`/api/conversations/${initialId}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((body) => {
        if (!body) return;
        setTurns(
          body.messages.map((m: { question: string; answer: AskResponse }) => ({
            question: m.question,
            response: m.answer,
            error: null,
          })),
        );
      })
      .catch(() => setTurns([]));
  }, [initialId]);

  async function ask(event: FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || busy) return;

    setBusy(true);
    setQuestion("");
    const index = turns.length;
    setTurns((prev) => [...prev, { question: text, response: null, error: null }]);
    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          database,
          question: text,
          conversation_id: conversationId ?? undefined,
        }),
      });
      const body = await res.json();
      if (!res.ok) {
        const message = typeof body.detail === "string" ? body.detail : `HTTP ${res.status}`;
        setTurns((prev) => prev.map((t, i) => (i === index ? { ...t, error: message } : t)));
        return;
      }
      setTurns((prev) => prev.map((t, i) => (i === index ? { ...t, response: body as AskResponse } : t)));
      setConversationId(body.conversation_id);
      onSaved(body.conversation_id);
    } catch {
      setTurns((prev) => prev.map((t, i) => (i === index ? { ...t, error: "Could not reach the server." } : t)));
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
