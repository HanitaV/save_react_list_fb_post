"use client";
import Link from "next/link";
import { useData, ErrorView } from "@/components/Load";

type Status = {
  posts: number; interactions: number; actors: number; suspicious_actors: number;
  clusters: number; evidence_records: number; browser_health: string;
  queue: { mode: string; pending: number | null };
};

export default function Dashboard() {
  const { data, error } = useData<Status>("/api/system/status");
  const metrics = data ? [
    ["Posts", data.posts], ["Interactions", data.interactions],
    ["Actors", data.actors], ["Suspicious actors", data.suspicious_actors],
    ["Clusters", data.clusters], ["Evidence records", data.evidence_records],
    ["Queue pending", data.queue.pending ?? "Unavailable"],
  ] : [];
  return <div className="stack">
    <div><h1>Engagement overview</h1><p className="muted">Observed activity and evidence processing status</p></div>
    <ErrorView message={error}/>
    <div className="gridcards">{metrics.map(([label, value]) => <div className="card" key={label}><div className="muted">{label}</div><div className="text-3xl font-bold mt-3 text-white">{value}</div></div>)}</div>
    <div className="card"><h2>Browser health</h2><span className="badge">{data?.browser_health || "Loading"}</span><p className="muted mt-3">Capture pauses when a restriction or authentication challenge appears.</p></div>
    <div className="flex gap-3"><Link href="/posts">Review posts →</Link><Link href="/actors">Review actors →</Link></div>
  </div>;
}
