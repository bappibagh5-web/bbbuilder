"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Building2, ChevronLeft, ChevronRight, Search } from "lucide-react";
import { OrganizationAccessState } from "@/components/organizations/organization-access-state";
import { useOrganization } from "@/components/organizations/organization-provider";
import { Card } from "@/components/ui/card";
import { contractorsApi, type DirectoryResponse } from "@/lib/contractors";

const emptyFilters = { search: "", active: "", trade: "", city: "", province: "", country: "", source: "", contact_ready: "", ordering: "name" };

export function SubcontractorDirectory() {
  const { memberships, activeMembership } = useOrganization();
  const [filters, setFilters] = useState(emptyFilters);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<DirectoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => { const timer = window.setTimeout(() => { setLoading(true); setError(""); setFilters((value) => ({ ...value, search })); setPage(1); }, 250); return () => window.clearTimeout(timer); }, [search]);
  useEffect(() => {
    if (!activeMembership) return;
    const controller = new AbortController();
    const query = new URLSearchParams({ page: String(page), page_size: "25" });
    Object.entries(filters).forEach(([key, value]) => { if (value) query.set(key, value); });
    contractorsApi.directory(activeMembership.organization.slug, query, controller.signal).then(setData).catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Contractors could not be loaded."); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [activeMembership, filters, page]);
  const totalPages = useMemo(() => data ? Math.max(1, Math.ceil(data.count / data.page_size)) : 1, [data]);
  if (!activeMembership) return <OrganizationAccessState multiple={memberships.length > 1} />;
  const summary = data?.summary;
  const hasFilters = Object.entries(filters).some(([key, value]) => key !== "ordering" && value);
  function change(key: keyof typeof filters, value: string) { setLoading(true); setError(""); setFilters((current) => ({ ...current, [key]: value })); setPage(1); }
  return <div className="space-y-5">
    <header><h1 className="text-2xl font-semibold text-slate-950">Subcontractors</h1><p className="mt-1 text-sm text-slate-500">Your organization&apos;s contractor companies, trade capabilities, contacts and bounded project history.</p></header>
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Metric label="Total Companies" value={summary?.total} tone="blue" /><Metric label="Active Companies" value={summary?.active} tone="green" /><Metric label="Usable Contacts" value={summary?.contact_ready} tone="purple" /><Metric label="Trades Covered" value={summary?.trades_covered} tone="amber" /></section>
    <Card><div className="grid gap-3 border-b p-4 md:grid-cols-2 xl:grid-cols-4">
      <label className="relative"><span className="sr-only">Search company or contact</span><Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search company or contact" className="h-10 w-full rounded-lg border pl-9 pr-3 text-sm" /></label>
      <Select label="Trade" value={filters.trade} options={(data?.filters.trades ?? []).map((item) => [item.trade_key, item.trade_label])} onChange={(value) => change("trade", value)} />
      <Select label="City" value={filters.city} options={(data?.filters.cities ?? []).map((item) => [item, item])} onChange={(value) => change("city", value)} />
      <Select label="Province" value={filters.province} options={(data?.filters.provinces ?? []).map((item) => [item, item])} onChange={(value) => change("province", value)} />
      <Select label="Country" value={filters.country} options={(data?.filters.countries ?? []).map((item) => [item, item])} onChange={(value) => change("country", value)} />
      <Select label="Source" value={filters.source} options={[["internal", "Internal network"], ["discovered", "External discovery"]]} onChange={(value) => change("source", value)} />
      <Select label="Status" value={filters.active} options={[["true", "Active"], ["false", "Inactive"]]} onChange={(value) => change("active", value)} />
      <Select label="Contact readiness" value={filters.contact_ready} options={[["true", "Usable contact"], ["false", "Missing contact"]]} onChange={(value) => change("contact_ready", value)} />
      <Select label="Sort" value={filters.ordering} includeAll={false} options={[["name", "Company name"], ["recent", "Recent activity"], ["projects", "Project participation"]]} onChange={(value) => change("ordering", value)} />
    </div>
    {error ? <div role="alert"><State title="Subcontractors unavailable" detail={error} /></div> : loading && !data ? <State title="Loading subcontractors…" /> : !data?.results.length ? <State title={hasFilters ? "No subcontractors match these filters" : "No subcontractors yet"} detail={hasFilters ? "Adjust the search or filters to see other companies." : "Companies appear here when they are added internally or discovered through an explicit project contractor search."} /> : <><div className={`overflow-x-auto transition-opacity ${loading ? "opacity-60" : ""}`}><table className="w-full min-w-[900px] text-left text-sm"><thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500"><tr>{["Company", "Trades", "Location", "Contact readiness", "Projects", "Recent activity"].map((label) => <th key={label} className="px-4 py-3 font-semibold">{label}</th>)}</tr></thead><tbody className="divide-y">{data.results.map((company) => <tr key={company.id} className="hover:bg-slate-50"><td className="px-4 py-4"><Link href={`/subcontractors/${company.id}`} className="font-semibold text-blue-800 hover:underline">{company.display_name}</Link>{company.legal_name && company.legal_name !== company.display_name && <p className="text-xs text-slate-500">{company.legal_name}</p>}<p className="mt-1 text-xs text-slate-500">{company.source_type === "internal" ? "Internal network" : company.external_provider === "google_places" ? "Google" : "External"} · {company.is_active ? "Active" : "Inactive"}</p></td><td className="px-4 py-4"><div className="flex max-w-sm flex-wrap gap-1">{company.trades.length ? company.trades.map((trade) => <span key={trade.trade_key} className="rounded-full bg-blue-50 px-2 py-1 text-xs font-medium text-blue-800">{trade.trade_label}</span>) : <span className="text-slate-400">No trade recorded</span>}</div></td><td className="px-4 py-4">{[company.city, company.province, company.country].filter(Boolean).join(", ") || "Not recorded"}</td><td className="px-4 py-4"><span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${company.usable_contact_count ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-800"}`}>{company.usable_contact_count ? `${company.usable_contact_count} usable` : "Missing contact"}</span>{company.primary_email_ready && <p className="mt-1 text-xs text-slate-500">Primary email ready</p>}</td><td className="px-4 py-4"><strong>{company.project_count}</strong><p className="text-xs text-slate-500">{company.outreach_count} outreach · {company.bid_count} bids</p></td><td className="px-4 py-4 text-slate-600">{company.last_activity_at ? new Date(company.last_activity_at).toLocaleDateString() : "No activity"}</td></tr>)}</tbody></table></div><div className="flex items-center justify-between border-t px-4 py-3 text-sm"><p className="text-slate-500">Page {data.page} of {totalPages} · {data.count} companies</p><div className="flex gap-2"><button type="button" aria-label="Previous page" disabled={!data.previous || loading} onClick={() => { setLoading(true); setError(""); setPage((value) => Math.max(1, value - 1)); }} className="rounded-lg border p-2 disabled:opacity-40"><ChevronLeft className="h-4 w-4" /></button><button type="button" aria-label="Next page" disabled={!data.next || loading} onClick={() => { setLoading(true); setError(""); setPage((value) => value + 1); }} className="rounded-lg border p-2 disabled:opacity-40"><ChevronRight className="h-4 w-4" /></button></div></div></>}
    </Card>
  </div>;
}

function Metric({ label, value, tone }: { label: string; value?: number; tone: "blue" | "green" | "purple" | "amber" }) { const styles = { blue: "bg-blue-50 text-blue-800", green: "bg-emerald-50 text-emerald-800", purple: "bg-violet-50 text-violet-800", amber: "bg-amber-50 text-amber-800" }; return <Card className={`p-4 ${styles[tone]}`}><p className="text-2xl font-semibold">{value ?? "—"}</p><p className="mt-1 text-xs font-medium">{label}</p></Card>; }
function Select({ label, value, options, onChange, includeAll = true }: { label: string; value: string; options: string[][]; onChange: (value: string) => void; includeAll?: boolean }) { return <label><span className="sr-only">{label}</span><select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)} className="h-10 w-full rounded-lg border bg-white px-3 text-sm">{includeAll && <option value="">All {label.toLowerCase()}</option>}{options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select></label>; }
function State({ title, detail }: { title: string; detail?: string }) { return <div className="flex min-h-56 flex-col items-center justify-center p-8 text-center"><Building2 className="h-8 w-8 text-slate-400" /><h2 className="mt-3 font-semibold">{title}</h2>{detail && <p className="mt-1 max-w-xl text-sm text-slate-500">{detail}</p>}</div>; }
