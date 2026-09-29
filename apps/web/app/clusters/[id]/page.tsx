"use client";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { ReactFlow, Background, Controls, type Node, type Edge } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useData, ErrorView } from "@/components/Load";

type SharedEdge = { source:string; target:string; weight:number; jaccard:number; shared_post_ids?:string[] };
type Cluster = { id:string; type:string; confidence:number; metadata:{ post_ids?:string[]; edges?:SharedEdge[] }; members:{ actor_id:string; score:number }[] };

export default function ClusterDetail() {
  const id = useParams().id as string;
  const { data, error } = useData<Cluster>(`/api/clusters/${id}`);
  const [minimum, setMinimum] = useState(2);
  const [post, setPost] = useState("ALL");
  const { nodes, edges } = useMemo(() => {
    if (!data) return { nodes: [] as Node[], edges: [] as Edge[] };
    const nodes: Node[] = data.members.map((member, index) => ({
      id: member.actor_id,
      position: { x: (index % 8) * 150, y: Math.floor(index / 8) * 110 },
      data: { label: member.actor_id.slice(0, 8) },
    }));
    const edges: Edge[] = (data.metadata.edges || [])
      .filter(edge => edge.weight >= minimum && (post === "ALL" || edge.shared_post_ids?.includes(post)))
      .map((edge, index) => ({
        id: String(index), source: edge.source, target: edge.target,
        label: `${edge.weight} shared`, style: { stroke: "#6da5ff" },
      }));
    return { nodes, edges };
  }, [data, minimum, post]);
  return <div className="stack">
    <h1>Cluster graph</h1><ErrorView message={error}/>
    <div className="card">
      <div className="flex gap-3 mb-4">
        <label>Minimum shared posts <input type="number" min="1" value={minimum} onChange={event => setMinimum(Number(event.target.value))}/></label>
        <select value={post} onChange={event => setPost(event.target.value)}><option>ALL</option>{data?.metadata.post_ids?.map(value => <option key={value}>{value}</option>)}</select>
      </div>
      <p className="muted mb-3">{data?.type} · {data?.members.length} actors · {edges.length} visible connections</p>
      <div style={{ height: 550 }}><ReactFlow nodes={nodes} edges={edges} fitView><Background/><Controls/></ReactFlow></div>
    </div>
  </div>;
}
