import { useState } from "react";
import { Sidebar } from "./Sidebar";

export function App() {
  const [database, setDatabase] = useState<string | null>(null);

  return (
    <div className="layout">
      <Sidebar selected={database} onSelect={setDatabase} />
      <main className="main">
        {database === null ? (
          <p>Choose a database to start.</p>
        ) : (
          <p>Selected: {database}</p>
        )}
      </main>
    </div>
  );
}
