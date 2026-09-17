"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import {
  bidHumanReviewsApi,
  type BidHumanDecision,
  type BidHumanDecisionState,
  type BidHumanReview,
  type BidHumanReviewOutcome,
} from "@/lib/bid-human-reviews";
import { displayBidMoney } from "@/lib/bid-money";

export function HumanBidReview({ slug, projectId, comparisonId, canEdit }: { slug: string; projectId: number; comparisonId: number; canEdit: boolean }) {
  const [review, setReview] = useState<BidHumanReview | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    bidHumanReviewsApi.list(slug, projectId, comparisonId, controller.signal)
      .then((data) => setReview(data.current))
      .catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Human review could not be loaded."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [slug, projectId, comparisonId]);

  async function mutate(action: () => Promise<BidHumanReview>) {
    setBusy(true); setError("");
    try { setReview(await action()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The human review could not be updated."); }
    finally { setBusy(false); }
  }

  if (loading) return <Card className="p-5 text-sm">Loading human review…</Card>;
  if (!review) return <Card className="p-5"><h3 className="font-semibold">Human procurement review</h3><p className="mt-1 text-sm text-slate-600">No human bidder decisions have been recorded. Nothing is preselected.</p>{canEdit && <button type="button" disabled={busy} onClick={() => void mutate(() => bidHumanReviewsApi.create(slug, projectId, comparisonId))} className="mt-3 rounded-lg bg-[#173f5f] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Start Human Review</button>}{error && <p className="mt-3 text-sm text-red-700" role="alert">{error}</p>}</Card>;
  if (review.status === "finalized") return <FinalizedReview review={review} />;
  return <DraftReview key={JSON.stringify(review)} review={review} canEdit={canEdit} busy={busy} error={error} saveDecision={(decision, state, note) => void mutate(() => bidHumanReviewsApi.updateDecision(slug, projectId, comparisonId, review.id, decision.id, { state, note }))} saveOutcome={(outcome, selected, rationale) => void mutate(() => bidHumanReviewsApi.updateOutcome(slug, projectId, comparisonId, review.id, { outcome, selected_entry_id: selected, rationale }))} finalize={() => { if (window.confirm("Finalize this human review? Bidder decisions and the overall outcome will become immutable.")) void mutate(() => bidHumanReviewsApi.finalize(slug, projectId, comparisonId, review.id)); }} />;
}

function DraftReview({ review, canEdit, busy, error, saveDecision, saveOutcome, finalize }: { review: BidHumanReview; canEdit: boolean; busy: boolean; error: string; saveDecision: (decision: BidHumanDecision, state: BidHumanDecisionState, note: string) => void; saveOutcome: (outcome: BidHumanReviewOutcome, selected: number | null, rationale: string) => void; finalize: () => void }) {
  const [outcome, setOutcome] = useState<BidHumanReviewOutcome>(review.outcome);
  const [selected, setSelected] = useState<number | null>(review.selected_entry_id);
  const [rationale, setRationale] = useState(review.rationale);
  const shortlisted = review.decisions.filter((item) => item.state === "shortlisted");
  return <Card className="border-indigo-200 p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-semibold">Human procurement review · Draft V{review.sequence}</h3><p className="mt-1 text-sm text-slate-600">Review each bidder explicitly. Price and comparison data remain unchanged.</p></div><span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-bold text-amber-800">Decision in progress</span></div>
    {error && <p className="mt-3 text-sm text-red-700" role="alert">{error}</p>}
    <div className="mt-4 grid gap-3">{review.decisions.map((decision) => <DecisionCard key={`${decision.id}:${decision.state}:${decision.note}`} decision={decision} disabled={!canEdit || busy} save={saveDecision} />)}</div>
    <div className="mt-5 border-t pt-5"><h4 className="font-semibold">Overall human decision</h4><div className="mt-3 grid gap-3 md:grid-cols-2"><label className="text-sm font-medium">Outcome<select disabled={!canEdit || busy} value={outcome} onChange={(event) => { const value = event.target.value as BidHumanReviewOutcome; setOutcome(value); if (value !== "selected_for_proposal") setSelected(null); }} className="mt-1 w-full rounded-lg border p-2"><option value="">Choose outcome</option><option value="selected_for_proposal">Selected for Proposal</option><option value="no_acceptable_bid">No Acceptable Bid</option></select></label>{outcome === "selected_for_proposal" && <label className="text-sm font-medium">Shortlisted bid<select disabled={!canEdit || busy} value={selected ?? ""} onChange={(event) => setSelected(event.target.value ? Number(event.target.value) : null)} className="mt-1 w-full rounded-lg border p-2"><option value="">Choose one Shortlisted bid</option>{shortlisted.map((item) => <option key={item.id} value={item.entry_id}>{item.company_name}</option>)}</select></label>}</div><label className="mt-3 block text-sm font-medium">Decision rationale<textarea disabled={!canEdit || busy} value={rationale} onChange={(event) => setRationale(event.target.value)} className="mt-1 min-h-24 w-full rounded-lg border p-3" placeholder="Record why this procurement decision was made." /></label>{canEdit && <button type="button" disabled={busy} onClick={() => saveOutcome(outcome, outcome === "selected_for_proposal" ? selected : null, rationale)} className="mt-3 rounded-lg border border-blue-300 px-3 py-2 text-sm font-semibold text-blue-800 disabled:opacity-50">Save Human Decision</button>}</div>
    <div className="mt-5 rounded-lg bg-slate-50 p-4"><p className="text-sm font-semibold">Finalization check</p>{review.blockers.length ? <ul className="mt-2 list-disc pl-5 text-sm text-amber-800">{review.blockers.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="mt-2 text-sm text-emerald-700">All required human decisions are recorded.</p>}<p className="mt-2 text-xs text-slate-500">Selected for Proposal is an internal procurement decision. It is not an award or contractor notification.</p>{canEdit && <button type="button" disabled={busy || review.blockers.length > 0} onClick={finalize} className="mt-3 rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Finalize Human Review</button>}</div>
  </Card>;
}

function DecisionCard({ decision, disabled, save }: { decision: BidHumanDecision; disabled: boolean; save: (decision: BidHumanDecision, state: BidHumanDecisionState, note: string) => void }) {
  const [note, setNote] = useState(decision.note);
  return <div className="rounded-xl border border-slate-200 p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="font-semibold">{decision.company_name}</p><p className="text-sm text-slate-600">Submitted: {displayBidMoney(decision.source_base_bid, decision.currency)} · Evaluated: {displayBidMoney(decision.evaluated_amount, decision.currency)}</p></div><span className={`rounded-full px-3 py-1 text-xs font-bold ${decision.state === "shortlisted" ? "bg-emerald-100 text-emerald-800" : decision.state === "not_shortlisted" ? "bg-slate-200 text-slate-700" : "bg-amber-100 text-amber-800"}`}>{decision.state === "shortlisted" ? "Shortlisted" : decision.state === "not_shortlisted" ? "Not Shortlisted" : "Undecided"}</span></div><label className="mt-3 block text-sm font-medium">Review note<input disabled={disabled} value={note} onChange={(event) => setNote(event.target.value)} className="mt-1 w-full rounded-lg border p-2" placeholder="Optional bidder-specific rationale" /></label>{!disabled && <div className="mt-3 flex flex-wrap gap-2"><button type="button" onClick={() => save(decision, "shortlisted", note)} className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-semibold text-white">Shortlist</button><button type="button" onClick={() => save(decision, "not_shortlisted", note)} className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold">Do Not Shortlist</button></div>}</div>;
}

function FinalizedReview({ review }: { review: BidHumanReview }) {
  return <Card className="border-emerald-200 p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-semibold">Human procurement review · Finalized V{review.sequence}</h3><p className="mt-1 text-sm text-slate-600">{review.outcome === "selected_for_proposal" ? `Selected for Proposal: ${review.selected_company_name}` : "No Acceptable Bid"}</p>{review.finalized_at && <p className="mt-1 text-xs text-slate-500">Finalized by {review.finalized_by_name ?? "authorized reviewer"} · {new Date(review.finalized_at).toLocaleString()}</p>}</div><span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-bold text-emerald-800">Finalized</span></div><div className="mt-4 grid gap-2">{review.decisions.map((item) => <div key={item.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-50 p-3 text-sm"><span><strong>{item.company_name}</strong>{item.note ? ` · ${item.note}` : ""}</span><span>{item.state === "shortlisted" ? "Shortlisted" : "Not Shortlisted"}</span></div>)}</div><p className="mt-4 whitespace-pre-wrap text-sm"><strong>Rationale:</strong> {review.rationale}</p><p className="mt-3 text-xs text-slate-500">Selected for Proposal is an internal procurement decision. It is not an award or contractor notification. Finalized records are immutable; corrections require a successor review.</p></Card>;
}
