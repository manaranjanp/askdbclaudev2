import { FormEvent, useEffect, useState } from "react";

type AdminUser = { id: number; username: string; role: string; created_at: string };

export function UsersPanel() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("analyst");
  const [resetFor, setResetFor] = useState<number | null>(null);
  const [resetPassword, setResetPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  function load() {
    fetch("/api/admin/users")
      .then((res) => (res.ok ? (res.json() as Promise<AdminUser[]>) : []))
      .then(setUsers)
      .catch(() => setUsers([]));
  }

  useEffect(load, []);

  async function create(event: FormEvent) {
    event.preventDefault();
    const res = await fetch("/api/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, role }),
    });
    if (res.status === 201) {
      setMessage(`Created ${username}.`);
      setUsername("");
      setPassword("");
      load();
    } else {
      const body = await res.json().catch(() => ({}));
      setMessage(typeof body.detail === "string" ? body.detail : `Could not create (HTTP ${res.status}).`);
    }
  }

  async function reset(event: FormEvent, id: number) {
    event.preventDefault();
    const res = await fetch(`/api/admin/users/${id}/password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: resetPassword }),
    });
    setMessage(res.status === 204 ? "Password reset. Their sessions have ended." : `Reset failed (HTTP ${res.status}).`);
    if (res.status === 204) {
      setResetFor(null);
      setResetPassword("");
    }
  }

  return (
    <div className="panel">
      <h2>Users</h2>
      {message && <p role="status">{message}</p>}
      <table>
        <thead>
          <tr>
            <th>Username</th>
            <th>Role</th>
            <th>Created</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td>{u.username}</td>
              <td>{u.role}</td>
              <td>{u.created_at}</td>
              <td>
                {resetFor === u.id ? (
                  <form onSubmit={(e) => reset(e, u.id)}>
                    <input
                      type="password"
                      aria-label={`New password for ${u.username}`}
                      minLength={8}
                      value={resetPassword}
                      onChange={(e) => setResetPassword(e.target.value)}
                      required
                    />
                    <button type="submit">Save</button>
                  </form>
                ) : (
                  <button type="button" onClick={() => setResetFor(u.id)}>
                    Reset password
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Create account</h3>
      <form onSubmit={create} className="create-user">
        <label htmlFor="new-username">Username</label>
        <input id="new-username" value={username} onChange={(e) => setUsername(e.target.value)} required />
        <label htmlFor="new-password">Password (at least 8 characters)</label>
        <input
          id="new-password"
          type="password"
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <label htmlFor="new-role">Role</label>
        <select id="new-role" value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="analyst">Analyst</option>
          <option value="support">Support</option>
        </select>
        <button type="submit">Create</button>
      </form>
    </div>
  );
}
