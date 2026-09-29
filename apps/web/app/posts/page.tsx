"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { useData, ErrorView } from "@/components/Load";

type Post = {
  id: string;
  url: string;
  status: string;
  interaction_count: number;
  last_scanned_at: string | null;
};

type ImportResult = { inserted: number; scans?: number; truncated_scans?: number };

export default function Posts() {
  const { data, error, reload } = useData<Post[]>("/api/posts");
  const [url, setUrl] = useState("");
  const [message, setMessage] = useState("");
  const [uploading, setUploading] = useState(false);

  async function add() {
    try {
      await api("/api/posts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ urls: url.split(/\s+/).filter(Boolean) }),
      });
      setUrl("");
      reload();
    } catch (error) {
      setMessage(String(error));
    }
  }

  async function upload(file: File, kind: "csv" | "extension") {
    const body = new FormData();
    body.append("file", file);
    setUploading(true);
    setMessage("");
    try {
      const result = await api<ImportResult>(`/api/import/${kind}`, { method: "POST", body });
      reload();
      setMessage(kind === "extension"
        ? `Đã nhập ${result.inserted} lượt tương tác từ ${result.scans ?? 0} bài quét${result.truncated_scans ? `; ${result.truncated_scans} bài chỉ có dữ liệu một phần` : ""}. Thời gian hiển thị là lúc quét, không phải lúc bấm like.`
        : `Đã nhập ${result.inserted} lượt tương tác từ CSV.`);
    } catch (error) {
      setMessage(String(error));
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="stack">
      <div><h1>Posts</h1><p className="muted">Add monitored URLs and import authorized interaction data.</p></div>
      <ErrorView message={error} />
      <div className="card flex gap-2 flex-wrap">
        <input className="flex-1" placeholder="https://www.facebook.com/..." value={url} onChange={event => setUrl(event.target.value)} />
        <button onClick={add}>Add URLs</button>
        <label className="rounded-lg border border-slate-600 p-2 cursor-pointer">
          Import CSV
          <input type="file" accept=".csv,text/csv" className="hidden" disabled={uploading} onChange={event => { const file = event.target.files?.[0]; if (file) void upload(file, "csv"); event.target.value = ""; }} />
        </label>
        <label className="rounded-lg border border-slate-600 p-2 cursor-pointer">
          Import extension JSON
          <input type="file" accept=".json,application/json" className="hidden" disabled={uploading} onChange={event => { const file = event.target.files?.[0]; if (file) void upload(file, "extension"); event.target.value = ""; }} />
        </label>
      </div>
      {message && <p role="status">{message}</p>}
      <div className="card tablewrap">
        <table>
          <thead><tr><th>Post</th><th>Status</th><th>Interactions</th><th>Scanned</th></tr></thead>
          <tbody>{data?.map(post => <tr key={post.id}><td><Link href={`/posts/${post.id}`}>{post.url}</Link></td><td>{post.status}</td><td>{post.interaction_count}</td><td>{post.last_scanned_at || "—"}</td></tr>)}</tbody>
        </table>
      </div>
    </div>
  );
}
