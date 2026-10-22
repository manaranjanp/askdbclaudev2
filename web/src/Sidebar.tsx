import { useEffect, useState } from "react";

export type DatabaseSummary = { name: string; display_name: string };

type Props = {
  selected: string | null;
  onSelect: (name: string) => void;
};

export function Sidebar({ selected, onSelect }: Props) {
  const [databases, setDatabases] = useState<DatabaseSummary[]>([]);
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

  return (
    <aside className="sidebar">
      <label htmlFor="database">Database</label>
      <select
        id="database"
        value={selected ?? ""}
        onChange={(e) => onSelect(e.target.value)}
      >
        <option value="" disabled>
          Choose a database
        </option>
        {databases.map((db) => (
          <option key={db.name} value={db.name}>
            {db.display_name}
          </option>
        ))}
      </select>
      {error && <p role="alert">Could not load databases: {error}</p>}
    </aside>
  );
}
