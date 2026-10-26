import { useState } from "react";

type Props = { sql: string };

export function ShowQuery({ sql }: Props) {
  const [open, setOpen] = useState(false);
  return (
    <div className="show-query">
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "Hide query" : "Show query"}
      </button>
      {open && <pre>{sql}</pre>}
    </div>
  );
}
