import { useEffect, useState } from "react";

export type DatabaseSummary = { name: string; display_name: string };

export type ConversationSummary = {
  id: number;
  database: string;
  title: string;
  updated_at: string;
};

type Props = {
  selected: string | null;
  selectedConversationId: number | null;
  refreshKey: number;
  onSelect: (name: string) => void;
  onOpenConversation: (conversation: ConversationSummary) => void;
  onNewConversation: () => void;
  onDeleted: (id: number) => void;
};

export function Sidebar({
  selected,
  selectedConversationId,
  refreshKey,
  onSelect,
  onOpenConversation,
  onNewConversation,
  onDeleted,
}: Props) {
  const [databases, setDatabases] = useState<DatabaseSummary[]>([]);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/databases")
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json() as Promise<DatabaseSummary[]>;
      })
      .then(setDatabases)
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    fetch("/api/conversations")
      .then((res) => (res.ok ? (res.json() as Promise<ConversationSummary[]>) : []))
      .then(setConversations)
      .catch(() => setConversations([]));
  }, [refreshKey]);

  async function remove(id: number) {
    if (!window.confirm("Delete this conversation? This cannot be undone.")) return;
    const res = await fetch(`/api/conversations/${id}`, { method: "DELETE" });
    if (res.ok) onDeleted(id);
  }

  const nameOf = (db: string) => databases.find((d) => d.name === db)?.display_name ?? db;

  // Group by database, keeping the server's newest-first order inside each group.
  const groups = new Map<string, ConversationSummary[]>();
  for (const c of conversations) {
    groups.set(c.database, [...(groups.get(c.database) ?? []), c]);
  }

  return (
    <aside className="sidebar">
      <label htmlFor="database">Database</label>
      <select id="database" value={selected ?? ""} onChange={(e) => onSelect(e.target.value)}>
        <option value="" disabled>
          Choose a database
        </option>
        {databases.map((db) => (
          <option key={db.name} value={db.name}>
            {db.display_name}
          </option>
        ))}
      </select>
      {selected && (
        <button type="button" onClick={onNewConversation}>
          New conversation
        </button>
      )}
      {error && <p role="alert">Could not load databases: {error}</p>}

      <nav aria-label="Conversations">
        {[...groups.entries()].map(([db, items]) => (
          <div key={db} className="conversation-group">
            <h2>{nameOf(db)}</h2>
            <ul>
              {items.map((c) => (
                <li key={c.id} className={c.id === selectedConversationId ? "active" : undefined}>
                  <button type="button" className="open" onClick={() => onOpenConversation(c)}>
                    {c.title}
                  </button>
                  <button type="button" aria-label={`Delete ${c.title}`} onClick={() => remove(c.id)}>
                    Delete
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
    </aside>
  );
}
