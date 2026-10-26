import { useEffect, useState } from "react";
import { AdminPage } from "./admin/AdminPage";
import { Chat } from "./Chat";
import { Login, User } from "./Login";
import { ConversationSummary, Sidebar } from "./Sidebar";

// undefined = still checking the session; null = signed out.
export function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [database, setDatabase] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<number | null>(null);
  // Changing this remounts Chat, which starts a fresh conversation or opens a saved one.
  const [chatKey, setChatKey] = useState(0);
  // Bumped whenever the conversation list may have changed.
  const [listVersion, setListVersion] = useState(0);
  const [view, setView] = useState<"chat" | "admin">("chat");

  useEffect(() => {
    fetch("/api/auth/me")
      .then((res) => (res.ok ? (res.json() as Promise<User>) : null))
      .then(setUser)
      .catch(() => setUser(null));
  }, []);

  function startNew(name: string | null) {
    setDatabase(name);
    setConversationId(null);
    setChatKey((k) => k + 1);
  }

  function open(conversation: ConversationSummary) {
    setDatabase(conversation.database);
    setConversationId(conversation.id);
    setChatKey((k) => k + 1);
  }

  async function signOut() {
    await fetch("/api/auth/logout", { method: "POST" });
    setDatabase(null);
    setConversationId(null);
    setUser(null);
  }

  if (user === undefined) return null;
  if (user === null) return <Login onSignedIn={setUser} />;

  return (
    <div className="layout">
      <Sidebar
        selected={database}
        selectedConversationId={conversationId}
        refreshKey={listVersion}
        onSelect={(name) => startNew(name)}
        onOpenConversation={open}
        onNewConversation={() => startNew(database)}
        onDeleted={(id) => {
          if (id === conversationId) startNew(database);
          setListVersion((v) => v + 1);
        }}
      />
      <main className="main">
        <header className="topbar">
          <span>Signed in as {user.username}</span>
          {user.role === "support" && (
            <button type="button" onClick={() => setView(view === "admin" ? "chat" : "admin")}>
              {view === "admin" ? "Back to questions" : "Admin"}
            </button>
          )}
          <button type="button" onClick={signOut}>
            Sign out
          </button>
        </header>
        {view === "admin" ? (
          <AdminPage onDatabasesChanged={() => setListVersion((v) => v + 1)} />
        ) : database === null ? (
          <p>Choose a database to start.</p>
        ) : (
          <Chat
            key={chatKey}
            database={database}
            conversationId={conversationId}
            onSaved={(id) => {
              setConversationId(id);
              setListVersion((v) => v + 1);
            }}
          />
        )}
      </main>
    </div>
  );
}
