import { useEffect, useState } from "react";

type DatabaseStatus = {
  name: string;
  display_name: string | null;
  source: string;
  enabled: boolean;
  errors: string[];
};

export function StatusPanel() {
  const [rows, setRows] = useState<DatabaseStatus[]>([]);

  useEffect(() => {
    fetch("/api/admin/status")
      .then((res) => (res.ok ? (res.json() as Promise<DatabaseStatus[]>) : []))
      .then(setRows)
      .catch(() => setRows([]));
  }, []);

  return (
    <div className="panel">
      <h2>Database status</h2>
      <p>Databases that fail their startup checks are hidden from analysts. Fix the config and restart.</p>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Config file</th>
            <th>Status</th>
            <th>Errors</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.source}>
              <td>{r.display_name ?? r.name}</td>
              <td>{r.source}</td>
              <td>{r.enabled ? "Enabled" : "Disabled"}</td>
              <td>
                <ul>
                  {r.errors.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
