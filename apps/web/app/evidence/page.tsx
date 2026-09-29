"use client";
import Link from "next/link";
import { useData, ErrorView } from "@/components/Load";
type Actor={id:string;display_name:string|null;actor_hash:string;suspicion_score:number};
export default function Evidence(){const {data,error}=useData<Actor[]>("/api/actors?min_score=50");return <div className="stack"><h1>Evidence queue</h1><p className="muted">High priority actors eligible for a profile capture.</p><ErrorView message={error}/><div className="card tablewrap"><table><thead><tr><th>Actor</th><th>Score</th><th>Priority</th></tr></thead><tbody>{data?.map(a=><tr key={a.id}><td><Link href={`/actors/${a.id}`}>{a.display_name||a.actor_hash.slice(0,12)}</Link></td><td>{a.suspicion_score}</td><td>{a.suspicion_score>=70?"HIGH":"NORMAL"}</td></tr>)}</tbody></table></div></div>}
