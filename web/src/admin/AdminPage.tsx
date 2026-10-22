import { useState } from "react";
import { AuditPanel } from "./AuditPanel";
import { StatusPanel } from "./StatusPanel";
import { UsersPanel } from "./UsersPanel";

type Tab = "users" | "status" | "audit";

const TABS: { id: Tab; label: string }[] = [
  { id: "users", label: "Users" },
  { id: "status", label: "Database status" },
  { id: "audit", label: "Audit log" },
];

// Support role only. The server enforces this on every admin route.
export function AdminPage() {
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
      {tab === "status" && <StatusPanel />}
      {tab === "audit" && <AuditPanel />}
    </section>
  );
}
