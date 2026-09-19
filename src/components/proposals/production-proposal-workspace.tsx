"use client";

import { useEffect, useState } from "react";
import { Calculator, FileText, History, LockKeyhole, Plus } from "lucide-react";
import type { OrganizationMembership } from "@/lib/auth";
import type { ProductionProject } from "@/lib/projects";
import { proposalsApi, type ProposalWorkspace } from "@/lib/proposals";
import { Card } from "@/components/ui/card";

export function ProductionProposalWorkspace({ project, membership }: { project: ProductionProject; membership: OrganizationMembership }) {
  const [workspace, setWorkspace] = useState<ProposalWorkspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const slug = membership.organization.slug;

  useEffect(() => {
    const controller = new AbortController();
    proposalsApi.workspace(slug, project.id, controller.signal)
      .then(setWorkspace)
      .catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Proposal preparation could not be loaded."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [project.id, slug]);

  async function mutate(action: () => Promise<ProposalWorkspace>) {
    setBusy(true); setError("");
    try { setWorkspace(await action()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The request could not be completed."); }
    finally { setBusy(false); }
  }

  if (loading) return <State title="Loading proposal preparation…" detail="Retrieving the project estimate and proposal history." />;
  if (!workspace) return <State title="Proposal preparation unavailable" detail={error || "The request could not be completed."} error />;

  const estimateVersion = workspace.estimate?.versions.at(-1);
  const proposalVersion = workspace.proposal?.versions.at(-1);
  return <div className="space-y-5">
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div><div className="flex items-center gap-2"><span className="rounded-full bg-violet-100 px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide text-violet-700">M4 foundation</span><span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-600">Draft preparation only</span></div><h2 className="mt-3 text-xl font-semibold text-slate-950">Estimate &amp; Proposal</h2><p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600">Create versioned preparation records for this client proposal. Pricing calculations, selected-bid assembly, PDF generation, finalization, and awards are intentionally not active yet.</p></div>{workspace.can_edit && !workspace.estimate && <button disabled={busy} onClick={() => void mutate(() => proposalsApi.createEstimate(slug, project.id))} className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-[#173f5f] px-4 text-sm font-semibold text-white shadow-sm hover:bg-[#0f3049] disabled:opacity-50"><Plus className="h-4 w-4" />Start proposal preparation</button>}</div>
    {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
    {!workspace.estimate ? <State title="No estimate has been started" detail={workspace.can_edit ? "Start proposal preparation to create the project Estimate and its first Draft version." : "An Admin or Estimator can start the first Draft estimate version."} /> : <>
      <div className="grid gap-4 lg:grid-cols-2"><SummaryCard icon={<Calculator />} title="Internal estimate" name={workspace.estimate.title} status={estimateVersion?.status_label ?? "Draft"} version={estimateVersion?.version ?? 1} detail="Stable estimate identity with append-only Draft versions." />{workspace.proposal ? <SummaryCard icon={<FileText />} title="Client proposal" name={workspace.proposal.title} status={proposalVersion?.status_label ?? "Draft"} version={proposalVersion?.version ?? 1} detail={`Bound to Estimate V${proposalVersion?.estimate_version ?? estimateVersion?.version ?? 1}.`} /> : <Card className="border-dashed border-violet-200 bg-violet-50/30 p-5"><FileText className="h-6 w-6 text-violet-600" /><h3 className="mt-3 font-semibold text-slate-900">Client proposal not created</h3><p className="mt-1 text-sm leading-6 text-slate-600">Create a Draft proposal explicitly from the current exact Estimate version.</p>{workspace.can_edit && estimateVersion && <button disabled={busy} onClick={() => void mutate(() => proposalsApi.createProposal(slug, project.id, estimateVersion.id))} className="mt-4 inline-flex h-9 items-center gap-2 rounded-lg bg-violet-700 px-3 text-sm font-semibold text-white disabled:opacity-50"><Plus className="h-4 w-4" />Create Draft proposal</button>}</Card>}</div>
      <Card className="border-slate-200 p-5"><div className="flex items-start gap-3"><div className="rounded-lg bg-slate-100 p-2 text-slate-600"><History className="h-5 w-5" /></div><div className="min-w-0 flex-1"><h3 className="font-semibold text-slate-900">Version history</h3><p className="mt-1 text-sm text-slate-500">Earlier versions remain preserved; new work creates a successor instead of rewriting history.</p><div className="mt-4 grid gap-4 lg:grid-cols-2"><VersionList title="Estimate versions" versions={workspace.estimate.versions.map((item) => ({ ...item, binding: "Internal estimate draft" }))} /><VersionList title="Proposal versions" versions={(workspace.proposal?.versions ?? []).map((item) => ({ ...item, binding: `Estimate V${item.estimate_version}` }))} /></div></div></div></Card>
      {workspace.can_edit && <div className="flex flex-wrap gap-2">{workspace.proposal ? <><button disabled={busy} onClick={() => void mutate(() => proposalsApi.createEstimateVersion(slug, project.id, workspace.estimate!.id))} className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 disabled:opacity-50">New Estimate draft</button>{estimateVersion && <button disabled={busy} onClick={() => void mutate(() => proposalsApi.createProposalVersion(slug, project.id, workspace.proposal!.id, estimateVersion.id))} className="rounded-lg border border-violet-200 bg-white px-3 py-2 text-sm font-semibold text-violet-700 disabled:opacity-50">New Proposal draft from Estimate V{estimateVersion.version}</button>}</> : null}</div>}
    </>}
    <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs text-slate-500"><LockKeyhole className="h-4 w-4 text-emerald-600" />This foundation creates no pricing totals, PDFs, final approvals, awards, subcontracts, or purchase orders.</div>
  </div>;
}

function SummaryCard({ icon, title, name, status, version, detail }: { icon: React.ReactNode; title: string; name: string; status: string; version: number; detail: string }) { return <Card className="border-slate-200 p-5"><div className="flex items-center justify-between"><span className="rounded-lg bg-blue-50 p-2 text-blue-700">{icon}</span><span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-bold text-amber-800">{status}</span></div><p className="mt-4 text-xs font-bold uppercase tracking-wide text-slate-500">{title}</p><h3 className="mt-1 font-semibold text-slate-950">{name}</h3><p className="mt-2 text-sm text-slate-600">Version {version} · {detail}</p></Card>; }
function VersionList({ title, versions }: { title: string; versions: Array<{ id: number; version: number; status_label: string; binding: string }> }) { return <div><h4 className="text-xs font-bold uppercase tracking-wide text-slate-500">{title}</h4><div className="mt-2 space-y-2">{versions.length ? versions.map((item) => <div key={item.id} className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm"><span className="font-semibold text-slate-800">V{item.version} · {item.status_label}</span><span className="text-xs text-slate-500">{item.binding}</span></div>) : <p className="text-sm text-slate-500">None yet</p>}</div></div>; }
function State({ title, detail, error = false }: { title: string; detail: string; error?: boolean }) { return <section className={`flex min-h-56 flex-col items-center justify-center rounded-xl border border-dashed bg-white p-6 text-center ${error ? "border-red-200" : "border-slate-300"}`}><FileText className={`h-6 w-6 ${error ? "text-red-500" : "text-slate-400"}`} /><h3 className="mt-3 font-semibold text-slate-900">{title}</h3><p className="mt-1 max-w-lg text-sm leading-6 text-slate-500">{detail}</p></section>; }
