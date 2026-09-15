"use client";

import { useEffect, useState } from "react";
import { bidsApi, type QuoteRecipientChoice, type QuoteSubmission } from "@/lib/bids";
import type { OrganizationMembership } from "@/lib/auth";
import type { ProductionProject } from "@/lib/projects";
import { Card } from "@/components/ui/card";

export function ProductionBidsModule({ project, membership }: { project: ProductionProject; membership: OrganizationMembership }) {
  const slug = membership.organization.slug;
  const canRecord = project.is_active && (membership.role === "admin" || membership.role === "estimator_operator");
  const [quotes, setQuotes] = useState<QuoteSubmission[]>([]);
  const [recipients, setRecipients] = useState<QuoteRecipientChoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [recipientId, setRecipientId] = useState(0);
  const [receivedAt, setReceivedAt] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [note, setNote] = useState("");
  const [requestKey, setRequestKey] = useState(() => crypto.randomUUID());

  async function refresh() {
    const list = await bidsApi.list(slug, project.id);
    setQuotes(list.submissions);
    setRecipients(list.recipient_choices);
  }
  useEffect(() => {
    let active = true;
    bidsApi.list(slug, project.id)
      .then((list) => { if (active) { setQuotes(list.submissions); setRecipients(list.recipient_choices); } })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "Quote intake could not be loaded."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [slug, project.id]);

  async function upload() {
    if (!recipientId || !receivedAt || files.length === 0) return;
    setBusy(true); setError("");
    try {
      await bidsApi.upload(slug, project.id, recipientId, new Date(receivedAt).toISOString(), files, note, requestKey);
      await refresh(); setFiles([]); setNote(""); setReceivedAt(""); setRequestKey(crypto.randomUUID());
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Quote upload could not be completed."); }
    finally { setBusy(false); }
  }
  async function download(submission: QuoteSubmission, attachment: QuoteSubmission["attachments"][number]) {
    setError("");
    try {
      const blob = await bidsApi.download(slug, project.id, submission.id, attachment.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a"); link.href = url; link.download = attachment.filename; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The private attachment could not be opened."); }
  }
  return <div className="space-y-5">
    <div><span className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-bold uppercase text-indigo-700">Bid inbox</span><h2 className="mt-3 text-xl font-semibold text-slate-950">Received trade quotes</h2><p className="mt-1 text-sm text-slate-600">Store the original quote files against the exact invitation and Ready scope version. This page does not compare or approve pricing.</p></div>
    {error && <Card className="border-red-200 bg-red-50 p-4 text-sm text-red-800" role="alert">{error}</Card>}
    {canRecord && <Card className="space-y-3 p-5"><h3 className="font-semibold">Record a received quote</h3><p className="text-sm text-slate-600">Choose the invitation, received time, and original files. Nothing is sent to the contractor.</p>
      <select aria-label="Invitation recipient" value={recipientId} onChange={(event) => setRecipientId(Number(event.target.value))} className="w-full rounded-lg border p-2"><option value={0}>Select invitation recipient</option>{recipients.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select>
      <label className="block text-sm">Received at<input type="datetime-local" value={receivedAt} onChange={(event) => setReceivedAt(event.target.value)} className="mt-1 block rounded-lg border p-2" /></label>
      <label className="block text-sm">Original quote files<input type="file" multiple accept=".pdf,.xls,.xlsx,.doc,.docx,.csv,.png,.jpg,.jpeg" onChange={(event) => setFiles(Array.from(event.target.files ?? []))} className="mt-1 block text-sm" /></label>
      <textarea aria-label="Intake note" value={note} onChange={(event) => setNote(event.target.value)} placeholder="Optional intake note" className="w-full rounded-lg border p-2 text-sm" />
      <button type="button" disabled={busy || !recipientId || !receivedAt || files.length === 0} onClick={() => void upload()} className="rounded-lg bg-[#173f5f] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Record Quote</button>
    </Card>}
    {loading ? <Card className="p-5 text-sm">Loading received quotes…</Card> : quotes.length === 0 ? <Card className="p-5 text-sm text-slate-600">No quotes have been recorded for this project.</Card> : quotes.map((quote) => <Card key={quote.id} className="p-5"><div className="flex flex-wrap items-start justify-between gap-2"><div><h3 className="font-semibold text-slate-950">{quote.trade} · {quote.company_name}</h3><p className="text-sm text-slate-600">{quote.source === "inbound_email" ? "Received email attachment" : "Manual quote upload"} · {new Date(quote.received_at).toLocaleString()} · Exact scope version #{quote.scope_version_id} · Campaign #{quote.campaign_id}, Batch #{quote.batch_id}</p></div><span className="rounded-full bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-700">Received</span></div><ul className="mt-3 space-y-2">{quote.attachments.map((attachment) => <li key={attachment.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-2 text-sm"><span>{attachment.filename} · {(attachment.byte_size / 1024).toFixed(1)} KB</span><button type="button" onClick={() => void download(quote, attachment)} className="font-semibold text-blue-700">Download privately</button></li>)}</ul></Card>)}
  </div>;
}
