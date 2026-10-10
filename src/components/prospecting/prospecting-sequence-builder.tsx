"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import {
  ProspectEmailTemplate,
  ProspectPreview,
  ProspectSequenceStep,
  prospectingApi,
} from "@/lib/prospecting";

const tokens = ["first_name", "name", "company_name", "trade"] as const;
type DelayUnit = "minutes" | "hours" | "days";
type CampaignData = Awaited<ReturnType<typeof prospectingApi.campaign>>;

function delayParts(minutes: number): { value: number; unit: DelayUnit } {
  if (minutes > 0 && minutes % 1440 === 0) return { value: minutes / 1440, unit: "days" };
  if (minutes > 0 && minutes % 60 === 0) return { value: minutes / 60, unit: "hours" };
  return { value: minutes, unit: "minutes" };
}

function delayMinutes(value: number, unit: DelayUnit) {
  return value * (unit === "days" ? 1440 : unit === "hours" ? 60 : 1);
}

function StepCard({
  step,
  first,
  editable,
  templates,
  onSave,
  onDuplicate,
  onRemove,
  onMove,
  onPreview,
  onSaveTemplate,
}: {
  step: ProspectSequenceStep;
  first: boolean;
  editable: boolean;
  templates: ProspectEmailTemplate[];
  onSave: (step: ProspectSequenceStep) => Promise<void>;
  onDuplicate: () => Promise<void>;
  onRemove: () => Promise<void>;
  onMove: (direction: -1 | 1) => Promise<void>;
  onPreview: () => void;
  onSaveTemplate: (step: ProspectSequenceStep) => Promise<void>;
}) {
  const [draft, setDraft] = useState(step);
  const [delay, setDelay] = useState(delayParts(step.delay_minutes));
  const insert = (field: "subject" | "body", token: string) => setDraft((current) => ({ ...current, [field]: `${current[field]}{{${token}}}` }));
  const applyTemplate = (id: number) => {
    const template = templates.find((item) => item.id === id);
    if (template) setDraft((current) => ({ ...current, subject: template.subject, body: template.body }));
  };
  return <article className={`rounded-xl border p-4 ${draft.enabled ? "bg-white" : "bg-slate-50 opacity-75"}`}>
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><p className="text-xs font-bold uppercase tracking-wide text-indigo-600">Step {step.step_number}</p><input aria-label={`Step ${step.step_number} name`} value={draft.label} disabled={!editable} onChange={(event) => setDraft({ ...draft, label: event.target.value })} className="mt-1 h-9 rounded-lg border px-2 font-semibold disabled:border-transparent disabled:bg-transparent" placeholder={first ? "Initial Email" : `Follow-up ${step.step_number - 1}`} /><p className="text-xs text-slate-500">{first ? "Send immediately" : `Wait ${delay.value} ${delay.unit} after previous step`}</p></div>
      <span className={`rounded-full px-2 py-1 text-xs font-semibold ${draft.enabled ? "bg-emerald-50 text-emerald-700" : "bg-slate-200 text-slate-600"}`}>{draft.enabled ? "Enabled" : "Disabled"}</span>
    </div>
    <div className="mt-4 grid gap-3">
      {!first && <div className="flex items-end gap-2"><label className="grid gap-1 text-xs font-semibold text-slate-600">Wait<input aria-label={`Step ${step.step_number} delay`} type="number" min="1" value={delay.value} disabled={!editable} onChange={(event) => setDelay({ ...delay, value: Number(event.target.value) })} className="h-9 w-24 rounded-lg border px-2" /></label><select aria-label={`Step ${step.step_number} delay unit`} value={delay.unit} disabled={!editable} onChange={(event) => setDelay({ ...delay, unit: event.target.value as DelayUnit })} className="h-9 rounded-lg border bg-white px-2"><option value="minutes">minutes</option><option value="hours">hours</option><option value="days">days</option></select></div>}
      {editable && templates.length > 0 && <label className="grid gap-1 text-xs font-semibold text-slate-600">Use template<select defaultValue="" onChange={(event) => applyTemplate(Number(event.target.value))} className="h-9 rounded-lg border bg-white px-2"><option value="">Choose saved template</option>{templates.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
      <label className="grid gap-1 text-sm font-semibold text-slate-700">Subject<input value={draft.subject} disabled={!editable} onChange={(event) => setDraft({ ...draft, subject: event.target.value })} className="h-10 rounded-lg border px-3" /></label>
      {editable && <div className="flex flex-wrap gap-1 text-xs"><span className="py-1 text-slate-500">Insert in subject:</span>{tokens.map((token) => <button type="button" key={token} onClick={() => insert("subject", token)} className="rounded border px-2 py-1">{`{{${token}}}`}</button>)}</div>}
      <label className="grid gap-1 text-sm font-semibold text-slate-700">Body<textarea value={draft.body} disabled={!editable} onChange={(event) => setDraft({ ...draft, body: event.target.value })} className="min-h-36 rounded-lg border p-3 font-normal" /></label>
      {editable && <div className="flex flex-wrap gap-1 text-xs"><span className="py-1 text-slate-500">Insert in body:</span>{tokens.map((token) => <button type="button" key={token} onClick={() => insert("body", token)} className="rounded border px-2 py-1">{`{{${token}}}`}</button>)}</div>}
    </div>
    <div className="mt-4 flex flex-wrap gap-2 text-sm font-semibold">
      {editable && <button type="button" onClick={() => void onSave({ ...draft, delay_minutes: first ? 0 : delayMinutes(delay.value, delay.unit) })} className="rounded-lg bg-indigo-700 px-3 py-2 text-white">Save draft</button>}
      <button type="button" onClick={onPreview} className="rounded-lg border px-3 py-2">Preview</button>
      {editable && <><button type="button" onClick={() => void onDuplicate()} className="rounded-lg border px-3 py-2">Duplicate</button><button type="button" onClick={() => void onSaveTemplate(draft)} className="rounded-lg border px-3 py-2">Save as template</button><button type="button" onClick={() => void onSave({ ...draft, enabled: !draft.enabled, delay_minutes: first ? 0 : delayMinutes(delay.value, delay.unit) })} className="rounded-lg border px-3 py-2">{draft.enabled ? "Disable" : "Enable"}</button><button type="button" onClick={() => void onMove(-1)} className="rounded-lg border px-3 py-2">Move up</button><button type="button" onClick={() => void onMove(1)} className="rounded-lg border px-3 py-2">Move down</button>{!first && <button type="button" onClick={() => void onRemove()} className="rounded-lg border border-red-200 px-3 py-2 text-red-700">Remove</button>}</>}
    </div>
  </article>;
}

export function ProspectingSequenceBuilder({ slug, campaignId }: { slug: string; campaignId: number }) {
  const router = useRouter();
  const [data, setData] = useState<CampaignData | null>(null);
  const [templates, setTemplates] = useState<ProspectEmailTemplate[]>([]);
  const [archivedTemplates, setArchivedTemplates] = useState<ProspectEmailTemplate[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [preview, setPreview] = useState<ProspectPreview | null>(null);
  const [previewStep, setPreviewStep] = useState<number | null>(null);
  const [previewRecipient, setPreviewRecipient] = useState<number | null>(null);
  const [testEmail, setTestEmail] = useState("");
  const load = useCallback(async () => {
    try {
      const [campaign, templateData, archivedData] = await Promise.all([prospectingApi.campaign(slug, campaignId), prospectingApi.templates(slug), prospectingApi.templates(slug, "archived")]);
      setData(campaign); setTemplates(templateData.results); setArchivedTemplates(archivedData.results); setError("");
      setPreviewRecipient((current) => current ?? campaign.recipients[0]?.id ?? null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Campaign could not be loaded."); }
  }, [slug, campaignId]);
  useEffect(() => {
    let active = true;
    Promise.all([prospectingApi.campaign(slug, campaignId), prospectingApi.templates(slug), prospectingApi.templates(slug, "archived")])
      .then(([campaign, templateData, archivedData]) => {
        if (!active) return;
        setData(campaign);
        setTemplates(templateData.results);
        setArchivedTemplates(archivedData.results);
        setError("");
        setPreviewRecipient((current) => current ?? campaign.recipients[0]?.id ?? null);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Campaign could not be loaded.");
      });
    return () => { active = false; };
  }, [slug, campaignId]);
  if (!data) return <Notice text={error || "Loading campaign…"} error={Boolean(error)} />;
  const editable = data.can_manage && data.campaign.status === "draft";
  async function mutate(action: () => Promise<unknown>, success?: string) { setError(""); try { await action(); if (success) setNotice(success); await load(); } catch (reason) { setError(reason instanceof Error ? reason.message : "The campaign could not be updated."); } }
  async function move(index: number, direction: -1 | 1) { const target = index + direction; if (target < 0 || target >= data!.steps.length) return; const ids = data!.steps.map((item) => item.id); [ids[index], ids[target]] = [ids[target], ids[index]]; await mutate(() => prospectingApi.reorderSteps(slug, campaignId, ids)); }
  async function showPreview(stepId: number) { setPreviewStep(stepId); if (!previewRecipient) { setError("Enroll an eligible prospect before previewing personalized content."); return; } try { setPreview(await prospectingApi.previewCampaignStep(slug, campaignId, stepId, previewRecipient)); } catch (reason) { setError(reason instanceof Error ? reason.message : "Preview could not be rendered."); } }
  async function saveTemplate(step: ProspectSequenceStep) { const name = window.prompt("Template name"); if (!name?.trim()) return; await mutate(() => prospectingApi.createTemplate(slug, { name, subject: step.subject, body: step.body }), "Template saved. Existing campaign steps remain independent."); }
  async function editTemplate(template: ProspectEmailTemplate) {
    const name = window.prompt("Template name", template.name); if (!name?.trim()) return;
    const subject = window.prompt("Template subject", template.subject); if (subject === null) return;
    const body = window.prompt("Template body", template.body); if (body === null) return;
    await mutate(() => prospectingApi.updateTemplate(slug, template.id, { name, subject, body }), "Template updated. Existing campaign steps were not changed.");
  }
  async function saveExistingStep(step: ProspectSequenceStep) {
    const { id: stepId, ...values } = step;
    await mutate(() => prospectingApi.saveStep(slug, campaignId, values, stepId));
  }
  async function addStep() {
    const initial = data!.steps.length === 0;
    await mutate(() => prospectingApi.saveStep(slug, campaignId, {
      step_number: data!.steps.length + 1,
      label: initial ? "Initial Email" : `Follow-up ${data!.steps.length}`,
      subject: data!.steps.at(-1)?.subject || "Quick question for {{company_name}}",
      body: initial ? "Hi {{first_name}},\n\n" : "Hi {{first_name}},\n\nI wanted to follow up on my previous note.",
      delay_minutes: initial ? 0 : 4320,
      enabled: true,
    }));
  }
  const campaignAction = (action: "approve" | "launch" | "pause" | "resume" | "archive" | "restore") => mutate(() => prospectingApi.campaignAction(slug, campaignId, action));
  async function removeCampaign() {
    const historical = data!.campaign.status !== "draft";
    if (!window.confirm(historical ? "Archive campaign?\n\nNo future messages will be sent. Historical delivery and recipient records will be preserved." : "Delete unused Draft campaign?")) return;
    setError("");
    try {
      await prospectingApi.removeCampaign(slug, campaignId);
      router.push("/prospecting/campaigns");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The campaign could not be removed.");
    }
  }
  return <div className="space-y-4">
    {error && <Notice text={error} error />}{notice && <Notice text={notice} />}
    <Card className="p-5"><div className="flex flex-wrap items-start justify-between gap-4"><div><h2 className="text-xl font-bold">{data.campaign.name}</h2><p className="mt-1 text-sm text-slate-500 capitalize">{data.campaign.status} · {data.metrics.enrolled} recipients · {data.steps.length} steps</p></div><div className="flex flex-wrap gap-2 text-sm font-semibold">{editable && <button type="button" onClick={() => void mutate(() => prospectingApi.enroll(slug, campaignId, { list_ids: data.campaign.source_list_ids }))} className="rounded-lg border px-3 py-2">Enroll eligible prospects</button>}{data.can_admin && data.campaign.status === "draft" && <button type="button" onClick={() => void campaignAction("approve")} className="rounded-lg bg-indigo-700 px-3 py-2 text-white">Approve sequence</button>}{data.can_admin && data.campaign.status === "approved" && <button type="button" onClick={() => void campaignAction("launch")} className="rounded-lg bg-emerald-700 px-3 py-2 text-white">Launch campaign</button>}{data.can_manage && data.campaign.status === "active" && <button type="button" onClick={() => void campaignAction("pause")} className="rounded-lg border px-3 py-2">Pause</button>}{data.can_manage && data.campaign.status === "paused" && <button type="button" onClick={() => void campaignAction("resume")} className="rounded-lg border px-3 py-2">Resume</button>}{data.can_manage && data.campaign.status !== "archived" && <button type="button" onClick={() => void removeCampaign()} className="rounded-lg border border-red-200 px-3 py-2 text-red-700">{data.campaign.status === "draft" ? "Delete campaign" : "Archive campaign"}</button>}{data.can_manage && data.campaign.status === "archived" && <button type="button" onClick={() => void campaignAction("restore")} className="rounded-lg border px-3 py-2">Restore campaign</button>}</div></div>{!data.readiness.ready && ["draft", "approved"].includes(data.campaign.status) && <div className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900"><strong>Next action</strong><p>{data.readiness.blockers[0]}</p></div>}</Card>
    <Card className="p-5"><div className="flex items-center justify-between"><div><h3 className="font-semibold">Cold email sequence</h3><p className="text-sm text-slate-500">Follow-ups stop after replies, unsubscribes, suppression, hard bounces, complaints, cancellation, or another terminal state.</p></div>{editable && data.steps.length < 5 && <button type="button" onClick={() => void addStep()} className="rounded-lg bg-indigo-700 px-3 py-2 text-sm font-semibold text-white">{data.steps.length === 0 ? "+ Add initial email" : "+ Add follow-up"}</button>}</div><div className="mt-4 space-y-3">{data.steps.map((step, index) => <StepCard key={step.id} step={step} first={index === 0} editable={editable} templates={templates} onSave={saveExistingStep} onDuplicate={() => mutate(() => prospectingApi.duplicateStep(slug, campaignId, step.id))} onRemove={() => mutate(() => prospectingApi.removeStep(slug, campaignId, step.id))} onMove={(direction) => move(index, direction)} onPreview={() => void showPreview(step.id)} onSaveTemplate={saveTemplate} />)}{!data.steps.length && <p className="text-sm text-slate-500">Add the initial email to begin this sequence.</p>}</div></Card>
    <Card className="p-5"><h3 className="font-semibold">Saved templates</h3><p className="mt-1 text-sm text-slate-500">Templates provide reusable starting content. Campaign steps remain independent snapshots.</p><div className="mt-3 space-y-2">{templates.map((template) => <div key={template.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3"><div><strong className="text-sm">{template.name}</strong><p className="text-xs text-slate-500">{template.subject}</p></div>{data.can_manage && <div className="flex gap-2"><button type="button" onClick={() => void editTemplate(template)} className="rounded border px-3 py-1.5 text-sm font-semibold">Edit</button><button type="button" onClick={() => void mutate(() => prospectingApi.updateTemplate(slug, template.id, { is_active: false }))} className="rounded border border-red-200 px-3 py-1.5 text-sm font-semibold text-red-700">Archive</button></div>}</div>)}</div>{archivedTemplates.length > 0 && <details className="mt-3"><summary className="cursor-pointer text-sm font-semibold">Archived templates ({archivedTemplates.length})</summary><div className="mt-2 space-y-2">{archivedTemplates.map((template) => <div key={template.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-slate-50 p-3"><strong className="text-sm">{template.name}</strong>{data.can_manage && <button type="button" onClick={() => void mutate(() => prospectingApi.updateTemplate(slug, template.id, { is_active: true }))} className="rounded border px-3 py-1.5 text-sm font-semibold">Restore</button>}</div>)}</div></details>}</Card>
    <Card className="p-5"><h3 className="font-semibold">Preview and test</h3><div className="mt-3 grid gap-3 md:grid-cols-3"><label className="grid gap-1 text-sm font-semibold">Preview as prospect<select value={previewRecipient ?? ""} onChange={(event) => setPreviewRecipient(Number(event.target.value))} className="h-10 rounded-lg border bg-white px-2"><option value="">Select enrolled prospect</option>{data.recipients.map((item) => <option key={item.id} value={item.id}>{item.contact_name} · {item.company_name}</option>)}</select></label><label className="grid gap-1 text-sm font-semibold">Sequence step<select value={previewStep ?? data.steps[0]?.id ?? ""} onChange={(event) => setPreviewStep(Number(event.target.value))} className="h-10 rounded-lg border bg-white px-2">{data.steps.map((item) => <option key={item.id} value={item.id}>Step {item.step_number}</option>)}</select></label><button type="button" disabled={!previewRecipient || !(previewStep ?? data.steps[0]?.id)} onClick={() => void showPreview(previewStep ?? data.steps[0].id)} className="self-end rounded-lg border px-3 py-2 text-sm font-semibold disabled:opacity-50">Preview as prospect</button></div>{preview && <div className="mt-4 rounded-lg border bg-slate-50 p-4 text-sm"><p><strong>From:</strong> {preview.from_name} &lt;{preview.from_address}&gt;</p><p><strong>To:</strong> {preview.to_name} &lt;{preview.to_address}&gt;</p><p><strong>Subject:</strong> {preview.subject}</p><pre className="mt-3 whitespace-pre-wrap font-sans">{preview.body}</pre></div>}{editable && <div className="mt-4 flex flex-wrap items-end gap-2"><label className="grid flex-1 gap-1 text-sm font-semibold">Explicit test recipient email<input type="email" value={testEmail} onChange={(event) => setTestEmail(event.target.value)} className="h-10 rounded-lg border px-3" placeholder="you@example.com" /></label><button type="button" disabled={!testEmail || !data.steps.length} onClick={() => void mutate(() => prospectingApi.sendTestEmail(slug, campaignId, { step_id: previewStep ?? data.steps[0].id, recipient_id: previewRecipient ?? undefined, test_email: testEmail }), "Test email sent. No prospect was enrolled or advanced.")} className="rounded-lg bg-slate-950 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Send test email</button></div>}</Card>
    <Card className="overflow-hidden"><div className="border-b p-4"><h3 className="font-semibold">Recipients</h3></div>{data.recipients.length ? <div className="divide-y">{data.recipients.map((item) => <div key={item.id} className="grid gap-2 p-4 text-sm md:grid-cols-5"><strong>{item.company_name}</strong><span>{item.contact_name}</span><span>{item.normalized_email}</span><span className="capitalize">{item.state}</span>{data.can_manage && ["pending", "scheduled", "active"].includes(item.state) ? <button type="button" onClick={() => void mutate(() => prospectingApi.cancelRecipient(slug, item.id))} className="text-left font-semibold text-red-700">Cancel</button> : <span />}</div>)}</div> : <p className="p-4 text-sm text-slate-500">No recipients enrolled.</p>}</Card>
  </div>;
}

function Notice({ text, error = false }: { text: string; error?: boolean }) { return <div role={error ? "alert" : "status"} className={`rounded-xl border p-4 text-sm ${error ? "border-red-200 bg-red-50 text-red-800" : "bg-white text-slate-600"}`}>{text}</div>; }
