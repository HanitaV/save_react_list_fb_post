"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useData, ErrorView } from "@/components/Load";
import { API, api, token } from "@/lib/api";
type Interaction = {id:string;actor_id:string;actor_name:string|null;type:string;observed_at:string;score:number};
type Post = {id:string;url:string;status:string;last_scanned_at:string|null;interaction_count:number;unique_actors:number;reaction_distribution:Record<string,number>;interactions:Interaction[]};
export default function PostDetail() {
  const id = useParams().id as string; const { data, error, reload } = useData<Post>(`/api/posts/${id}`);
  const [reaction,setReaction]=useState("ALL"); const [score,setScore]=useState(0); const [message,setMessage]=useState("");
  async function analyze() { try { const r=await api<{actors:number}>(`/api/analyze/post/${id}`,{method:"POST"});setMessage(`Analyzed ${r.actors} actors`);reload(); } catch(e){setMessage(String(e));} }
  async function exportReport() { const r=await fetch(`${API}/api/reports/post/${id}`,{method:"POST",headers:{Authorization:`Bearer ${token()}`}}); if(!r.ok){setMessage(await r.text());return;} const blob=await r.blob(); const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=`report-${id}.zip`;a.click();URL.revokeObjectURL(a.href); }
  const rows=data?.interactions.filter(r=>(reaction==="ALL"||r.type===reaction)&&r.score>=score)||[];
  return <div className="stack"><div><h1>Post detail</h1><p className="muted break-all">{data?.url}</p></div><ErrorView message={error}/><div className="flex gap-2"><button onClick={analyze}>Analyze post</button><button onClick={exportReport}>Export evidence ZIP</button></div>{message&&<p>{message}</p>}<div className="gridcards"><div className="card">Interactions<div className="text-2xl">{data?.interaction_count||0}</div></div><div className="card">Unique actors<div className="text-2xl">{data?.unique_actors||0}</div></div><div className="card">Last scan<div>{data?.last_scanned_at||"—"}</div></div></div><div className="card"><h2>Reaction distribution</h2><div className="flex flex-wrap gap-3">{Object.entries(data?.reaction_distribution||{}).map(([k,v])=><div className="badge" key={k}>{k}: {v}</div>)}</div></div><div className="card"><h2>Interactions</h2><div className="flex gap-2 mb-4"><select value={reaction} onChange={e=>setReaction(e.target.value)}><option>ALL</option>{Object.keys(data?.reaction_distribution||{}).map(k=><option key={k}>{k}</option>)}</select><input type="number" min="0" max="100" value={score} onChange={e=>setScore(Number(e.target.value))} aria-label="Minimum score"/></div><div className="tablewrap"><table><thead><tr><th>Actor</th><th>Type</th><th>Observed</th><th>Score</th></tr></thead><tbody>{rows.map(r=><tr key={r.id}><td><Link href={`/actors/${r.actor_id}`}>{r.actor_name||r.actor_id}</Link></td><td>{r.type}</td><td>{r.observed_at}</td><td>{r.score}</td></tr>)}</tbody></table></div></div></div>;
}
