import { useEffect, useState } from "react";
import { Login, User } from "./Login";
import { RawSqlBox } from "./RawSqlBox";
import { Sidebar } from "./Sidebar";

// undefined = still checking the session; null = signed out.
export function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [database, setDatabase] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/auth/me")
      .then((res) => (res.ok ? (res.json() as Promise<User>) : null))
      .then(setUser)
      .catch(() => setUser(null));
  }, []);

  async function signOut() {
    await fetch("/api/auth/logout", { method: "POST" });
    setDatabase(null);
    setUser(null);
  }

  if (user === undefined) return null;
  if (user === null) return <Login onSignedIn={setUser} />;

  return (
    <div className="layout">
      <Sidebar selected={database} onSelect={setDatabase} />
      <main className="main">
        <header className="topbar">
          <span>Signed in as {user.username}</span>
          <button type="button" onClick={signOut}>
            Sign out
          </button>
        </header>
        {database === null ? (
          <p>Choose a database to start.</p>
        ) : (
          <RawSqlBox database={database} />
        )}
      </main>
    </div>
  );
}
