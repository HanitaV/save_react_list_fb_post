"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
export function useData<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const reload = useCallback(() => api<T>(path).then(setData).catch(e => setError(String(e))), [path]);
  useEffect(() => { reload(); }, [reload]);
  return { data, error, reload };
}
export function ErrorView({ message }: { message: string }) { return message ? <div className="card text-red-300">{message.includes("403") || message.includes("401") ? "Sign in under Settings to view data." : message}</div> : null; }
