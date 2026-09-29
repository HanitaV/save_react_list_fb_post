"use client";
import { useData, ErrorView } from "@/components/Load";
import { api } from "@/lib/api";

type Status = Record<string, string | number | boolean | { mode: string; pending: number | null }>;

export default function System() {
  const { data, error, reload } = useData<Status>("/api/system/status");
  return <div className="stack">
    <h1>System status</h1><ErrorView message={error}/>
    <button className="w-fit" onClick={reload}>Refresh</button>
    {data?.browser_health === "NEEDS_MANUAL_REVIEW" && <button className="w-fit" onClick={async () => { await api("/api/system/resume", { method: "POST" }); reload(); }}>Resume after manual review</button>}
    <div className="gridcards">{data && Object.entries(data).map(([key, value]) =>
      <div className="card" key={key}><div className="muted">{key.replaceAll("_", " ")}</div><div className="text-xl mt-2">{typeof value === "object" ? `${value.mode}: ${value.pending ?? "Unavailable"} pending` : typeof value === "boolean" ? value ? "Yes" : "No" : value}</div></div>
    )}</div>
  </div>;
}
