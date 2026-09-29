import "./globals.css";
import Link from "next/link";
import type { ReactNode } from "react";

const links = [["Dashboard", "/dashboard"], ["Posts", "/posts"], ["Actors", "/actors"], ["Clusters", "/clusters"], ["Evidence", "/evidence"], ["Settings", "/settings"], ["System", "/system"]];
export default function RootLayout({ children }: { children: ReactNode }) {
  return <html lang="en"><body><div className="min-h-screen md:flex"><aside className="w-full md:w-60 shrink-0 border-r border-slate-800 bg-[#0c1422] p-5"><div className="text-xl font-bold text-white mb-8">Evidence System</div><nav className="flex md:flex-col gap-2 flex-wrap">{links.map(([label, href]) => <Link key={href} className="rounded-lg px-3 py-2 hover:bg-slate-800" href={href}>{label}</Link>)}</nav></aside><main className="flex-1 min-w-0 p-6 md:p-8">{children}</main></div></body></html>;
}
