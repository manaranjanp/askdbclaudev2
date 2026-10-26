import { useState } from "react";
import { AuditPanel } from "./AuditPanel";
import { DatabasesPanel } from "./DatabasesPanel";
import { UsersPanel } from "./UsersPanel";

type Tab = "users" | "databases" | "audit";

const TABS: { id: Tab; label: string }[] = [
  { id: "users", label: "Users" },
  { id: "databases", label: "Databases" },
  { id: "audit", label: "Audit log" },
];

// Support role only. The server enforces this on every admin route.
type Props = { onDatabasesChanged: () => void };

export function AdminPage({ onDatabasesChanged }: Props) {
  const [tab, setTab] = useState<Tab>("users");
  return (
    <section className="admin">
      <h1>Admin</h1>
      <nav role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>
      {tab === "users" && <UsersPanel />}
      {tab === "databases" && <DatabasesPanel onChanged={onDatabasesChanged} />}
      {tab === "audit" && <AuditPanel />}
    </section>
  );
}
