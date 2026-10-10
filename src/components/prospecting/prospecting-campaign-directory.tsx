"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { ProspectCampaignSummary, prospectingApi } from "@/lib/prospecting";

export function ProspectingCampaignDirectory({ slug }: { slug: string }) {
  const [view, setView] = useState<"active" | "archived">("active");
  const [data, setData] = useState<{ results: ProspectCampaignSummary[]; can_manage: boolean } | null>(null);
  const [lists, setLists] = useState<{ id: number; name: string }[]>([]);
  const [selectedLists, setSelectedLists] = useState<number[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const load = async () => {
    const [campaigns, prospectLists] = await Promise.all([
      prospectingApi.campaigns(slug, view),
      prospectingApi.lists(slug, new URLSearchParams({ status: "active", page_size: "100" })),
    ]);
    setData(campaigns);
    setLists(prospectLists.results);
  };
  useEffect(() => {
    let active = true;
    Promise.all([
      prospectingApi.campaigns(slug, view),
      prospectingApi.lists(slug, new URLSearchParams({ status: "active", page_size: "100" })),
    ]).then(([campaigns, prospectLists]) => {
      if (!active) return;
      setData(campaigns); setLists(prospectLists.results); setError("");
    }).catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "Campaigns could not be loaded."); });
    return () => { active = false; };
  }, [slug, view]);
  async function create() {
    try { await prospectingApi.createCampaign(slug, { name, list_ids: selectedLists }); setName(""); setSelectedLists([]); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Campaign could not be created."); }
  }
  async function remove(item: ProspectCampaignSummary) {
    const historical = item.status !== "draft";
    const confirmed = window.confirm(historical
      ? "Archive campaign?\n\nThis campaign will be removed from active campaigns and no future messages will be sent. Historical delivery and recipient records will be preserved."
      : "Delete unused Draft campaign?\n\nThis empty Draft and its editable steps will be permanently removed.");
    if (!confirmed) return;
    try { await prospectingApi.removeCampaign(slug, item.id); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Campaign could not be removed safely."); }
  }
  async function restore(item: ProspectCampaignSummary) {
    if (!window.confirm("Restore campaign container? Historical recipients remain stopped and no messages will be sent automatically.")) return;
    try { await prospectingApi.campaignAction(slug, item.id, "restore"); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Campaign could not be restored."); }
  }
  if (!data) return <Notice text={error || "Loading campaigns…"} error={Boolean(error)} />;
  return <div className="space-y-4">
    {error && <Notice text={error} error />}
    <div className="flex gap-2"><button type="button" onClick={() => setView("active")} className={`rounded-lg border px-4 py-2 text-sm font-semibold ${view === "active" ? "bg-slate-950 text-white" : "bg-white"}`}>Active</button><button type="button" onClick={() => setView("archived")} className={`rounded-lg border px-4 py-2 text-sm font-semibold ${view === "archived" ? "bg-slate-950 text-white" : "bg-white"}`}>Archived</button></div>
    {data.can_manage && view === "active" && <Card className="p-5"><h2 className="font-semibold">Create Draft campaign</h2><div className="mt-3 grid gap-2 sm:grid-cols-[1fr_1fr_auto]"><input aria-label="Campaign name" value={name} onChange={(event) => setName(event.target.value)} className="h-10 rounded-lg border px-3" placeholder="Fall contractor introduction" /><select multiple aria-label="Source prospect lists" value={selectedLists.map(String)} onChange={(event) => setSelectedLists(Array.from(event.target.selectedOptions, (option) => Number(option.value)))} className="min-h-20 rounded-lg border bg-white px-3">{lists.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><button type="button" disabled={!name.trim() || !selectedLists.length} onClick={() => void create()} className="rounded-lg bg-indigo-700 px-4 text-sm font-semibold text-white disabled:opacity-50">Create campaign</button></div></Card>}
    <Card className="overflow-hidden">{data.results.length ? <div className="divide-y">{data.results.map((item) => <div key={item.id} className="flex items-center justify-between gap-4 p-5"><Link href={`/prospecting/campaigns/${item.id}`} className="min-w-0 flex-1 hover:text-indigo-800"><strong>{item.name}</strong><p className="text-sm text-slate-500">{item.step_count} steps · {item.recipient_count} recipients</p></Link><div className="flex items-center gap-2"><span className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold capitalize text-indigo-700">{item.status}</span><Link href={`/prospecting/campaigns/${item.id}`} className="rounded-lg border px-3 py-2 text-sm font-semibold">Open</Link>{data.can_manage && (view === "archived" ? <button type="button" onClick={() => void restore(item)} className="rounded-lg border px-3 py-2 text-sm font-semibold">Restore</button> : <button type="button" onClick={() => void remove(item)} className="rounded-lg border border-red-200 px-3 py-2 text-sm font-semibold text-red-700">{item.status === "draft" ? "Delete" : "Archive"}</button>)}</div></div>)}</div> : <Notice text={view === "active" ? "No active prospecting campaigns." : "No archived campaigns."} />}</Card>
  </div>;
}

function Notice({ text, error = false }: { text: string; error?: boolean }) { return <div role={error ? "alert" : "status"} className={`rounded-xl border p-5 text-sm ${error ? "border-red-200 bg-red-50 text-red-800" : "bg-white text-slate-600"}`}>{text}</div>; }
