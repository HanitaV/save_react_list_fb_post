"use client";
import Link from "next/link";
import { useData, ErrorView } from "@/components/Load";
type Cluster={id:string;type:string;confidence:number;member_count:number};
export default function Clusters(){const {data,error}=useData<Cluster[]>("/api/clusters");return <div className="stack"><h1>Clusters</h1><ErrorView message={error}/><div className="card tablewrap"><table><thead><tr><th>Type</th><th>Members</th><th>Confidence</th></tr></thead><tbody>{data?.map(c=><tr key={c.id}><td><Link href={`/clusters/${c.id}`}>{c.type}</Link></td><td>{c.member_count}</td><td>{Math.round(c.confidence*100)}%</td></tr>)}</tbody></table></div></div>}
