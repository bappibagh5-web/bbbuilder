"use client";

import { useCallback, useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import {
  bidReadinessCopy, bidRevisionsApi, type BidCandidate, type BidExtraction,
  type BidCommercialItem, type BidRevision, type BidScopeItemChoice,
} from "@/lib/bid-revisions";
import type { QuoteSubmission } from "@/lib/bids";
import { displayBidCandidateValue, displayBidMoney } from "@/lib/bid-money";

type Props = {
  quote: QuoteSubmission; slug: string; projectId: number; canEdit: boolean;
  onBack: () => void; download: (attachment: QuoteSubmission["attachments"][number]) => void;
};

export function StructuredBidEditor({ quote, slug, projectId, canEdit, onBack, download }: Props) {
  const [revisions, setRevisions] = useState<BidRevision[]>([]);
  const [scopeItems, setScopeItems] = useState<BidScopeItemChoice[]>([]);
  const [extractions, setExtractions] = useState<BidExtraction[]>([]);
  const [selectedId, setSelectedId] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [label, setLabel] = useState("Original");
  const [baseBid, setBaseBid] = useState("");
  const [currency, setCurrency] = useState("");
  const [baseReview, setBaseReview] = useState("unreviewed");
  const [currencyReview, setCurrencyReview] = useState("unreviewed");
  const [tax, setTax] = useState("not_stated");
  const [taxReviewed, setTaxReviewed] = useState(false);
  const [commercialReviewed, setCommercialReviewed] = useState(false);
  const [scopeReviewed, setScopeReviewed] = useState(false);
  const [validityDate, setValidityDate] = useState("");
  const [validityDays, setValidityDays] = useState("");
  const [schedule, setSchedule] = useState("");
  const [notes, setNotes] = useState("");
  const [itemKind, setItemKind] = useState("alternate");
  const [itemTitle, setItemTitle] = useState("");
  const [itemDescription, setItemDescription] = useState("");
  const [itemTreatment, setItemTreatment] = useState("");
  const [itemAmount, setItemAmount] = useState("");
  const [itemCurrency, setItemCurrency] = useState("");
  const [itemInBase, setItemInBase] = useState("unclear");
  const [itemCategory, setItemCategory] = useState("");
  const [itemLabel, setItemLabel] = useState("");
  const [extractKey, setExtractKey] = useState(() => crypto.randomUUID());
  const [revisionKey, setRevisionKey] = useState(() => crypto.randomUUID());
  const [supersedesId, setSupersedesId] = useState(0);
  const [evidenceTarget, setEvidenceTarget] = useState("base_bid");
  const [evidenceSource, setEvidenceSource] = useState("quote");
  const [evidenceAttachment, setEvidenceAttachment] = useState(quote.attachments[0]?.id || 0);
  const [evidencePage, setEvidencePage] = useState("");
  const [evidenceExcerpt, setEvidenceExcerpt] = useState("");
  const [evidenceNote, setEvidenceNote] = useState("");

  const refresh = useCallback(async () => {
    const [revisionList, extractionList] = await Promise.all([
      bidRevisionsApi.list(slug, projectId, quote.id),
      bidRevisionsApi.extractions(slug, projectId, quote.id),
    ]);
    setRevisions(revisionList.revisions);
    setScopeItems(revisionList.scope_items);
    setExtractions(extractionList.runs);
    setSelectedId((previous) => previous || revisionList.revisions[0]?.id || 0);
  }, [slug, projectId, quote.id]);

  useEffect(() => {
    let alive = true;
    Promise.all([
      bidRevisionsApi.list(slug, projectId, quote.id),
      bidRevisionsApi.extractions(slug, projectId, quote.id),
    ]).then(([list, extractionsList]) => {
      if (!alive) return;
      setRevisions(list.revisions); setScopeItems(list.scope_items);
      setExtractions(extractionsList.runs); setSelectedId(list.revisions[0]?.id || 0);
    }).catch((reason: unknown) => { if (alive) setError(message(reason)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [slug, projectId, quote.id]);

  useEffect(() => {
    if (!extractions.some((run) => run.status === "queued" || run.status === "running")) return;
    const timer = window.setInterval(() => { void refresh().catch((reason) => setError(message(reason))); }, 5000);
    return () => window.clearInterval(timer);
  }, [extractions, refresh]);

  const selected = revisions.find((revision) => revision.id === selectedId);
  const draft = selected?.status === "draft" && canEdit;
  const [formSource, setFormSource] = useState<BidRevision | undefined>();
  if (selected && selected !== formSource) {
    setFormSource(selected);
    setLabel(selected.contractor_label);
    setBaseBid(selected.base_bid ?? ""); setBaseReview(selected.base_bid_review);
    setCurrency(selected.currency); setCurrencyReview(selected.currency_review);
    setTax(selected.tax_treatment); setTaxReviewed(selected.tax_reviewed);
    setCommercialReviewed(selected.commercial_items_reviewed);
    setScopeReviewed(selected.scope_reviewed);
    setValidityDate(selected.validity_date ?? "");
    setValidityDays(selected.validity_days ? String(selected.validity_days) : "");
    setSchedule(selected.schedule_text); setNotes(selected.estimator_notes);
  }

  async function act(operation: () => Promise<unknown>) {
    setBusy(true); setError("");
    try { await operation(); await refresh(); return true; }
    catch (reason) { setError(message(reason)); return false; }
    finally { setBusy(false); }
  }

  async function create() {
    let createdId = 0;
    const ok = await act(async () => {
      const revision = await bidRevisionsApi.create(slug, projectId, quote.id,
        label || "Original", revisionKey, supersedesId || undefined);
      createdId = revision.id;
    });
    if (ok) {
      setSelectedId(createdId);
      setRevisionKey(crypto.randomUUID());
      setSupersedesId(0);
    }
  }
  async function saveSummary() {
    if (!selected) return;
    await act(() => bidRevisionsApi.update(slug, projectId, quote.id, selected.id, {
      contractor_label: label, base_bid: baseReview === "confirmed" ? baseBid : null,
      base_bid_review: baseReview, currency: currencyReview === "confirmed" ? currency.toUpperCase() : "",
      currency_review: currencyReview, tax_treatment: tax, tax_reviewed: taxReviewed,
      commercial_items_reviewed: commercialReviewed, scope_reviewed: scopeReviewed,
      validity_date: validityDate || null, validity_days: validityDays ? Number(validityDays) : null,
      schedule_text: schedule, estimator_notes: notes,
    }));
  }
  async function addItem() {
    if (!selected || !itemTitle) return;
    const ok = await act(() => bidRevisionsApi.addItem(slug, projectId, quote.id, selected.id, {
      kind: itemKind, title: itemTitle, description: itemDescription,
      treatment: itemTreatment, amount: itemAmount || null,
      currency: itemAmount ? itemCurrency.toUpperCase() : "",
      included_in_base: itemInBase,
      category: itemCategory, contractor_label: itemLabel,
    }));
    if (ok) { setItemTitle(""); setItemDescription(""); setItemAmount(""); }
  }
  async function saveCoverage(scopeItemId: number, state: string, wording: string, reviewed: boolean) {
    if (!selected) return;
    await act(() => bidRevisionsApi.coverage(slug, projectId, quote.id, selected.id,
      scopeItemId, { state, wording, reviewed }));
  }
  async function extract(attachmentId: number) {
    const ok = await act(() => bidRevisionsApi.extract(slug, projectId, quote.id, attachmentId, extractKey));
    if (ok) setExtractKey(crypto.randomUUID());
  }
  async function addEvidence() {
    if (!selected) return;
    const ok = await act(() => bidRevisionsApi.evidence(slug, projectId, quote.id, selected.id, {
      ...(evidenceTarget.startsWith("item:")
        ? { commercial_item_id: Number(evidenceTarget.slice(5)) }
        : { field_key: evidenceTarget }),
      source: evidenceSource,
      attachment_id: evidenceSource === "quote" ? evidenceAttachment : null,
      page_number: evidenceSource === "quote" && evidencePage ? Number(evidencePage) : null,
      excerpt: evidenceExcerpt, note: evidenceNote,
    }));
    if (ok) { setEvidencePage(""); setEvidenceExcerpt(""); setEvidenceNote(""); }
  }
  async function decide(run: BidExtraction, index: number, candidate: BidCandidate,
                        decision: "accepted" | "corrected" | "ignored", correction = "", note = "") {
    if (!selected) return;
    const correctedField = candidate.kind === "base_bid" || candidate.kind === "alternate"
      || candidate.kind === "allowance" || candidate.kind === "fee" ? "amount"
      : candidate.kind === "currency" ? "currency"
      : candidate.kind === "tax" ? "treatment"
      : candidate.kind === "scope_coverage" ? "state" : "description";
    const change = decision === "corrected" ? { [correctedField]: correction, note } : {};
    await act(() => bidRevisionsApi.candidateDecision(slug, projectId, quote.id,
      selected.id, run.id, index, decision, change));
  }

  return <div className="space-y-5">
    <button type="button" onClick={onBack} className="text-sm font-semibold text-blue-700">← Back to received quotes</button>
    <div><h2 className="text-xl font-semibold">Structure Bid · {quote.trade}</h2>
      <p className="text-sm text-slate-600">{quote.company_name} · Exact Ready scope version #{quote.scope_version_id} · Campaign #{quote.campaign_id} / Batch #{quote.batch_id}. The original quote remains authoritative. This does not compare contractors.</p></div>
    {error && <Card role="alert" className="border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</Card>}
    <Card className="space-y-2 p-5"><h3 className="font-semibold">Original source quote</h3>
      <p className="text-sm text-slate-600">{quote.source === "inbound_email" ? "Received by email" : "Uploaded manually"} · {new Date(quote.received_at).toLocaleString()}</p>
      {quote.attachments.map((attachment) => <div key={attachment.id} className="flex items-center justify-between gap-2 text-sm"><span>{attachment.filename}</span><button type="button" onClick={() => download(attachment)} className="font-semibold text-blue-700">Download original</button></div>)}
    </Card>
    {loading ? <Card className="p-5 text-sm">Loading structured bid…</Card> : <>
      {canEdit && <Card className="space-y-2 p-5"><h3 className="font-semibold">Create a human-controlled revision</h3>
        <p className="text-sm text-slate-600">A later quote does not automatically become a new revision or replace the earlier one.</p>
        <input aria-label="Contractor revision label" value={label} onChange={(event) => setLabel(event.target.value)} placeholder="Original / Rev A" className="rounded-lg border p-2 text-sm" />
        {revisions.length > 0 && <select aria-label="Supersedes earlier revision" value={supersedesId} onChange={(event) => setSupersedesId(Number(event.target.value))} className="ml-2 rounded-lg border p-2 text-sm"><option value={0}>No supersession (separate commercial record)</option>{revisions.map((revision) => <option key={revision.id} value={revision.id}>Supersedes {revision.contractor_label || `Revision ${revision.sequence}`}</option>)}</select>}
        <button type="button" disabled={busy} onClick={() => void create()} className="ml-2 rounded-lg bg-blue-800 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">Create Draft Revision</button>
      </Card>}
      {revisions.length > 0 && <Card className="p-5"><h3 className="font-semibold">Revision history</h3>
        <div className="mt-2 flex flex-wrap gap-2">{revisions.map((revision) => <button type="button" key={revision.id} onClick={() => setSelectedId(revision.id)} className={`rounded-lg border px-3 py-2 text-sm ${selectedId === revision.id ? "border-blue-700 bg-blue-50" : ""}`}>
          {revision.contractor_label || `Revision ${revision.sequence}`} · {revision.status === "ready" ? "Ready for Comparison" : "Draft"}{revision.supersedes_id ? ` · Supersedes #${revision.supersedes_id}` : ""}{revision.superseded_by_ids.length > 0 ? ` · Superseded by #${revision.superseded_by_ids.join(", #")}` : ""}
        </button>)}</div></Card>}
      {selected && <>
        <Card className="space-y-3 p-5"><h3 className="font-semibold">Commercial Summary</h3>
          <p className="text-sm font-medium text-slate-700">Recorded Base Bid: {displayBidMoney(selected.base_bid, selected.currency)} · Tax: {selected.tax_reviewed ? selected.tax_treatment.replaceAll("_", " ") : "not yet reviewed"}</p>
          <div className="grid gap-3 md:grid-cols-3">
            <label className="text-sm">Base Bid<input aria-label="Base Bid" disabled={!draft || baseReview !== "confirmed"} value={baseBid} onChange={(event) => setBaseBid(event.target.value)} placeholder="Exact decimal amount" className="mt-1 w-full rounded-lg border p-2" /></label>
            <label className="text-sm">Base Bid reviewed as<select disabled={!draft} value={baseReview} onChange={(event) => setBaseReview(event.target.value)} className="mt-1 w-full rounded-lg border p-2"><option value="unreviewed">Not yet reviewed</option><option value="confirmed">Human confirmed</option><option value="not_stated">Not stated in quote</option></select></label>
            <label className="text-sm">Currency<input aria-label="Currency" disabled={!draft || currencyReview !== "confirmed"} value={currency} onChange={(event) => setCurrency(event.target.value)} placeholder="CAD / USD (do not assume)" className="mt-1 w-full rounded-lg border p-2" /></label>
            <label className="text-sm">Currency reviewed as<select disabled={!draft} value={currencyReview} onChange={(event) => setCurrencyReview(event.target.value)} className="mt-1 w-full rounded-lg border p-2"><option value="unreviewed">Not yet reviewed</option><option value="confirmed">Human confirmed</option><option value="not_stated">Not stated in quote</option></select></label>
            <label className="text-sm">Tax treatment<select disabled={!draft} value={tax} onChange={(event) => setTax(event.target.value)} className="mt-1 w-full rounded-lg border p-2"><option value="not_stated">Not stated / needs confirmation</option><option value="included">Included</option><option value="extra">Extra</option><option value="exempt">Exempt</option></select></label>
            <label className="flex items-center gap-2 self-end text-sm"><input type="checkbox" disabled={!draft} checked={taxReviewed} onChange={(event) => setTaxReviewed(event.target.checked)} />Tax treatment reviewed by you</label>
            <label className="text-sm">Bid validity date (if stated)<input type="date" disabled={!draft} value={validityDate} onChange={(event) => setValidityDate(event.target.value)} className="mt-1 w-full rounded-lg border p-2" /></label>
            <label className="text-sm">Or validity days (if stated)<input type="number" min="1" disabled={!draft} value={validityDays} onChange={(event) => setValidityDays(event.target.value)} className="mt-1 w-full rounded-lg border p-2" /></label>
            <label className="text-sm">Schedule / duration (if stated)<input disabled={!draft} value={schedule} onChange={(event) => setSchedule(event.target.value)} className="mt-1 w-full rounded-lg border p-2" /></label>
          </div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={!draft} checked={commercialReviewed} onChange={(event) => setCommercialReviewed(event.target.checked)} />I reviewed alternates, allowances, fees, exclusions and conditions in the original quote</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={!draft} checked={scopeReviewed} onChange={(event) => setScopeReviewed(event.target.checked)} />I reviewed scope coverage and differences against the exact Ready scope</label>
          <textarea aria-label="Estimator notes" disabled={!draft} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Estimator notes; do not invent quote terms" className="w-full rounded-lg border p-2 text-sm" />
          {draft && <button type="button" disabled={busy} onClick={() => void saveSummary()} className="rounded-lg bg-blue-800 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">Save Draft</button>}
        </Card>
        <Card className="space-y-3 p-5"><h3 className="font-semibold">Commercial details</h3>
          <p className="text-sm text-slate-600">Separate commercial terms stay separate from the Base Bid. Missing values are never treated as zero.</p>
          {([ ["alternate", "Alternates / Options"], ["allowance", "Allowances"],
            ["fee", "Permits / Fees / Taxes"], ["exclusion", "Exclusions"],
            ["condition", "Qualifications / Conditions"] ] as const).map(([kind, heading]) => <section key={kind} className="space-y-2 rounded-lg border border-slate-200 p-3"><h4 className="font-semibold">{heading}</h4>
              {selected.commercial_items.filter((item) => item.kind === kind).length === 0 ? <p className="text-sm text-slate-500">None recorded yet; do not infer this from silence.</p> : selected.commercial_items.filter((item) => item.kind === kind).map((item) => <CommercialItemRow key={item.id} item={item} disabled={!draft || busy}
                save={(values) => act(() => bidRevisionsApi.updateItem(slug, projectId, quote.id, selected.id, item.id, values))}
                remove={() => act(() => bidRevisionsApi.removeItem(slug, projectId, quote.id, selected.id, item.id))} />)}
            </section>)}
          {draft && <div className="grid gap-2 md:grid-cols-3"><select aria-label="Commercial item type" value={itemKind} onChange={(event) => setItemKind(event.target.value)} className="rounded-lg border p-2 text-sm"><option value="alternate">Alternate / Option</option><option value="allowance">Allowance</option><option value="fee">Permit / Fee / Tax</option><option value="exclusion">Explicit exclusion</option><option value="condition">Qualification / Condition</option></select>
            <input aria-label="Commercial item title" value={itemTitle} onChange={(event) => setItemTitle(event.target.value)} placeholder="Title" className="rounded-lg border p-2 text-sm" />
            <input aria-label="Contractor alternate label" value={itemLabel} onChange={(event) => setItemLabel(event.target.value)} placeholder="Contractor label, if supplied" className="rounded-lg border p-2 text-sm" />
            <input aria-label="Fee or condition category" value={itemCategory} onChange={(event) => setItemCategory(event.target.value)} placeholder="Permits / freight / taxes / schedule…" className="rounded-lg border p-2 text-sm" />
            <input aria-label="Commercial item description" value={itemDescription} onChange={(event) => setItemDescription(event.target.value)} placeholder="Contractor wording" className="rounded-lg border p-2 text-sm" />
            <select aria-label="Treatment" value={itemTreatment} onChange={(event) => setItemTreatment(event.target.value)} className="rounded-lg border p-2 text-sm"><option value="">Treatment not stated</option><option value="add">Add</option><option value="deduct">Deduct</option><option value="no_cost">No cost</option><option value="price_on_request">Price on request</option><option value="included">Included</option><option value="excluded">Excluded</option><option value="extra">Extra</option><option value="allowance">Allowance</option><option value="not_stated">Not stated</option></select>
            <input aria-label="Item amount" value={itemAmount} onChange={(event) => setItemAmount(event.target.value)} placeholder="Amount, if stated" className="rounded-lg border p-2 text-sm" />
            <input aria-label="Item currency" value={itemCurrency} onChange={(event) => setItemCurrency(event.target.value)} placeholder="Currency, if amount stated" className="rounded-lg border p-2 text-sm" />
            <select aria-label="Included in Base Bid" value={itemInBase} onChange={(event) => setItemInBase(event.target.value)} className="rounded-lg border p-2 text-sm"><option value="unclear">Included in Base Bid: unclear</option><option value="yes">Included in Base Bid: yes</option><option value="no">Included in Base Bid: no</option></select>
            <button type="button" disabled={busy || !itemTitle} onClick={() => void addItem()} className="rounded-lg bg-blue-800 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">Add Draft item</button>
          </div>}
        </Card>
        <Card className="space-y-3 p-5"><h3 className="font-semibold">Scope Coverage / Differences</h3><p className="text-sm text-slate-600">Check the exact Ready scope version. Not addressed does not mean excluded.</p>
          <details><summary className="cursor-pointer text-sm font-semibold text-blue-700">Review {scopeItems.length} quoted scope items</summary>
            <div className="mt-3 space-y-2">{scopeItems.map((scopeItem) => <CoverageRow key={scopeItem.id} item={scopeItem} selected={selected} disabled={!draft || busy} save={saveCoverage} />)}</div>
          </details>
        </Card>
        <Card className="space-y-3 p-5"><h3 className="font-semibold">Notes / Evidence</h3>
          <p className="text-sm text-slate-600">Evidence links to the original quote attachment. Page excerpts from native-text PDF must match the actual page exactly.</p>
          {selected.evidence.length === 0 ? <p className="text-sm text-slate-500">No specific evidence recorded yet.</p> : selected.evidence.map((evidence) => <div key={evidence.id} className="rounded-lg border p-2 text-sm">{evidence.source} · {evidence.attachment_id ? `Source file #${evidence.attachment_id}` : "Estimator note"}{evidence.page_number ? ` · Page ${evidence.page_number}` : ""}{evidence.excerpt && <blockquote className="mt-1 text-slate-600">{evidence.excerpt}</blockquote>}{evidence.note && <p>{evidence.note}</p>}{draft && <button type="button" disabled={busy} onClick={() => void act(() => bidRevisionsApi.removeEvidence(slug, projectId, quote.id, selected.id, evidence.id))} className="mt-2 font-semibold text-red-700">Remove Draft evidence</button>}</div>)}
          {draft && <div className="grid gap-2 md:grid-cols-2">
            <select aria-label="Evidence supports" value={evidenceTarget} onChange={(event) => setEvidenceTarget(event.target.value)} className="rounded-lg border p-2 text-sm"><option value="base_bid">Base Bid</option><option value="currency">Currency</option><option value="tax_treatment">Tax treatment</option>{selected.commercial_items.map((item) => <option key={item.id} value={`item:${item.id}`}>{item.kind} · {item.title}</option>)}</select>
            <select aria-label="Evidence source" value={evidenceSource} onChange={(event) => setEvidenceSource(event.target.value)} className="rounded-lg border p-2 text-sm"><option value="quote">Original quote</option><option value="estimator">Estimator note</option><option value="contractor">Contractor clarification</option></select>
            {evidenceSource === "quote" && <select aria-label="Evidence attachment" value={evidenceAttachment} onChange={(event) => setEvidenceAttachment(Number(event.target.value))} className="rounded-lg border p-2 text-sm">{quote.attachments.map((attachment) => <option key={attachment.id} value={attachment.id}>{attachment.filename}</option>)}</select>}
            {evidenceSource === "quote" && <input aria-label="Evidence page" type="number" min="1" value={evidencePage} onChange={(event) => setEvidencePage(event.target.value)} placeholder="PDF page, if applicable" className="rounded-lg border p-2 text-sm" />}
            <textarea aria-label="Exact quote excerpt" value={evidenceExcerpt} onChange={(event) => setEvidenceExcerpt(event.target.value)} placeholder="Exact contiguous excerpt only; never paraphrase" className="rounded-lg border p-2 text-sm" />
            <textarea aria-label="Evidence note" value={evidenceNote} onChange={(event) => setEvidenceNote(event.target.value)} placeholder="Optional human note" className="rounded-lg border p-2 text-sm" />
            <button type="button" disabled={busy} onClick={() => void addEvidence()} className="rounded-lg bg-blue-800 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">Add source evidence</button>
          </div>}
        </Card>
        {selected.status === "draft" && <Card className="space-y-2 border-amber-200 bg-amber-50 p-5"><h3 className="font-semibold">Ready for Comparison</h3><p className="text-sm">This is an explicit human gate. Ready commercial meaning is frozen; create a successor for later corrections.</p>
          {selected.readiness_blockers.length ? <ul className="list-inside list-disc text-sm text-amber-900">{selected.readiness_blockers.map((code) => <li key={code}>{bidReadinessCopy(code)}</li>)}</ul> : <p className="text-sm text-emerald-700">Required review checks complete.</p>}
          {canEdit && <button type="button" disabled={busy || selected.readiness_blockers.length > 0} onClick={() => void act(() => bidRevisionsApi.ready(slug, projectId, quote.id, selected.id))} className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">Mark Ready for Comparison</button>}
        </Card>}
      </>}
      <Card className="space-y-3 p-5"><h3 className="font-semibold">Optional AI-assisted extraction</h3><p className="text-sm text-slate-600">An explicit native-text PDF extraction produces suggestions only. No quote is processed on upload or page load, and AI cannot mark a bid Ready.</p>
        {canEdit && quote.attachments.filter((attachment) => attachment.content_type === "application/pdf").map((attachment) => <button type="button" key={attachment.id} disabled={busy} onClick={() => void extract(attachment.id)} className="mr-2 rounded-lg border border-indigo-300 px-3 py-2 text-sm font-semibold text-indigo-800">Extract Bid Details · {attachment.filename}</button>)}
        {extractions.map((run) => <div key={run.id} className="rounded-lg border p-3 text-sm"><strong>AI suggestion #{run.id}</strong> · {run.status}{run.safe_error_message && <p className="text-red-700">{run.safe_error_message}</p>}
          {run.status === "succeeded" && <details><summary className="cursor-pointer text-indigo-700">Review {run.candidate_count} grounded suggestions</summary><div className="mt-2 space-y-2">{run.candidates.map((candidate, index) => <BidCandidateRow key={`${run.id}-${index}`} candidate={candidate} index={index} decision={run.decisions.find((item) => item.candidate_index === index && item.revision_id === selectedId)?.decision} canReview={Boolean(draft) && !busy} decide={(choice, correction, note) => decide(run, index, candidate, choice, correction, note)} />)}</div></details>}
        </div>)}
      </Card>
    </>}
  </div>;
}

function CoverageRow({ item, selected, disabled, save }: {
  item: BidScopeItemChoice; selected: BidRevision; disabled: boolean;
  save: (id: number, state: string, wording: string, reviewed: boolean) => Promise<void>;
}) {
  const existing = selected.scope_coverage.find((coverage) => coverage.scope_item_id === item.id);
  const [state, setState] = useState(existing?.state ?? "not_addressed");
  const [wording, setWording] = useState(existing?.wording ?? "");
  const [reviewed, setReviewed] = useState(existing?.reviewed ?? false);
  const [coverageSource, setCoverageSource] = useState(existing);
  if (existing !== coverageSource) {
    setCoverageSource(existing);
    setState(existing?.state ?? "not_addressed");
    setWording(existing?.wording ?? "");
    setReviewed(existing?.reviewed ?? false);
  }
  return <div className="grid gap-2 rounded-lg border p-3 text-sm md:grid-cols-3"><strong>{item.title}</strong>
    <select aria-label={`${item.title} coverage`} disabled={disabled} value={state} onChange={(event) => setState(event.target.value)} className="rounded-lg border p-2"><option value="not_addressed">Not addressed</option><option value="included">Confirmed included</option><option value="excluded">Confirmed excluded</option><option value="qualified">Qualified / conditional</option><option value="needs_clarification">Needs clarification</option></select>
    <input aria-label={`${item.title} contractor wording`} disabled={disabled} value={wording} onChange={(event) => setWording(event.target.value)} placeholder="Exact contractor wording if stated" className="rounded-lg border p-2" />
    <label className="flex items-center gap-2"><input type="checkbox" disabled={disabled} checked={reviewed} onChange={(event) => setReviewed(event.target.checked)} />Reviewed by you</label>
    {!disabled && <button type="button" onClick={() => void save(item.id, state, wording, reviewed)} className="font-semibold text-blue-700">Save scope decision</button>}
  </div>;
}

function CommercialItemRow({ item, disabled, save, remove }: {
  item: BidCommercialItem; disabled: boolean;
  save: (values: Record<string, unknown>) => Promise<boolean>;
  remove: () => Promise<boolean>;
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(item.title);
  const [description, setDescription] = useState(item.description);
  const [treatment, setTreatment] = useState(item.treatment);
  const [amount, setAmount] = useState(item.amount ?? "");
  const [currency, setCurrency] = useState(item.currency);
  const [inBase, setInBase] = useState<string>(item.included_in_base);
  const [category, setCategory] = useState(item.category);
  const [label, setLabel] = useState(item.contractor_label);
  const [note, setNote] = useState(item.estimator_note);
  return <div className="space-y-2 rounded-lg border p-3 text-sm">
    <strong>{item.title}</strong> · {item.kind} · {item.treatment || "Treatment not stated"} · {displayBidMoney(item.amount, item.currency)}
    {item.contractor_label && <p>Contractor label: {item.contractor_label}</p>}
    {item.description && <p>{item.description}</p>}
    {!disabled && <div className="flex gap-3"><button type="button" onClick={() => setEditing(!editing)} className="font-semibold text-blue-700">{editing ? "Cancel edit" : "Edit Draft item"}</button><button type="button" onClick={() => void remove()} className="font-semibold text-red-700">Remove Draft item</button></div>}
    {editing && !disabled && <div className="grid gap-2 md:grid-cols-2">
      <input aria-label="Edit item title" value={title} onChange={(event) => setTitle(event.target.value)} className="rounded-lg border p-2" />
      <input aria-label="Edit contractor label" value={label} onChange={(event) => setLabel(event.target.value)} placeholder="Contractor label" className="rounded-lg border p-2" />
      <input aria-label="Edit description" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Description" className="rounded-lg border p-2" />
      <input aria-label="Edit category" value={category} onChange={(event) => setCategory(event.target.value)} placeholder="Category" className="rounded-lg border p-2" />
      <select aria-label="Edit treatment" value={treatment} onChange={(event) => setTreatment(event.target.value)} className="rounded-lg border p-2"><option value="">Not stated</option><option value="add">Add</option><option value="deduct">Deduct</option><option value="no_cost">No cost</option><option value="price_on_request">Price on request</option><option value="included">Included</option><option value="excluded">Excluded</option><option value="extra">Extra</option><option value="allowance">Allowance</option><option value="not_stated">Not stated</option></select>
      <input aria-label="Edit amount" value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="Amount if stated" className="rounded-lg border p-2" />
      <input aria-label="Edit currency" value={currency} onChange={(event) => setCurrency(event.target.value)} placeholder="Currency if amount stated" className="rounded-lg border p-2" />
      <select aria-label="Edit included in Base Bid" value={inBase} onChange={(event) => setInBase(event.target.value)} className="rounded-lg border p-2"><option value="unclear">Base Bid treatment unclear</option><option value="yes">Included in Base Bid</option><option value="no">Not included in Base Bid</option></select>
      <input aria-label="Edit estimator note" value={note} onChange={(event) => setNote(event.target.value)} placeholder="Estimator note" className="rounded-lg border p-2" />
      <button type="button" onClick={() => void save({ title, contractor_label: label, description, category, treatment, amount: amount || null, currency: amount ? currency.toUpperCase() : "", included_in_base: inBase, estimator_note: note }).then((ok) => { if (ok) setEditing(false); })} className="rounded-lg bg-blue-800 px-3 py-2 font-semibold text-white">Save Draft item</button>
    </div>}
  </div>;
}

function BidCandidateRow({ candidate, index, decision, canReview, decide }: {
  candidate: BidCandidate; index: number; decision?: string; canReview: boolean;
  decide: (choice: "accepted" | "corrected" | "ignored", correction?: string, note?: string) => Promise<void>;
}) {
  const [correction, setCorrection] = useState("");
  const [correctionNote, setCorrectionNote] = useState("");
  const missingScopeItem = candidate.kind === "scope_coverage" && candidate.scope_item_id === null;
  return <div className="space-y-2 rounded-lg border p-3 text-sm">
    <strong>{candidate.title}</strong> · {candidate.kind} · Source page {candidate.page_number}
    <p>{displayBidCandidateValue(candidate)}</p>
    <blockquote className="border-l-2 border-indigo-200 pl-2 text-slate-600">{candidate.excerpt}</blockquote>
    {decision ? <p className="font-semibold text-emerald-700">{decision === "ignored" ? "Ignored by you" : decision === "corrected" ? "Human corrected" : "Human confirmed"}</p> : canReview && <>
      {missingScopeItem && <p className="rounded-lg bg-amber-50 p-2 text-amber-900">No exact Ready scope item is linked. Ignore this suggestion; record coverage manually only if you can identify the exact scope item.</p>}
      {!missingScopeItem && <>
      <input aria-label={`Correct suggestion ${index + 1}`} value={correction} onChange={(event) => setCorrection(event.target.value)} placeholder={candidate.kind === "tax" ? "included / extra / exempt / not_stated" : candidate.kind === "currency" ? "Three-letter currency code" : candidate.kind === "scope_coverage" ? "included / excluded / qualified / not_addressed / needs_clarification" : "Correct amount or description before confirming"} className="w-full rounded-lg border p-2" />
      <input aria-label={`Correction reason ${index + 1}`} value={correctionNote} onChange={(event) => setCorrectionNote(event.target.value)} placeholder="Why you corrected this suggestion" className="w-full rounded-lg border p-2" />
      </>}
      <div className="flex flex-wrap gap-3">
        {!missingScopeItem && <button type="button" onClick={() => void decide("accepted")} className="font-semibold text-emerald-700">Human confirm</button>}
        {!missingScopeItem && <button type="button" disabled={!correction || !correctionNote} onClick={() => void decide("corrected", correction, correctionNote)} className="font-semibold text-blue-700 disabled:opacity-50">Correct & confirm</button>}
        <button type="button" onClick={() => void decide("ignored")} className="font-semibold text-slate-600">Ignore</button>
      </div>
    </>}
  </div>;
}

function message(reason: unknown) {
  return reason instanceof Error ? reason.message : "The bid request could not be completed.";
}
