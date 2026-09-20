"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Mail, Search } from "lucide-react";
import { OrganizationAccessState } from "@/components/organizations/organization-access-state";
import { useOrganization } from "@/components/organizations/organization-provider";
import { Card } from "@/components/ui/card";
import { procurementDirectoriesApi, type CampaignDirectoryResponse } from "@/lib/procurement-directories";

export function CampaignDirectory() {
  const { memberships, activeMembership } = useOrganization();
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState({ search: "", trade: "", status: "" });
  const [page, setPage] = useState(1);
  const [data, setData] = useState<CampaignDirectoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => { const timer = window.setTimeout(() => { setLoading(true); setError(""); setFilters((value) => ({ ...value, search })); setPage(1); }, 250); return () => window.clearTimeout(timer); }, [search]);
  useEffect(() => {
    if (!activeMembership) return;
    const controller = new AbortController();
    const query = new URLSearchParams({ page: String(page), page_size: "25" });
    Object.entries(filters).forEach(([key, value]) => value && query.set(key, value));
    procurementDirectoriesApi.campaigns(activeMembership.organization.slug, query, controller.signal).then(setData).catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Campaigns could not be loaded."); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [activeMembership, filters, page]);

  if (!activeMembership) return <OrganizationAccessState multiple={memberships.length > 1} />;
  const change = (key: "trade" | "status", value: string) => { setLoading(true); setError(""); setFilters((current) => ({ ...current, [key]: value })); setPage(1); };
  const filtered = Boolean(filters.search || filters.trade || filters.status);
  return <div className="space-y-5">
    <header><h1 className="text-2xl font-semibold">Outreach Campaigns</h1><p className="mt-1 text-sm text-slate-500">Organization-wide bid invitation activity linked to each exact project trade package.</p></header>
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Metric label="Total Campaigns" value={data?.summary.total} /><Metric label="Draft" value={data?.summary.draft} /><Metric label="Prepared" value={data?.summary.prepared} /><Metric label="Closed" value={data?.summary.closed} /></section>
    <Card><div className="grid gap-3 border-b p-4 md:grid-cols-3"><label className="relative"><span className="sr-only">Search campaigns</span><Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search project or trade" className="h-10 w-full rounded-lg border pl-9 pr-3" /></label><Select label="Trade" value={filters.trade} options={(data?.filters.trades ?? []).map((item) => [item.trade_key, item.trade_category])} onChange={(value) => change("trade", value)} /><Select label="Status" value={filters.status} options={(data?.filters.statuses ?? []).map((item) => [item.value, item.label])} onChange={(value) => change("status", value)} /></div>
      {error ? <State title="Campaigns unavailable" detail={error} /> : loading && !data ? <State title="Loading outreach campaigns…" /> : !data?.results.length ? <State title={filtered ? "No campaigns match these filters" : "No outreach campaigns yet"} /> : <><div className={`overflow-x-auto ${loading ? "opacity-60" : ""}`}><table className="w-full min-w-[1100px] text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr>{["Project", "Trade / Scope", "Campaign Lifecycle", "Recipients", "Delivery", "Responses", "Qualification", "Quotes", "Created", "Action"].map((heading) => <th key={heading} className="px-4 py-3">{heading}</th>)}</tr></thead><tbody className="divide-y">{data.results.map((item) => <tr key={item.id}><td className="px-4 py-3"><strong>{item.project_number}</strong><p className="text-xs text-slate-500">{item.project_name}</p></td><td className="px-4 py-3">{item.trade}<p className="text-xs text-slate-500">Campaign #{item.id} · Scope V{item.scope_version_id}</p></td><td className="px-4 py-3 capitalize">{item.status}<p className="text-xs normal-case text-slate-500">Setup lifecycle; delivery counts shown separately</p></td><td className="px-4 py-3">{item.recipient_count}</td><td className="px-4 py-3">{item.invited_count} invited · {item.delivered_count} delivered</td><td className="px-4 py-3">{item.responded_count}</td><td className="px-4 py-3">{item.qualified_count} qualified · {item.not_reviewed_count} not reviewed</td><td className="px-4 py-3">{item.bid_count}</td><td className="px-4 py-3">{new Date(item.created_at).toLocaleDateString()}</td><td className="px-4 py-3"><Link href={item.project_url} className="font-semibold text-blue-700 hover:underline">Open Outreach</Link></td></tr>)}</tbody></table></div><Pager data={data} loading={loading} setPage={(update) => { setLoading(true); setError(""); setPage(update); }} /></>}
    </Card>
  </div>;
}

function Metric({ label, value }: { label: string; value?: number }) { return <Card className="bg-blue-50 p-4 text-blue-900"><p className="text-2xl font-semibold">{value ?? "—"}</p><p className="text-xs font-medium">{label}</p></Card>; }
function Select({ label, value, options, onChange }: { label: string; value: string; options: string[][]; onChange: (value: string) => void }) { return <select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)} className="h-10 rounded-lg border bg-white px-3"><option value="">All {label.toLowerCase()}</option>{options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select>; }
function State({ title, detail }: { title: string; detail?: string }) { return <div className="flex min-h-56 flex-col items-center justify-center p-8 text-center"><Mail className="h-8 w-8 text-slate-400" /><h2 className="mt-3 font-semibold">{title}</h2>{detail && <p className="mt-1 text-sm text-slate-500">{detail}</p>}</div>; }
function Pager({ data, loading, setPage }: { data: CampaignDirectoryResponse; loading: boolean; setPage: React.Dispatch<React.SetStateAction<number>> }) { return <div className="flex items-center justify-between border-t px-4 py-3 text-sm"><span>Page {data.page} · {data.count} campaigns</span><div className="flex gap-2"><button aria-label="Previous page" disabled={!data.previous || loading} onClick={() => setPage((value) => Math.max(1, value - 1))} className="rounded border p-2 disabled:opacity-40"><ChevronLeft className="h-4 w-4" /></button><button aria-label="Next page" disabled={!data.next || loading} onClick={() => setPage((value) => value + 1)} className="rounded border p-2 disabled:opacity-40"><ChevronRight className="h-4 w-4" /></button></div></div>; }
