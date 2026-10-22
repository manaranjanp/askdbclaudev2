// CSV is built by the server (the same capped rows the screen shows).
export function downloadCsv(csv: string, name: string): void {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${name.slice(0, 60).replace(/[^\w-]+/g, "_") || "result"}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}
