"use client";
import Link from "next/link";
import { useState } from "react";
import { useData, ErrorView } from "@/components/Load";
type Actor={id:string;display_name:string|null;actor_hash:string;status:string;suspicion_score:number};
export default function Actors(){const [min,setMin]=useState(0);const {data,error}=useData<Actor[]>(`/api/actors?min_score=${min}`);return <div className="stack"><h1>Actors</h1><ErrorView message={error}/><div className="card"><label>Minimum score <input type="number" min="0" max="100" value={min} onChange={e=>setMin(Number(e.target.value))}/></label></div><div className="card tablewrap"><table><thead><tr><th>Actor</th><th>Hash</th><th>Score</th><th>Status</th></tr></thead><tbody>{data?.map(a=><tr key={a.id}><td><Link href={`/actors/${a.id}`}>{a.display_name||"Unnamed"}</Link></td><td className="font-mono text-xs">{a.actor_hash.slice(0,20)}…</td><td>{a.suspicion_score}/100</td><td><span className="badge">{a.status}</span></td></tr>)}</tbody></table></div></div>}
