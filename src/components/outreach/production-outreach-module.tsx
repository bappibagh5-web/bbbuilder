"use client";

import { useEffect, useState } from "react";
import { Mail, Users } from "lucide-react";

import { Card } from "@/components/ui/card";
import type { OrganizationMembership } from "@/lib/auth";
import { outreachApi, type OutreachRecipient, type OutreachTrade, type OutreachWorkspace, type RFQPreview } from "@/lib/outreach";
import type { ProductionProject } from "@/lib/projects";

export function ProductionOutreachModule({ project, membership }: { project: ProductionProject; membership: OrganizationMembership }) {
  const slug = membership.organization.slug;
  const canPrepare = project.is_active && (membership.role === "admin" || membership.role === "estimator_operator");
  const [workspace, setWorkspace] = useState<OutreachWorkspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<Record<number, RFQPreview>>({});
  const [selectedBatch, setSelectedBatch] = useState<Record<number, number>>({});
  const [selectedContact, setSelectedContact] = useState<Record<number, number>>({});
  const [deadlineDrafts, setDeadlineDrafts] = useState<Record<number, { bid: string; questions: string }>>({});
  const [unassigned, setUnassigned] = useState<{ id: number; from_address: string; subject: string; occurred_at: string; attachment_count: number; content_status: string }[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    outreachApi.workspace(slug, project.id, controller.signal)
      .then(setWorkspace)
      .catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Outreach preparation could not be loaded."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [slug, project.id]);

  useEffect(() => {
    if (membership.role !== "admin") return;
    outreachApi.unassignedResponses(slug).then((result) => setUnassigned(result.responses)).catch(() => {});
  }, [slug, membership.role]);

  async function refresh() { setWorkspace(await outreachApi.workspace(slug, project.id)); }
  async function act(action: () => Promise<void>) {
    setBusy(true); setError(null);
    try { await action(); await refresh(); return true; }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The preparation step could not be completed."); return false; }
    finally { setBusy(false); }
  }

  async function createCampaign(trade: OutreachTrade) {
    await act(async () => { await outreachApi.createCampaign(slug, project.id, trade.scope_package_id, trade.scope_version_id); });
  }
  async function createBatch(trade: OutreachTrade) {
    if (!trade.campaign) return;
    const sequence = Math.max(0, ...trade.campaign.batches.map((batch) => batch.sequence)) + 1;
    await act(async () => {
      const batch = await outreachApi.createBatch(slug, project.id, trade.campaign!.id, sequence);
      setSelectedBatch((current) => ({ ...current, [trade.scope_package_id]: batch.id }));
    });
  }
  async function addRecipient(trade: OutreachTrade, candidateId: number) {
    const batchId = selectedBatch[trade.scope_package_id];
    const contactId = selectedContact[candidateId];
    if (!batchId || !contactId) { setError("Select a batch and a contact before preparing this recipient."); return; }
    await act(async () => { await outreachApi.addRecipient(slug, project.id, batchId, candidateId, contactId); });
  }
  async function openPreview(trade: OutreachTrade) {
    if (!trade.campaign) return;
    setBusy(true); setError(null);
    try { const result = await outreachApi.preview(slug, project.id, trade.campaign.id); setPreview((current) => ({ ...current, [trade.scope_package_id]: result })); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The RFQ preview could not be loaded."); }
    finally { setBusy(false); }
  }
  async function saveSetup(trade: OutreachTrade) {
    if (!trade.campaign) return;
    const draft = deadlineDrafts[trade.campaign.id] ?? { bid: trade.campaign.bid_due_local, questions: trade.campaign.questions_due_local };
    await act(async () => {
      await outreachApi.saveCampaignSetup(slug, project.id, trade.campaign!.id, draft.bid, draft.questions);
      setPreview((current) => { const next = { ...current }; delete next[trade.scope_package_id]; return next; });
    });
  }

  return <div className="space-y-5">
    <div><span className="inline-flex items-center gap-2 rounded-full bg-indigo-50 px-3 py-1 text-xs font-bold uppercase text-indigo-700"><Mail className="h-4 w-4" />Outreach preparation</span><h2 className="mt-3 text-xl font-semibold text-slate-950">Prepare trade invitations</h2><p className="mt-1 text-sm text-slate-600">Selecting a contractor is separate from approving and sending an invitation. Delivery is disabled unless explicitly configured.</p></div>
    {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>}
    {workspace && <Card className="p-4 text-sm text-slate-700"><strong>Email Delivery Status:</strong> {workspace.provider.label}. <strong>Sender Name / From Address:</strong> {workspace.sender.configured ? `${workspace.sender.display_name} <${workspace.sender.from_address}>` : "Not configured in Settings"}. <strong>Reply-To:</strong> {workspace.sender.reply_to || "Not configured"}. Opening this page sends no email.</Card>}
    {membership.role === "admin" && unassigned.length > 0 && <Card className="p-4 text-sm"><h3 className="font-semibold text-amber-900">Unassigned incoming replies · {unassigned.length}</h3><p className="text-slate-600">These replies could not be reliably tied to an invitation. Review them in Resend; no contractor status was changed.</p><ul className="mt-2 space-y-1">{unassigned.map((item) => <li key={item.id}>{item.from_address} · {item.subject} · {new Date(item.occurred_at).toLocaleString()}{item.attachment_count > 0 ? " · Attachments received — bid intake pending" : ""}</li>)}</ul></Card>}
    {loading ? <Card className="p-6 text-sm text-slate-500">Loading Ready trades…</Card> : !workspace || workspace.trades.length === 0 ? <Card className="p-6 text-sm text-slate-600">No Ready trade scopes are available for outreach preparation.</Card> : workspace.trades.map((trade) => {
      const batch = trade.campaign?.batches.find((item) => item.id === selectedBatch[trade.scope_package_id]);
      const delivery = batch?.delivery_readiness ?? { ready: false, blockers: [{ code: "readiness_unavailable", label: "Send readiness is unavailable. Refresh after the backend restarts." }] };
      return <Card key={trade.scope_package_id} className="overflow-hidden border-slate-200 shadow-sm"><div className="flex flex-wrap items-center justify-between gap-3 border-b bg-slate-50 p-5"><div><h3 className="font-semibold text-slate-950">{trade.trade}</h3><p className="mt-1 text-sm text-slate-600">Ready V{trade.scope_version} · {trade.approved_count} contractor{trade.approved_count === 1 ? "" : "s"} approved for outreach</p></div><span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700">Ready scope</span></div><div className="space-y-4 p-5">
        {!trade.campaign ? <div className="flex flex-wrap items-center justify-between gap-3"><p className="text-sm text-slate-600">Create a draft campaign for this exact Ready scope version. No contractor is added automatically.</p>{canPrepare && <button type="button" disabled={busy} onClick={() => void createCampaign(trade)} className="rounded-lg bg-[#173f5f] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Create Draft Campaign</button>}</div> : <><div className="flex flex-wrap items-center gap-3"><span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-bold text-blue-700">Draft campaign #{trade.campaign.id}</span><button type="button" disabled={busy} onClick={() => void openPreview(trade)} className="rounded-lg border border-blue-200 px-3 py-2 text-sm font-semibold text-blue-700">Preview RFQ</button>{canPrepare && <button type="button" disabled={busy} onClick={() => void createBatch(trade)} className="rounded-lg bg-[#173f5f] px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">Create Next Batch</button>}</div>
          <div className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 p-3"><p className="w-full text-xs font-semibold text-slate-600">Campaign Setup · Project Timezone: {trade.campaign.project_timezone}</p><label className="text-xs font-semibold">Bid Deadline<input type="datetime-local" disabled={!canPrepare || busy} value={deadlineDrafts[trade.campaign.id]?.bid ?? trade.campaign.bid_due_local} onChange={(event) => setDeadlineDrafts((current) => ({ ...current, [trade.campaign!.id]: { bid: event.target.value, questions: current[trade.campaign!.id]?.questions ?? trade.campaign!.questions_due_local } }))} className="mt-1 block rounded border p-2" /></label><label className="text-xs font-semibold">Questions Deadline (optional)<input type="datetime-local" disabled={!canPrepare || busy} value={deadlineDrafts[trade.campaign.id]?.questions ?? trade.campaign.questions_due_local} onChange={(event) => setDeadlineDrafts((current) => ({ ...current, [trade.campaign!.id]: { bid: current[trade.campaign!.id]?.bid ?? trade.campaign!.bid_due_local, questions: event.target.value } }))} className="mt-1 block rounded border p-2" /></label>{canPrepare && <button type="button" disabled={busy} onClick={() => void saveSetup(trade)} className="rounded-lg border border-blue-300 px-3 py-2 text-sm font-semibold text-blue-800">Save Campaign Setup</button>}</div>
          {preview[trade.scope_package_id] && <div className="rounded-xl border border-indigo-200 bg-indigo-50/40 p-4"><p className="text-xs font-bold uppercase text-indigo-700">RFQ preview · Template V{preview[trade.scope_package_id].template_version}</p><p className="mt-2 font-semibold text-slate-900">{preview[trade.scope_package_id].subject}</p><pre className="mt-3 whitespace-pre-wrap break-words font-sans text-sm leading-6 text-slate-700">{preview[trade.scope_package_id].body}</pre><p className="mt-3 text-xs text-slate-500">Preview only. No message has been prepared or sent.</p></div>}
          {trade.campaign.batches.length > 0 && <div><label className="text-xs font-semibold text-slate-700">Invitation batch<select aria-label={`Invitation batch for ${trade.trade}`} value={selectedBatch[trade.scope_package_id] ?? ""} onChange={(event) => setSelectedBatch((current) => ({ ...current, [trade.scope_package_id]: Number(event.target.value) }))} className="mt-1 block h-10 rounded-lg border bg-white px-3 text-sm"><option value="">Select a batch</option>{trade.campaign.batches.map((item) => <option key={item.id} value={item.id}>Batch {item.sequence} · {item.recipients.length} recipient{item.recipients.length === 1 ? "" : "s"}</option>)}</select></label></div>}
          {batch && <><div className="flex items-center gap-2 text-sm font-semibold text-slate-800"><Users className="h-4 w-4" />Batch {batch.sequence} · {batch.recipients.length} recipient{batch.recipients.length === 1 ? "" : "s"}</div>{batch.recipients.map((recipient) => <RecipientTracking key={recipient.id} recipient={recipient} canEdit={canPrepare} busy={busy} record={(data) => act(async () => { await outreachApi.recordResponse(slug, project.id, recipient.id, data); })} qualify={(data) => act(async () => { await outreachApi.qualifyRecipient(slug, project.id, recipient.id, data); })} />)}</>}
          {batch && <section className="rounded-xl border border-amber-200 bg-amber-50/40 p-4" aria-label={`Send readiness for ${trade.trade}`}>
            <h4 className="text-sm font-semibold text-slate-900">Send readiness</h4>
            {delivery.ready ? <p className="mt-1 text-sm text-emerald-700">Ready for explicit send</p> : <ul className="mt-2 list-inside list-disc text-sm text-amber-900">{delivery.blockers.map((blocker) => <li key={blocker.code}>{blocker.label}</li>)}</ul>}
            {batch.send_approved && <p className="mt-2 text-sm font-medium text-emerald-700">Sending approved by an authorized user</p>}
            {canPrepare && <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" disabled={busy || delivery.blockers.some((item) => !["messages_required", "messages_stale", "send_approval_required", "send_approval_stale", "delivery_not_configured"].includes(item.code))} onClick={() => void act(async () => { await outreachApi.deliveryAction(slug, project.id, batch.id, "prepare"); })} className="rounded-lg border border-blue-300 bg-white px-3 py-2 text-sm font-semibold text-blue-800 disabled:opacity-50">Prepare Messages</button>
              {!batch.send_approved && <button type="button" disabled={busy || delivery.blockers.some((item) => !["send_approval_required", "send_approval_stale"].includes(item.code))} onClick={() => { if (window.confirm("Approve the exact prepared message versions for sending? Review the RFQ and recipients first.")) void act(async () => { await outreachApi.deliveryAction(slug, project.id, batch.id, "approve"); }); }} className="rounded-lg border border-blue-300 bg-white px-3 py-2 text-sm font-semibold text-blue-800 disabled:opacity-50">Approve Sending</button>}
              {batch.send_approved && <button type="button" disabled={busy || !delivery.ready} onClick={() => { if (window.confirm("Send these prepared invitations now?")) void act(async () => { await outreachApi.deliveryAction(slug, project.id, batch.id, "send"); }); }} className="rounded-lg bg-[#173f5f] px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">Send Invitations</button>}
            </div>}
            {batch.recipients.flatMap((recipient) => (recipient.messages ?? []).map((message) => <div key={message.id} className="mt-3 rounded-lg border bg-white p-3 text-xs text-slate-700"><p className="font-semibold">{recipient.company_name} · Message V{message.sequence}</p><details className="mt-2"><summary className="cursor-pointer font-semibold text-blue-700">Review exact message before approval</summary><div className="mt-2 space-y-1"><p>From: {message.from_name} &lt;{message.from_address}&gt;</p><p>Reply-To: {message.reply_to}</p><p>To: {message.to_address}</p><p>Subject: {message.subject}</p><p>Template V{message.template_version} · Scope version ID {message.scope_version_id}</p><pre className="whitespace-pre-wrap break-words font-sans">{message.body}</pre></div></details>{message.attempts.length === 0 ? <p>Prepared; no delivery attempt</p> : message.attempts.map((attempt) => <div key={attempt.id} className="mt-1 flex flex-wrap items-center gap-2"><span>Attempt {attempt.sequence}: {attempt.status}</span>{attempt.safe_error_message && <span>{attempt.safe_error_message}</span>}{canPrepare && attempt.status === "failed" && <button type="button" disabled={busy} onClick={() => void act(async () => { await outreachApi.retryMessage(slug, project.id, message.id); })} className="font-semibold text-blue-700">Retry explicitly</button>}</div>)}</div>))}
          </section>}
          <div><h4 className="text-sm font-semibold text-slate-900">Approved contractors</h4>{trade.approved_candidates.length === 0 ? <p className="mt-2 text-sm text-slate-500">No contractors approved for outreach. Approve an eligible shortlisted contractor in Contractors first.</p> : <div className="mt-3 space-y-3">{trade.approved_candidates.map((candidate) => { const prepared = Boolean(batch?.recipients.some((recipient) => recipient.candidate_id === candidate.id)); return <div key={candidate.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border p-3"><div><p className="text-sm font-semibold text-slate-900">{candidate.company_name}</p><p className="text-xs text-emerald-700">Approved for Outreach ✓</p></div>{canPrepare && batch && !prepared && <div className="flex flex-wrap items-center gap-2"><select aria-label={`Contact for ${candidate.company_name}`} value={selectedContact[candidate.id] ?? ""} onChange={(event) => setSelectedContact((current) => ({ ...current, [candidate.id]: Number(event.target.value) }))} className="h-10 rounded-lg border bg-white px-3 text-sm"><option value="">Select contact</option>{candidate.contacts.map((contact) => <option key={contact.id} value={contact.id}>{contact.name} · {contact.email}{contact.is_primary ? " · Primary" : ""}</option>)}</select><button type="button" disabled={busy || !selectedContact[candidate.id]} onClick={() => void addRecipient(trade, candidate.id)} className="rounded-lg bg-[#173f5f] px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">Add Recipient</button></div>}{prepared && <span className="text-xs font-semibold text-emerald-700">Prepared in this batch ✓</span>}</div>; })}</div>}</div>
        </>}
      </div></Card>;
    })}
  </div>;
}

function RecipientTracking({ recipient, canEdit, busy, record, qualify }: {
  recipient: OutreachRecipient; canEdit: boolean; busy: boolean;
  record: (data: { outcome: string; channel: string; note: string }) => Promise<boolean>;
  qualify: (data: { state: string; note: string }) => Promise<boolean>;
}) {
  const [channel, setChannel] = useState("phone");
  const [note, setNote] = useState("");
  const [qualificationNote, setQualificationNote] = useState("");
  const canTrack = canEdit && !["prepared", "cancelled"].includes(recipient.status);
  return <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
    <p className="font-semibold text-slate-900">{recipient.company_name} · {recipient.contact_name}</p><p>{recipient.email}</p>
    <div className="mt-2 flex flex-wrap gap-2 text-xs"><span className="rounded-full bg-blue-100 px-2 py-1">Delivery: {recipient.delivery_state.replaceAll("_", " ")}</span><span className="rounded-full bg-indigo-100 px-2 py-1">Engagement: {recipient.engagement_state.replaceAll("_", " ")} (provider-reported)</span><span className="rounded-full bg-amber-100 px-2 py-1">Response: {recipient.response_state.replaceAll("_", " ")}</span><span className="rounded-full bg-emerald-100 px-2 py-1">Qualification: {recipient.qualification_state.replaceAll("_", " ")}</span></div>
    {recipient.attachment_notice && <p className="mt-2 font-medium text-amber-800">Attachments received — bid intake pending</p>}
    {canTrack && <div className="mt-3 space-y-2 rounded-lg border bg-white p-3"><p className="font-semibold">Record a response or human decision</p><div className="flex flex-wrap gap-2"><select aria-label={`Response channel for ${recipient.company_name}`} value={channel} onChange={(event) => setChannel(event.target.value)} className="rounded border p-2"><option value="phone">Phone</option><option value="email">Email outside tracked thread</option><option value="other">Other</option></select><input aria-label={`Response note for ${recipient.company_name}`} value={note} onChange={(event) => setNote(event.target.value)} placeholder="Short response note" className="min-w-48 flex-1 rounded border p-2" /></div><div className="flex flex-wrap gap-2">{([ ["Record response", "responded"], ["Mark declined", "declined"], ["Mark needs follow-up", "needs_follow_up"] ] as const).map(([label, outcome]) => <button key={outcome} type="button" disabled={busy || !note.trim()} onClick={() => void record({ outcome, channel, note }).then((saved) => { if (saved) setNote(""); })} className="rounded border border-blue-200 px-3 py-2 font-medium text-blue-800 disabled:opacity-50">{label}</button>)}</div><div className="border-t pt-3"><input aria-label={`Qualification note for ${recipient.company_name}`} value={qualificationNote} onChange={(event) => setQualificationNote(event.target.value)} placeholder="Qualification note (required if not qualified)" className="w-full rounded border p-2" /><div className="mt-2 flex flex-wrap gap-2">{([ ["Needs follow-up", "needs_follow_up"], ["Qualify", "qualified"], ["Mark not qualified", "not_qualified"] ] as const).map(([label, state]) => <button key={state} type="button" disabled={busy || (state === "not_qualified" && !qualificationNote.trim())} onClick={() => void qualify({ state, note: qualificationNote }).then((saved) => { if (saved) setQualificationNote(""); })} className="rounded border border-emerald-200 px-3 py-2 font-medium text-emerald-800 disabled:opacity-50">{label}</button>)}</div></div></div>}
    <details className="mt-3"><summary className="cursor-pointer font-medium text-blue-800">Chronological activity · {recipient.activity.length}</summary>{recipient.activity.length === 0 ? <p className="mt-2 text-slate-500">No tracked activity yet.</p> : <ol className="mt-2 space-y-2 border-l pl-4">{recipient.activity.map((item, index) => <li key={`${item.at}-${index}`}><time className="text-xs text-slate-500">{new Date(item.at).toLocaleString()}</time><p>{item.label}</p>{item.note && <p className="text-xs text-slate-600">{item.note}</p>}</li>)}</ol>}</details>
  </div>;
}
