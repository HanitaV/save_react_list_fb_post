export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export function token() { return typeof window === "undefined" ? "" : localStorage.getItem("evidence_token") || ""; }
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API}${path}`, { ...options, headers: { Authorization: `Bearer ${token()}`, ...options.headers }, cache: "no-store" });
  if (!response.ok) throw new Error((await response.text()).slice(0, 300));
  return response.json() as Promise<T>;
}
