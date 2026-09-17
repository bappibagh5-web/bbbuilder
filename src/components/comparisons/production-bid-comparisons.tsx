"use client";

import { useEffect, useMemo, useState } from "react";
import type { OrganizationMembership } from "@/lib/auth";
import { bidComparisonsApi, type ComparisonDetail, type ComparisonSummary, type ReadyBidChoice } from "@/lib/bid-comparisons";
import { displayBidMoney } from "@/lib/bid-money";
import { bidsApi } from "@/lib/bids";
import type { ProductionProject } from "@/lib/projects";
import { Card } from "@/components/ui/card";
import { HumanBidReview } from "@/components/comparisons/human-bid-review";

const coverageLabels: Record<string, string> = { included: "Confirmed included", excluded: "Confirmed excluded", qualified: "Qualified / conditional", not_addressed: "Not addressed", needs_clarification: "Needs clarification" };
const categoryLabels: Record<string, string> = { scope_gap: "Scope gap", exclusion_normalization: "Exclusion normalization", alternate_option: "Alternate / option", allowance_normalization: "Allowance normalization", permit_fee: "Permit / fee", other: "Other estimator adjustment" };

export function ProductionBidComparisons({ project, membership }: { project: ProductionProject; membership: OrganizationMembership }) {
  const slug = membership.organization.slug;
  const canEdit = project.is_active && (membership.role === "admin" || membership.role === "estimator_operator");
  const [comparisons, setComparisons] = useState<ComparisonSummary[]>([]);
  const [choices, setChoices] = useState<ReadyBidChoice[]>([]);
  const [detail, setDetail] = useState<ComparisonDetail | null>(null);
  const [scopeVersionId, setScopeVersionId] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    const data = await bidComparisonsApi.list(slug, project.id);
    setComparisons(data.comparisons); setChoices(data.ready_revisions);
  }
  useEffect(() => {
    const controller = new AbortController();
    bidComparisonsApi.list(slug, project.id, controller.signal).then((data) => { setComparisons(data.comparisons); setChoices(data.ready_revisions); }).catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Bid comparisons could not be loaded."); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [slug, project.id]);

  const scopeChoices = useMemo(() => [...new Map(choices.map((item) => [item.scope_version_id, item])).values()], [choices]);
  async function mutate(action: () => Promise<ComparisonDetail | void>, refreshDetail = true) {
    setBusy(true); setError("");
    try { const result = await action(); if (result) setDetail(result); else if (refreshDetail && detail) setDetail(await bidComparisonsApi.detail(slug, project.id, detail.id)); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The comparison could not be updated."); }
    finally { setBusy(false); }
  }
  async function download(entry: ComparisonDetail["entries"][number], attachment: { id: number; filename: string }) {
    try { const blob = await bidsApi.download(slug, project.id, entry.submission_id, attachment.id); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = attachment.filename; link.click(); setTimeout(() => URL.revokeObjectURL(url), 60_000); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The source quote could not be opened."); }
  }

  if (detail) return <ComparisonWorkspace detail={detail} choices={choices} canEdit={canEdit} busy={busy} error={error} slug={slug} projectId={project.id} back={() => { setDetail(null); setError(""); }} add={(id) => void mutate(() => bidComparisonsApi.addEntry(slug, project.id, detail.id, id))} remove={(id) => void mutate(() => bidComparisonsApi.removeEntry(slug, project.id, detail.id, id))} saveNotes={(notes) => void mutate(() => bidComparisonsApi.updateNotes(slug, project.id, detail.id, notes))} adjust={(entryId, values) => void mutate(() => bidComparisonsApi.addAdjustment(slug, project.id, detail.id, entryId, values))} removeAdjustment={(entryId, id) => void mutate(() => bidComparisonsApi.removeAdjustment(slug, project.id, detail.id, entryId, id))} ready={() => void mutate(() => bidComparisonsApi.ready(slug, project.id, detail.id))} download={download} />;

  return <div className="space-y-5">
    <div><span className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-bold uppercase text-indigo-700">Bid leveling</span><h2 className="mt-3 text-xl font-semibold text-slate-950">Scope-aware bid comparisons</h2><p className="mt-1 text-sm text-slate-600">Explicitly choose human-reviewed Ready bids for the same exact trade scope. BB Builders adjustments never rewrite contractor pricing or make a procurement decision.</p></div>
    {error && <Card className="border-red-200 bg-red-50 p-4 text-sm text-red-800" role="alert">{error}</Card>}
    {canEdit && scopeChoices.length > 0 && <Card className="flex flex-wrap items-end gap-3 p-5"><label className="min-w-72 flex-1 text-sm font-medium">Ready trade scope<select value={scopeVersionId} onChange={(event) => setScopeVersionId(Number(event.target.value))} className="mt-1 w-full rounded-lg border p-2"><option value={0}>Choose exact Ready scope</option>{scopeChoices.map((item) => <option key={item.scope_version_id} value={item.scope_version_id}>{item.trade} · Ready V{item.scope_version} · Scope #{item.scope_version_id}</option>)}</select></label><button type="button" disabled={busy || !scopeVersionId} onClick={() => void mutate(() => bidComparisonsApi.create(slug, project.id, scopeVersionId))} className="rounded-lg bg-[#173f5f] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Create Bid Comparison</button></Card>}
    {loading ? <Card className="p-5 text-sm">Loading comparisons…</Card> : comparisons.length === 0 ? <Card className="p-8 text-center"><h3 className="font-semibold">No bid comparisons yet</h3><p className="mt-2 text-sm text-slate-600">Create a Draft comparison, then explicitly select at least two Ready bidder revisions.</p></Card> : comparisons.map((item) => <Card key={item.id} className="flex flex-wrap items-center justify-between gap-3 p-5"><div><h3 className="font-semibold">{item.trade} · Scope #{item.scope_version_id}</h3><p className="text-sm text-slate-600">Comparison V{item.sequence} · {item.bidder_count} selected bidders · {item.status === "ready" ? "Ready for Human Review" : "Draft"}</p></div><button type="button" onClick={() => void bidComparisonsApi.detail(slug, project.id, item.id).then(setDetail).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Comparison could not be opened."))} className="rounded-lg border border-blue-300 px-3 py-2 text-sm font-semibold text-blue-800">Open Comparison</button></Card>)}
  </div>;
}

function ComparisonWorkspace({ detail, choices, canEdit, busy, error, slug, projectId, back, add, remove, saveNotes, adjust, removeAdjustment, ready, download }: { detail: ComparisonDetail; choices: ReadyBidChoice[]; canEdit: boolean; busy: boolean; error: string; slug: string; projectId: number; back: () => void; add: (id: number) => void; remove: (id: number) => void; saveNotes: (notes: string) => void; adjust: (entryId: number, values: Record<string, unknown>) => void; removeAdjustment: (entryId: number, id: number) => void; ready: () => void; download: (entry: ComparisonDetail["entries"][number], attachment: { id: number; filename: string }) => void }) {
  const [notes, setNotes] = useState(detail.notes);
  const selectedCompanies = new Set(detail.entries.map((item) => item.company_id));
  const eligible = choices.filter((item) => item.scope_version_id === detail.scope_version_id && !selectedCompanies.has(item.company_id));
  return <div className="space-y-5"><button type="button" onClick={back} className="text-sm font-semibold text-blue-700">← All comparisons</button>
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-xl font-semibold">{detail.trade} comparison</h2><p className="text-sm text-slate-600">Exact Ready scope V{detail.scope_version} / #{detail.scope_version_id} · {detail.entries.length} explicitly selected bidders</p></div><span className={`rounded-full px-3 py-1 text-xs font-bold ${detail.status === "ready" ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>{detail.status === "ready" ? "Ready for Human Review" : "Draft"}</span></div>
    {error && <Card className="border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</Card>}
    {detail.status === "draft" && canEdit && <Card className="p-5"><h3 className="font-semibold">Choose Ready bidder revisions</h3><p className="mt-1 text-sm text-slate-600">Nothing is preselected. Historical no-price revisions remain available but are never chosen automatically.</p><div className="mt-3 grid gap-2">{eligible.length === 0 ? <p className="text-sm text-slate-500">No additional eligible companies.</p> : eligible.map((item) => <div key={item.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3 text-sm"><span><strong>{item.company_name}</strong> · Revision {item.revision_sequence} · {displayBidMoney(item.base_bid, item.currency)} · received {new Date(item.received_at).toLocaleDateString()}</span><button type="button" disabled={busy} onClick={() => add(item.id)} className="font-semibold text-blue-700">Add this revision</button></div>)}</div></Card>}
    {detail.entries.length > 0 && <><CommercialTable detail={detail} canEdit={canEdit} busy={busy} remove={remove} download={download} /><ScopeMatrix detail={detail} /><section className="grid gap-4 xl:grid-cols-2">{detail.entries.map((entry) => <AdjustmentCard key={entry.id} entry={entry} draft={detail.status === "draft" && canEdit} busy={busy} adjust={adjust} removeAdjustment={removeAdjustment} />)}</section></>}
    <Card className="p-5"><h3 className="font-semibold">Estimator comparison notes</h3>{detail.status === "draft" && canEdit ? <><textarea value={notes} onChange={(event) => setNotes(event.target.value)} className="mt-2 min-h-24 w-full rounded-lg border p-3 text-sm" placeholder="Record comparison context without changing contractor quote data." /><button type="button" disabled={busy || notes === detail.notes} onClick={() => saveNotes(notes)} className="mt-2 rounded-lg border border-blue-300 px-3 py-2 text-sm font-semibold text-blue-800 disabled:opacity-50">Save notes</button></> : <p className="mt-2 whitespace-pre-wrap text-sm text-slate-600">{detail.notes || "No comparison notes."}</p>}</Card>
    {detail.status === "draft" && canEdit && <Card className="flex flex-wrap items-center justify-between gap-3 p-5"><div><h3 className="font-semibold">Human review gate</h3><p className="text-sm text-slate-600">This freezes selected revisions and BB Builders leveling adjustments. The separate human review records the procurement decision.</p></div><button type="button" disabled={busy || detail.entries.length < 2} onClick={ready} className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Mark Ready for Human Review</button></Card>}
    {detail.status === "ready" && <HumanBidReview slug={slug} projectId={projectId} comparisonId={detail.id} canEdit={canEdit} />}
  </div>;
}

function CommercialTable({ detail, canEdit, busy, remove, download }: { detail: ComparisonDetail; canEdit: boolean; busy: boolean; remove: (id: number) => void; download: (entry: ComparisonDetail["entries"][number], attachment: { id: number; filename: string }) => void }) {
  return <Card className="overflow-x-auto"><table className="w-full min-w-[850px] text-left text-sm"><thead className="bg-slate-50"><tr><th className="p-3">Commercial factor</th>{detail.entries.map((entry) => <th key={entry.id} className="p-3"><div>{entry.company_name}</div><div className="text-xs font-normal text-slate-500">Revision {entry.revision_sequence} · Submission #{entry.submission_id}</div>{detail.status === "draft" && canEdit && <button type="button" disabled={busy} onClick={() => remove(entry.id)} className="mt-1 text-xs text-red-700">Remove</button>}</th>)}</tr></thead><tbody className="divide-y">
    <Row label="Submitted Base Bid" entries={detail.entries} render={(entry) => displayBidMoney(entry.base_bid, entry.currency)} />
    <Row label="Tax treatment" entries={detail.entries} render={(entry) => entry.tax_treatment.replaceAll("_", " ")} />
    <Row label="Bid validity" entries={detail.entries} render={(entry) => entry.validity_days ? `${entry.validity_days} days` : entry.validity_date ?? "Not stated"} />
    <Row label="Schedule" entries={detail.entries} render={(entry) => entry.schedule_text || "Not stated"} />
    <Row label="Commercial terms" entries={detail.entries} render={(entry) => <ul className="space-y-2">{entry.commercial_items.map((item) => <li key={item.id}><strong>{item.title}</strong>{item.kind === "condition" ? item.detail ? ` — ${item.detail}` : "" : <>: {item.amount ? displayBidMoney(item.amount, item.currency) : item.treatment.replaceAll("_", " ") || item.description}</>}{item.included_in_base === "yes" ? " · Included in Base Bid" : ""}{item.scope_item_id === null ? " · Unmapped" : ""}{item.evidence.map((source, index) => <details key={index} className="text-xs text-slate-500"><summary className="cursor-pointer text-blue-700">{source.page_number ? `Source page ${source.page_number}` : "Source evidence"}</summary><blockquote className="mt-1 whitespace-pre-wrap border-l-2 border-slate-200 pl-2">{source.excerpt}</blockquote></details>)}</li>)}</ul>} />
    <Row label="Source quote" entries={detail.entries} render={(entry) => <div className="space-y-1">{entry.attachments.map((item) => <button type="button" key={item.id} onClick={() => download(entry, item)} className="block font-semibold text-blue-700">{item.filename}</button>)}</div>} />
    <Row label="Attention" entries={detail.entries} render={(entry) => entry.attention_flags.length ? entry.attention_flags.join(" · ") : "No rule-based flags"} />
  </tbody></table></Card>;
}
function Row({ label, entries, render }: { label: string; entries: ComparisonDetail["entries"]; render: (entry: ComparisonDetail["entries"][number]) => React.ReactNode }) { return <tr><th className="p-3 align-top">{label}</th>{entries.map((entry) => <td key={entry.id} className="p-3 align-top">{render(entry)}</td>)}</tr>; }

function ScopeMatrix({ detail }: { detail: ComparisonDetail }) {
  return <Card className="overflow-hidden"><details><summary className="cursor-pointer p-5 font-semibold">Scope leveling matrix · {detail.scope_items.length} exact scope items</summary><div className="overflow-x-auto"><table className="w-full min-w-[850px] text-left text-sm"><thead className="bg-slate-50"><tr><th className="p-3">Scope item</th>{detail.entries.map((entry) => <th key={entry.id} className="p-3">{entry.company_name}</th>)}</tr></thead><tbody className="divide-y">{detail.scope_items.map((item) => <tr key={item.id}><th className="p-3">{item.sequence}. {item.title}</th>{detail.entries.map((entry) => { const coverage = entry.coverage[String(item.id)]; return <td key={entry.id} className="p-3"><span className="font-medium">{coverageLabels[coverage.state] ?? coverage.state}</span>{!coverage.recorded && <div className="text-xs text-amber-700">No recorded coverage; not assumed excluded.</div>}{coverage.wording && <div className="text-xs text-slate-500">{coverage.wording}</div>}</td>; })}</tr>)}</tbody></table></div></details></Card>;
}

function AdjustmentCard({ entry, draft, busy, adjust, removeAdjustment }: { entry: ComparisonDetail["entries"][number]; draft: boolean; busy: boolean; adjust: (entryId: number, values: Record<string, unknown>) => void; removeAdjustment: (entryId: number, id: number) => void }) {
  const [direction, setDirection] = useState("add"); const [amount, setAmount] = useState(""); const [category, setCategory] = useState("scope_gap"); const [description, setDescription] = useState("");
  return <Card className="p-5"><h3 className="font-semibold">{entry.company_name}</h3><p className="mt-1 text-sm">Source Base Bid: {displayBidMoney(entry.base_bid, entry.currency)}</p><div className="mt-3 space-y-2">{entry.adjustments.map((item) => <div key={item.id} className="flex justify-between gap-2 rounded-lg bg-slate-50 p-2 text-sm"><span>{item.direction.toUpperCase()} {displayBidMoney(item.amount, item.currency)} · {categoryLabels[item.category]} · {item.description}</span>{draft && <button type="button" disabled={busy} onClick={() => removeAdjustment(entry.id, item.id)} className="text-red-700">Remove</button>}</div>)}</div><p className="mt-3 text-sm font-semibold">Evaluated amount: {entry.evaluated_amount ? displayBidMoney(entry.evaluated_amount, entry.currency) : "Unavailable — Base Bid/currency requires confirmation"}</p>{draft && <div className="mt-4 grid gap-2 sm:grid-cols-2"><select aria-label={`${entry.company_name} adjustment direction`} value={direction} onChange={(event) => setDirection(event.target.value)} className="rounded border p-2"><option value="add">ADD</option><option value="deduct">DEDUCT</option></select><input aria-label={`${entry.company_name} adjustment amount`} value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="Amount" className="rounded border p-2" /><select aria-label={`${entry.company_name} adjustment category`} value={category} onChange={(event) => setCategory(event.target.value)} className="rounded border p-2">{Object.entries(categoryLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><input aria-label={`${entry.company_name} adjustment reason`} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Estimator rationale" className="rounded border p-2" /><button type="button" disabled={busy || !amount || !description || !entry.currency} onClick={() => { adjust(entry.id, { direction, amount, category, description, currency: entry.currency }); setAmount(""); setDescription(""); }} className="rounded bg-blue-700 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">Add leveling adjustment</button></div>}<p className="mt-3 text-xs text-slate-500">Alternates, allowances, taxes, fees, and exclusions change this total only through an explicit estimator adjustment.</p></Card>;
}
