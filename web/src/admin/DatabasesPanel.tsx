import { ChangeEvent, FormEvent, useEffect, useState } from "react";

type DatabaseEntry = {
  file: string;
  name: string;
  display_name: string | null;
  path: string | null;
  enabled: boolean;
  errors: string[];
  schema_yaml: string;
};

// "new" while adding; otherwise the file id of the database being edited.
type Editing = "new" | string | null;

type ApiError = { detail?: string | { errors?: string[] } };

function errorsFrom(body: ApiError, fallback: string): string[] {
  if (body.detail && typeof body.detail === "object" && body.detail.errors) return body.detail.errors;
  if (typeof body.detail === "string") return [body.detail];
  return [fallback];
}

type Props = { onChanged: () => void };

export function DatabasesPanel({ onChanged }: Props) {
  const [entries, setEntries] = useState<DatabaseEntry[]>([]);
  const [editing, setEditing] = useState<Editing>(null);
  const [path, setPath] = useState("");
  const [schema, setSchema] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const [message, setMessage] = useState<string | null>(null);

  function load() {
    fetch("/api/admin/databases")
      .then((res) => (res.ok ? (res.json() as Promise<DatabaseEntry[]>) : []))
      .then(setEntries)
      .catch(() => setEntries([]));
  }

  useEffect(load, []);

  function startNew() {
    setEditing("new");
    setPath("");
    setSchema("");
    setErrors([]);
    setMessage(null);
  }

  function startEdit(entry: DatabaseEntry) {
    setEditing(entry.file);
    setPath(entry.path ?? "");
    setSchema(entry.schema_yaml);
    setErrors([]);
    setMessage(null);
  }

  function cancel() {
    setEditing(null);
    setErrors([]);
  }

  function readSchemaFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setSchema(String(reader.result ?? ""));
    reader.readAsText(file);
  }

  function body() {
    return { path, schema_yaml: schema };
  }

  async function validate() {
    const res = await fetch("/api/admin/databases/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...body(), file: editing === "new" ? null : editing }),
    });
    const result = (await res.json()) as { ok: boolean; errors: string[] };
    setErrors(result.ok ? [] : result.errors);
    setMessage(result.ok ? "The configuration is valid. Nothing has been saved." : null);
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    setErrors([]);
    setMessage(null);
    const isNew = editing === "new";
    const res = await fetch(
      isNew ? "/api/admin/databases" : `/api/admin/databases/${editing}`,
      {
        method: isNew ? "POST" : "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body()),
      },
    );
    if (res.ok) {
      const saved = (await res.json()) as DatabaseEntry;
      setMessage(`Saved ${saved.name}. It is available to analysts now.`);
      setEditing(null);
      load();
      onChanged();
      return;
    }
    const failure = (await res.json().catch(() => ({}))) as ApiError;
    setErrors(errorsFrom(failure, `Save failed (HTTP ${res.status}).`));
  }

  async function recheck(file: string) {
    const res = await fetch(`/api/admin/databases/${file}/recheck`, { method: "POST" });
    setMessage(res.ok ? "Re-checked." : `Re-check failed (HTTP ${res.status}).`);
    load();
    onChanged();
  }

  async function remove(entry: DatabaseEntry) {
    if (!window.confirm(`Remove ${entry.name}? Existing conversations stay, but new questions to it will fail.`)) return;
    const res = await fetch(`/api/admin/databases/${entry.file}`, { method: "DELETE" });
    setMessage(res.status === 204 ? `Removed ${entry.name}.` : `Remove failed (HTTP ${res.status}).`);
    if (editing === entry.file) setEditing(null);
    load();
    onChanged();
  }

  return (
    <div className="panel">
      <h2>Databases</h2>
      <p>Changes take effect at once. A save that fails any check is refused, and nothing is written.</p>
      {message && <p role="status">{message}</p>}

      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>File</th>
            <th>Status</th>
            <th>Errors</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {entries.map((e) => (
            <tr key={e.file}>
              <td>{e.display_name ?? e.name}</td>
              <td>{e.path ?? "(unreadable)"}</td>
              <td>{e.enabled ? "Enabled" : "Disabled"}</td>
              <td>
                <ul>
                  {e.errors.map((err, i) => (
                    <li key={i}>{err}</li>
                  ))}
                </ul>
              </td>
              <td className="row-actions">
                <button type="button" onClick={() => startEdit(e)}>
                  Edit
                </button>
                <button type="button" onClick={() => recheck(e.file)}>
                  Re-check
                </button>
                <button type="button" onClick={() => remove(e)}>
                  Remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {entries.length === 0 && <p>No databases yet.</p>}

      {editing === null ? (
        <button type="button" onClick={startNew}>
          Add database
        </button>
      ) : (
        <form onSubmit={save} className="database-form">
          <h3>{editing === "new" ? "Add database" : `Edit ${editing}`}</h3>
          <label htmlFor="db-path">Database file path (absolute, or ${"{NAME}"} for an environment variable)</label>
          <input id="db-path" value={path} onChange={(e) => setPath(e.target.value)} required />

          <label htmlFor="db-schema-file">Schema file (YAML)</label>
          <input id="db-schema-file" type="file" accept=".yaml,.yml" onChange={readSchemaFile} />

          <label htmlFor="db-schema">Schema YAML</label>
          <textarea
            id="db-schema"
            rows={16}
            value={schema}
            onChange={(e) => setSchema(e.target.value)}
            required
          />

          {errors.length > 0 && (
            <ul role="alert" className="errors">
              {errors.map((err, i) => (
                <li key={i}>{err}</li>
              ))}
            </ul>
          )}

          <div className="form-actions">
            <button type="button" onClick={validate}>
              Validate
            </button>
            <button type="submit">Save</button>
            <button type="button" onClick={cancel}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
