"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Building2, RefreshCw } from "lucide-react";
import { OrganizationAccessState } from "@/components/organizations/organization-access-state";
import { useOrganization } from "@/components/organizations/organization-provider";
import { Card } from "@/components/ui/card";
import { awardedProjects, type AwardedProjectSummary } from "@/lib/proposals";

export function AwardedDirectory() {
  const { memberships, activeMembership } = useOrganization();
  const [items, setItems] = useState<AwardedProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    if (!activeMembership) return;
    const controller = new AbortController();
    awardedProjects(activeMembership.organization.slug, controller.signal)
      .then((data) => setItems(data.results))
      .catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Awarded projects could not be loaded."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [activeMembership, reload]);
  if (!activeMembership) return <OrganizationAccessState multiple={memberships.length > 1} />;
  return <div className="space-y-5"><header className="flex flex-wrap items-start justify-between gap-3"><div><h1 className="text-2xl font-semibold">Awarded Projects</h1><p className="mt-1 text-sm text-slate-500">Confirmed client awards and immutable project handoff readiness.</p></div><button type="button" onClick={() => { setLoading(true); setError(""); setReload((value) => value + 1); }} disabled={loading} className="rounded-lg border p-2 text-slate-600 disabled:opacity-50" aria-label="Refresh awarded projects"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /></button></header>
    {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
    {loading && !items.length ? <State title="Loading awarded projects…" /> : !items.length ? <State title="No awarded projects" detail="A finalized proposal does not appear here until an authorized user explicitly confirms the client award and transitions the project." /> : <div className="space-y-4">{items.map((item) => <Card key={item.project_id} className="p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-bold uppercase tracking-wide text-emerald-700">{item.project_number}</p><h2 className="mt-1 text-lg font-semibold text-slate-950">{item.project_name}</h2><p className="text-sm text-slate-600">{item.client_name}</p></div><span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-bold text-emerald-800">AWARDED</span></div><div className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4"><Metric label="Accepted amount" value={`${item.currency} ${item.award_amount}`} /><Metric label="Award date" value={item.award_date} /><Metric label="Proposal" value={`${item.proposal_number} · V${item.proposal_version}`} /><Metric label="Handoff" value={item.handoff_ready ? "Ready" : "Not prepared"} /></div>{item.client_reference && <p className="mt-3 text-sm text-slate-600">Client reference: {item.client_reference}</p>}<div className="mt-4"><p className="text-xs font-bold uppercase text-slate-500">Confirmed trade awards</p>{item.trade_awards.length ? <ul className="mt-2 grid gap-2 md:grid-cols-2">{item.trade_awards.map((award) => <li key={`${award.trade}-${award.company}`} className="rounded-lg bg-slate-50 p-3 text-sm"><span className="font-semibold">{award.trade}</span><br />{award.company} · {award.currency} {award.award_amount}</li>)}</ul> : <p className="mt-2 text-sm text-slate-500">No subcontractor awards have been confirmed.</p>}</div><div className="mt-4 flex flex-wrap gap-3"><Link href={`/projects/${item.project_id}/proposal`} className="font-semibold text-blue-700">Final Proposal &amp; Estimate</Link><Link href={`/projects/${item.project_id}/comparisons`} className="font-semibold text-blue-700">Procurement history</Link><Link href={`/projects/${item.project_id}`} className="font-semibold text-blue-700">Open Project</Link></div></Card>)}</div>}
    <p className="text-xs text-slate-500">Award records do not create subcontracts, purchase orders, notifications, or external PM synchronization.</p>
  </div>;
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="rounded-lg border bg-slate-50 p-3"><p className="text-xs font-semibold text-slate-500">{label}</p><p className="mt-1 font-semibold text-slate-900">{value}</p></div>; }
function State({ title, detail }: { title: string; detail?: string }) { return <Card className="flex min-h-56 flex-col items-center justify-center p-8 text-center"><Building2 className="h-8 w-8 text-slate-400" /><h2 className="mt-3 font-semibold">{title}</h2>{detail && <p className="mt-1 max-w-xl text-sm text-slate-500">{detail}</p>}</Card>; }
