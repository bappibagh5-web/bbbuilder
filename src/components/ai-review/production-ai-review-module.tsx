"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, Bot, CheckCircle2, Clock3, FileSearch, LoaderCircle, RotateCcw } from "lucide-react";
import type { OrganizationMembership } from "@/lib/auth";
import { analysisApi, type AnalysisRun, type ExtractedFinding, type FindingDecision, type IntelligenceCandidateRun, type IntelligenceConflict, type IntelligenceReadiness, type IntelligenceSnapshot, type MachineCandidate } from "@/lib/analysis";
import { analysisActions, deriveAnalysisState, MACHINE_REVIEW_WARNING, shouldPollAnalysis } from "@/lib/analysis-state";
import { canSubmitFindingReview, findingReviewActions, REVIEWED_NOT_APPROVED_WARNING, reviewProgress } from "@/lib/finding-review-state";
import { selectedRunsRespectRevisionBoundary, snapshotActions, snapshotStatus } from "@/lib/intelligence-snapshot-state";
import { documentsApi, type ProcessingJob, type ProductionDocument, type ProductionDocumentRevision } from "@/lib/documents";
import type { ProductionProject } from "@/lib/projects";
import { Card } from "@/components/ui/card";

type RevisionOption = { document: ProductionDocument; revision: ProductionDocumentRevision };
const categoryLabels: Record<string, string> = {
  project_fact: "Project Fact Candidates", date_deadline: "Dates / Deadlines", bid_condition: "Bid Conditions",
  scope_trade: "Scope / Trade Candidates", responsibility: "Responsibilities", permit_inspection: "Permits / Inspections",
  landlord_requirement: "Landlord Requirements", owner_third_party_item: "Owner / Vendor Items",
  commercial: "Alternates / Allowances / Exclusions", submittal_closeout: "Submittal / Closeout Requirements", open_question: "Open Questions",
};

export function ProductionAIReviewModule({ project, membership }: { project: ProductionProject; membership: OrganizationMembership }) {
  const slug = membership.organization.slug;
  const canOperate = membership.role === "admin" || membership.role === "estimator_operator";
  const [options, setOptions] = useState<RevisionOption[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [runs, setRuns] = useState<AnalysisRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [findings, setFindings] = useState<ExtractedFinding[]>([]);
  const [conflicts, setConflicts] = useState<IntelligenceConflict[]>([]);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const polls = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    documentsApi.list(slug, project.id, controller.signal).then(async ({ results }) => {
      const revisionLists = await Promise.all(results.map(async (document) => ({ document, revisions: (await documentsApi.revisions(slug, project.id, document.id, controller.signal)).results })));
      const next = revisionLists.flatMap(({ document, revisions }) => revisions.map((revision) => ({ document, revision })));
      setOptions(next); setSelectedId((current) => current ?? next[0]?.revision.id ?? null);
    }).catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Documents are unavailable."); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [project.id, slug]);

  const selected = options.find((item) => item.revision.id === selectedId) ?? null;
  const refresh = useCallback(async (signal?: AbortSignal) => {
    if (!selected) return;
    const [nextJobs, nextRuns] = await Promise.all([
      documentsApi.processingJobs(slug, project.id, selected.document.id, selected.revision.id, signal),
      analysisApi.list(slug, project.id, selected.document.id, selected.revision.id, signal),
    ]);
    setJobs(nextJobs); setRuns(nextRuns);
    setSelectedRunId((current) => current && nextRuns.some((run) => run.id === current) ? current : nextRuns[0]?.id ?? null);
    return nextRuns;
  }, [project.id, selected, slug]);

  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController(); let timer: number | undefined; let active = true; polls.current = 0;
    async function check() {
      let currentRuns: AnalysisRun[] = [];
      try { currentRuns = (await refresh(controller.signal)) ?? []; setError(null); }
      catch (reason) { if (active && !controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Analysis state is unavailable."); }
      const activeRun = currentRuns.some((run) => run.status === "queued" || run.status === "running");
      if (active && activeRun && shouldPollAnalysis(currentRuns[0]?.status ?? "ready", polls.current)) { polls.current += 1; timer = window.setTimeout(() => void check(), 5_000); }
    }
    void check();
    return () => { active = false; controller.abort(); if (timer) window.clearTimeout(timer); };
  }, [refresh, selected]);

  const latestSource = jobs.find((job) => job.job_type === "source_verification");
  const latestPdf = jobs.find((job) => job.job_type === "pdf_indexing");
  const latestRun = runs[0];
  const selectedRun = runs.find((run) => run.id === selectedRunId) ?? latestRun;
  const isPdf = selected ? (selected.revision.project_file.file_asset.detected_mime_type || selected.revision.project_file.file_asset.declared_mime_type) === "application/pdf" : false;
  const state = deriveAnalysisState({ isPdf, sourceStatus: latestSource?.status, pdfStatus: latestPdf?.status, pageCount: latestPdf?.result_metadata.page_count ?? 0, runStatus: latestRun?.status });
  const actions = analysisActions(state, canOperate);
  const reviewActions = findingReviewActions(canOperate);

  const refreshReview = useCallback(async (signal?: AbortSignal) => {
    if (!selectedRun) return;
    const [nextFindings, nextConflicts] = await Promise.all([
      analysisApi.findings(slug, project.id, selectedRun.id, signal),
      analysisApi.conflicts(slug, project.id, signal),
    ]);
    setFindings(nextFindings);
    setConflicts(nextConflicts.filter((conflict) => conflict.analysis_run === selectedRun.id));
  }, [project.id, selectedRun, slug]);

  useEffect(() => {
    if (!selectedRun) return;
    const controller = new AbortController();
    async function loadReview() {
      try { await refreshReview(controller.signal); }
      catch (reason) { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Finding review is unavailable."); }
    }
    void loadReview();
    return () => controller.abort();
  }, [refreshReview, selectedRun]);

  async function act(action: () => Promise<AnalysisRun>) {
    if (acting) return; setActing(true); setError(null);
    try { const created = await action(); setSelectedRunId(created.id); polls.current = 0; await refresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The analysis request failed."); }
    finally { setActing(false); }
  }

  if (loading) return <ModuleState icon={LoaderCircle} title="Loading AI analysis…" spin />;
  if (!options.length) return <ModuleState icon={FileSearch} title="No document revisions available" detail="Upload, verify, and index a PDF before requesting AI analysis." />;

  return <div className="space-y-5">
    <section className="flex flex-col gap-4 rounded-xl border bg-slate-50 p-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0 flex-1"><p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Production AI Review</p><h2 className="mt-1 text-lg font-semibold">Structured document analysis</h2><p className="mt-1 text-sm text-slate-600">Explicit, versioned machine analysis of one immutable indexed revision.</p></div>
      <label className="block min-w-0 text-xs font-semibold sm:w-96">Document revision<select value={selectedId ?? ""} onChange={(event) => { setSelectedId(Number(event.target.value)); setJobs([]); setRuns([]); setSelectedRunId(null); setFindings([]); setConflicts([]); }} className="mt-1 h-10 w-full rounded-lg border bg-white px-3 text-sm font-normal">{options.map(({ document, revision }) => <option key={revision.id} value={revision.id}>{document.title} — {revision.revision_label || `Revision #${revision.id}`}</option>)}</select></label>
    </section>
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm font-medium text-amber-900">{MACHINE_REVIEW_WARNING} Results are candidates, not approved project intelligence.</div>
    {error && <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</div>}
    <Card className="p-4 sm:p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><div className="flex items-center gap-2"><StateIcon state={state} /><h3 className="font-semibold">{stateLabel(state)}</h3></div><p className="mt-1 text-sm text-slate-500">{stateDetail(state, canOperate)}</p></div><div className="flex gap-2">{(actions.canRun || actions.canRunAgain) && selected && <button type="button" disabled={acting} onClick={() => void act(() => analysisApi.request(slug, project.id, selected.document.id, selected.revision.id))} className="inline-flex h-10 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50"><Bot className="h-4 w-4" />{acting ? "Requesting…" : actions.canRunAgain ? "Run AI Analysis Again" : "Run AI Analysis"}</button>}{actions.canRetry && latestRun && <button type="button" disabled={acting} onClick={() => void act(() => analysisApi.retry(slug, project.id, latestRun.id))} className="inline-flex h-10 items-center gap-2 rounded-lg border bg-white px-4 text-sm font-semibold disabled:opacity-50"><RotateCcw className="h-4 w-4" />{acting ? "Requesting…" : "Retry Analysis"}</button>}</div></div>{state === "failed" && latestRun?.safe_failure_message && <p className="mt-3 text-sm text-red-700">{latestRun.safe_failure_message}</p>}</Card>
    {selectedRun?.status === "succeeded" && <MachineResult run={selectedRun} />}
    {selectedRun?.status === "succeeded" && <HumanReviewPanel run={selectedRun} findings={findings} conflicts={conflicts} canOperate={canOperate} actions={reviewActions} slug={slug} projectId={project.id} acting={acting} setActing={setActing} setError={setError} refresh={refreshReview} />}
    <ProjectIntelligencePanel slug={slug} projectId={project.id} canOperate={canOperate} />
    <RunHistory runs={runs} selectedRunId={selectedRun?.id ?? null} onSelect={(id) => { setSelectedRunId(id); setFindings([]); setConflicts([]); }} />
  </div>;
}

function HumanReviewPanel({ run, findings, conflicts, canOperate, actions, slug, projectId, acting, setActing, setError, refresh }: { run: AnalysisRun; findings: ExtractedFinding[]; conflicts: IntelligenceConflict[]; canOperate: boolean; actions: ReturnType<typeof findingReviewActions>; slug: string; projectId: number; acting: boolean; setActing: (value: boolean) => void; setError: (value: string | null) => void; refresh: () => Promise<void> }) {
  const progress = reviewProgress(findings);
  async function perform(action: () => Promise<unknown>) {
    if (acting) return;
    setActing(true); setError(null);
    try { await action(); await refresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The review action failed."); }
    finally { setActing(false); }
  }
  if (!findings.length) return <Card className="border-blue-200 p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wider text-blue-700">Human review</p><h3 className="mt-1 font-semibold">Prepare Run #{run.id} findings for review</h3><p className="mt-1 text-sm text-slate-600">Deterministically materialize persisted machine candidates. This makes no AI call and creates no approved intelligence.</p></div>{actions.canMaterialize && <button type="button" disabled={acting} onClick={() => void perform(() => analysisApi.materialize(slug, projectId, run.id))} className="h-10 rounded-lg bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50">{acting ? "Preparing…" : "Prepare Findings for Review"}</button>}</div>{!canOperate && <p className="mt-3 text-sm text-slate-500">An Admin or Estimator / Operator may prepare this run.</p>}</Card>;
  return <section className="space-y-4"><div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm font-medium text-blue-900">{REVIEWED_NOT_APPROVED_WARNING}</div><Card className="p-4"><div className="flex flex-wrap gap-x-6 gap-y-2 text-sm"><span><strong>{progress.total}</strong> findings</span><span><strong>{progress.reviewed}</strong> reviewed</span><span><strong>{progress.unreviewed}</strong> unreviewed</span><span><strong>{conflicts.filter((item) => item.status === "open").length}</strong> open conflicts</span></div></Card><div className="space-y-3">{findings.map((finding) => <FindingCard key={finding.id} finding={finding} canReview={actions.canReview} acting={acting} onReview={(decision, reviewedValue, reviewNote) => perform(() => analysisApi.review(slug, projectId, finding.id, { decision, reviewed_value: reviewedValue, review_note: reviewNote }))} />)}</div><ConflictPanel conflicts={conflicts} canResolve={actions.canResolveConflict} acting={acting} onResolve={(conflict, status, note) => perform(() => analysisApi.resolveConflict(slug, projectId, conflict.id, { status, resolution_note: note }))} /></section>;
}

function ProjectIntelligencePanel({ slug, projectId, canOperate }: { slug: string; projectId: number; canOperate: boolean }) {
  const [candidates, setCandidates] = useState<IntelligenceCandidateRun[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [readiness, setReadiness] = useState<IntelligenceReadiness | null>(null);
  const [snapshots, setSnapshots] = useState<IntelligenceSnapshot[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const actions = snapshotActions(canOperate, readiness);
  const load = useCallback(async () => {
    const [candidatePayload, history] = await Promise.all([
      analysisApi.intelligenceCandidates(slug, projectId),
      analysisApi.snapshots(slug, projectId),
    ]);
    setCandidates(candidatePayload.candidate_runs);
    setSnapshots(history);
  }, [projectId, slug]);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load().catch((reason) => setMessage(reason instanceof Error ? reason.message : "Project intelligence is unavailable."));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);
  useEffect(() => {
    if (!selected.length) return;
    const controller = new AbortController();
    void analysisApi.intelligenceReadiness(slug, projectId, selected, controller.signal)
      .then(setReadiness)
      .catch((reason) => { if (!controller.signal.aborted) setMessage(reason instanceof Error ? reason.message : "Readiness check failed."); });
    return () => controller.abort();
  }, [projectId, selected, slug]);
  function toggle(candidate: IntelligenceCandidateRun) {
    setMessage(null);
    setReadiness(null);
    setSelected((current) => current.includes(candidate.id)
      ? current.filter((id) => id !== candidate.id)
      : [...current.filter((id) => candidates.find((item) => item.id === id)?.document_revision_id !== candidate.document_revision_id), candidate.id]);
  }
  async function createSnapshot() {
    if (!actions.canCreate || !selectedRunsRespectRevisionBoundary(selected, candidates)) return;
    setBusy(true); setMessage(null);
    try {
      await analysisApi.createSnapshot(slug, projectId, selected);
      await load(); setMessage("Immutable intelligence snapshot created.");
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : "Snapshot creation failed."); }
    finally { setBusy(false); }
  }
  async function approve(snapshot: IntelligenceSnapshot) {
    if (!actions.canApprove(snapshot)) return;
    const count = snapshot.summary_counts.approved_entries ?? 0;
    if (!window.confirm(`Approve Intelligence Snapshot V${snapshot.version} with ${count} intelligence entries? Approval targets this exact immutable version. Future review changes require a new snapshot.`)) return;
    setBusy(true); setMessage(null);
    try {
      await analysisApi.approveSnapshot(slug, projectId, snapshot.id);
      await load(); setMessage(`Snapshot V${snapshot.version} approved.`);
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : "Snapshot approval failed."); }
    finally { setBusy(false); }
  }
  return <section className="space-y-4"><Card className="p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wider text-blue-700">Project intelligence readiness</p><h3 className="mt-1 font-semibold">Select complete reviewed source runs</h3><p className="mt-1 text-sm text-slate-600">Select at most one successful AnalysisRun per current document revision. Every finding in each selected run is included automatically.</p></div><div className="flex gap-2"><button type="button" disabled={busy} onClick={() => void load()} className="h-10 rounded-lg border px-3 text-sm font-semibold disabled:opacity-50">Refresh readiness</button>{canOperate && <button type="button" disabled={busy || !actions.canCreate} onClick={() => void createSnapshot()} className="h-10 rounded-lg bg-primary px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40">Create Intelligence Snapshot</button>}</div></div>{message && <p className="mt-3 text-sm text-slate-700">{message}</p>}<div className="mt-4 space-y-2">{candidates.map((candidate) => <label key={candidate.id} className={`flex gap-3 rounded-lg border p-3 ${candidate.is_current_revision ? "bg-white" : "bg-slate-50 text-slate-500"}`}><input type="checkbox" checked={selected.includes(candidate.id)} disabled={!canOperate || !candidate.is_current_revision} onChange={() => toggle(candidate)} className="mt-1" /><span className="min-w-0"><span className="block text-sm font-semibold">{candidate.document_title} · {candidate.revision_label || `Revision #${candidate.document_revision_id}`} · Run #{candidate.id}</span><span className="mt-1 block text-xs">{candidate.finding_count} findings · {candidate.unreviewed_count} unreviewed · {candidate.needs_clarification_count} need clarification · {candidate.is_current_revision ? "Current revision" : "Historical revision"}</span></span></label>)}{!candidates.length && <p className="text-sm text-slate-500">No materialized successful analysis runs are available.</p>}</div>{selected.length > 0 && readiness && <div className={`mt-4 rounded-lg border p-3 text-sm ${readiness.eligible ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-amber-200 bg-amber-50 text-amber-900"}`}><p className="font-semibold">{readiness.eligible ? "Eligible for immutable snapshot" : "Cannot create snapshot"}</p>{readiness.blockers.map((blocker) => <p key={`${blocker.code}-${blocker.message}`} className="mt-1">{blocker.message}</p>)}</div>}{!canOperate && <p className="mt-3 text-sm text-slate-500">Viewer access is read-only. An Admin or Estimator / Operator may create and approve snapshots.</p>}</Card><SnapshotHistory snapshots={snapshots} canOperate={canOperate} busy={busy} onApprove={approve} /></section>;
}

function SnapshotHistory({ snapshots, canOperate, busy, onApprove }: { snapshots: IntelligenceSnapshot[]; canOperate: boolean; busy: boolean; onApprove: (snapshot: IntelligenceSnapshot) => void }) {
  const actions = snapshotActions(canOperate, null);
  return <Card className="p-5"><h3 className="font-semibold">Intelligence snapshot history</h3><p className="mt-1 text-sm text-slate-500">Immutable snapshots of reviewed intelligence. Historical versions remain inspectable.</p><div className="mt-4 space-y-4">{snapshots.map((snapshot, index) => { const status = snapshotStatus(snapshot); return <details key={snapshot.id} className="rounded-lg border bg-white p-4" open={index === 0}><summary className="cursor-pointer list-none"><div className="flex flex-wrap items-center justify-between gap-2"><div><p className="font-semibold">Snapshot V{snapshot.version} · {status.replaceAll("_", " ")}</p><p className="mt-1 text-xs text-slate-500">Created {new Date(snapshot.created_at).toLocaleString("en-CA")} by {snapshot.created_by} · {snapshot.summary_counts.approved_entries ?? 0} intelligence entries · {snapshot.fingerprint.slice(0, 12)}…</p></div>{actions.canApprove(snapshot) && <button type="button" disabled={busy} onClick={(event) => { event.preventDefault(); void onApprove(snapshot); }} className="h-9 rounded-lg bg-primary px-3 text-xs font-semibold text-white disabled:opacity-50">Approve Intelligence Snapshot</button>}</div></summary>{snapshot.is_stale && <p className="mt-3 rounded bg-amber-50 p-2 text-sm text-amber-900">This snapshot is based on an older review or source state. Create a new snapshot before approval. Any prior approval remains historical.</p>}{snapshot.approval && <div className="mt-3 rounded bg-emerald-50 p-3 text-sm text-emerald-900"><p className="font-semibold">Approved project intelligence</p><p>Approved by {snapshot.approval.approver} on {new Date(snapshot.approval.approved_at).toLocaleString("en-CA")}</p>{snapshot.approval.approval_note && <p className="mt-1">{snapshot.approval.approval_note}</p>}</div>}<p className="mt-3 text-xs font-semibold uppercase tracking-wider text-slate-500">Immutable snapshot of reviewed intelligence</p>{snapshot.sources.map((source) => <div key={source.id} className="mt-3 rounded-lg bg-slate-50 p-3"><p className="text-sm font-semibold">{source.document_title} · {source.revision_label || `Revision #${source.document_revision}`} · Analysis Run #{source.analysis_run}</p>{source.entries.map((entry) => <div key={entry.id} className="mt-2 border-t pt-2 text-sm"><p className="font-medium">{entry.subject} · {entry.decision.replaceAll("_", " ")}</p><p className="text-slate-700">{entry.included_in_intelligence ? entry.effective_value : "Rejected — preserved in manifest, excluded from approved intelligence."}</p><p className="mt-1 text-xs text-slate-500">Finding #{entry.finding} · Review #{entry.finding_review}{entry.provenance.map((item) => ` · Page ${item.page_number}${item.sheet_number ? ` / ${item.sheet_number}` : ""}`)}</p></div>)}</div>)}</details>; })}{!snapshots.length && <p className="text-sm text-slate-500">No intelligence snapshots have been created.</p>}</div></Card>;
}

function FindingCard({ finding, canReview, acting, onReview }: { finding: ExtractedFinding; canReview: boolean; acting: boolean; onReview: (decision: FindingDecision, value: string, note: string) => void }) {
  const [editing, setEditing] = useState(false); const [value, setValue] = useState(finding.effective_value || finding.machine_value); const [note, setNote] = useState("");
  const currentReview = finding.reviews.at(-1);
  const canAccept = canSubmitFindingReview(canReview, currentReview, "accepted", "", note);
  const canReject = canSubmitFindingReview(canReview, currentReview, "rejected", "", note);
  const canClarify = canSubmitFindingReview(canReview, currentReview, "needs_clarification", "", note);
  return <Card className="p-5"><div className="flex flex-wrap items-start justify-between gap-2"><div><p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Machine candidate · Run #{finding.analysis_run}</p><h3 className="mt-1 font-semibold">{finding.subject}</h3></div><span className="rounded bg-slate-100 px-2 py-1 text-xs font-semibold capitalize">{finding.review_status.replaceAll("_", " ")}</span></div><p className="mt-3 text-sm text-slate-700">{finding.machine_value}</p><p className="mt-1 text-xs text-slate-500">{finding.category.replaceAll("_", " ")} · {finding.machine_support.replaceAll("_", " ")}</p><div className="mt-4 rounded-lg bg-slate-50 p-3"><p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Source evidence</p>{finding.sources.map((source) => <div key={source.id} className="mt-2 text-sm"><p className="font-medium">{source.document_title} · {source.revision_label || `Revision #${source.document_revision}`} · Page {source.page_number}{source.sheet_number ? ` · ${source.sheet_number}${source.sheet_title ? ` — ${source.sheet_title}` : ""}` : ""}</p><p className="mt-1 text-slate-600">{source.evidence_excerpt ? `“${source.evidence_excerpt}”` : `Visual evidence: ${source.visual_evidence_description}`}</p></div>)}</div>{finding.review_status !== "unreviewed" && <div className="mt-4 rounded-lg border border-blue-100 bg-blue-50 p-3 text-sm"><p className="font-semibold">Reviewed finding</p>{finding.effective_value && <p className="mt-1">Reviewed value: {finding.effective_value}</p>}<p className="mt-1 text-xs text-slate-600">{finding.reviews.length} review decision{finding.reviews.length === 1 ? "" : "s"} preserved</p></div>}{canReview && <div className="mt-4 space-y-2">{editing && <textarea value={value} onChange={(event) => setValue(event.target.value)} maxLength={2000} className="min-h-20 w-full rounded-lg border p-2 text-sm" aria-label="Reviewed value" />}<input value={note} onChange={(event) => setNote(event.target.value)} maxLength={1000} placeholder="Review note (optional)" className="h-10 w-full rounded-lg border px-3 text-sm" /><div className="flex flex-wrap gap-2"><button disabled={acting || !canAccept} onClick={() => onReview("accepted", "", note)} className="rounded-lg border px-3 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400">Accept</button><button disabled={acting} onClick={() => editing ? onReview("edited_accepted", value, note) : setEditing(true)} className="rounded-lg border px-3 py-2 text-xs font-semibold disabled:opacity-50">{editing ? "Save Edited / Accepted" : "Edit / Accept"}</button><button disabled={acting || !canReject} onClick={() => onReview("rejected", "", note)} className="rounded-lg border px-3 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400">Reject</button><button disabled={acting || !canClarify} onClick={() => onReview("needs_clarification", "", note)} className="rounded-lg border px-3 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400">Needs Clarification</button></div></div>}</Card>;
}

function ConflictPanel({ conflicts, canResolve, acting, onResolve }: { conflicts: IntelligenceConflict[]; canResolve: boolean; acting: boolean; onResolve: (conflict: IntelligenceConflict, status: "resolved" | "dismissed", note: string) => void }) {
  if (!conflicts.length) return <Card className="p-5"><h3 className="font-semibold">Conflicts</h3><p className="mt-1 text-sm text-slate-500">No deterministic material conflicts were detected for this AnalysisRun.</p></Card>;
  return <Card className="p-5"><h3 className="font-semibold">Conflicts</h3><div className="mt-3 space-y-4">{conflicts.map((conflict) => <ConflictItem key={conflict.id} conflict={conflict} canResolve={canResolve} acting={acting} onResolve={onResolve} />)}</div></Card>;
}

function ConflictItem({ conflict, canResolve, acting, onResolve }: { conflict: IntelligenceConflict; canResolve: boolean; acting: boolean; onResolve: (conflict: IntelligenceConflict, status: "resolved" | "dismissed", note: string) => void }) {
  const [note, setNote] = useState("");
  return <div className="rounded-lg border p-3"><div className="flex justify-between gap-2"><p className="text-sm font-semibold">{conflict.semantic_key}</p><span className="text-xs font-semibold uppercase">{conflict.status}</span></div><p className="mt-1 text-sm text-slate-600">{conflict.explanation}</p><ul className="mt-2 space-y-2 text-sm">{conflict.findings.map((finding) => <li key={finding.id}><p>Finding #{finding.id}: {finding.machine_value}</p><p className="text-xs text-slate-500">{finding.sources.map((source) => `Page ${source.page_number}${source.sheet_number ? ` · ${source.sheet_number}` : ""}`).join(", ")}</p></li>)}</ul>{conflict.status === "open" && canResolve && <div className="mt-3 flex flex-wrap gap-2"><input value={note} onChange={(event) => setNote(event.target.value)} maxLength={1000} placeholder="Resolution rationale" className="h-9 min-w-56 flex-1 rounded-lg border px-3 text-sm" /><button disabled={acting} onClick={() => onResolve(conflict, "resolved", note)} className="rounded-lg border px-3 text-xs font-semibold">Resolve</button><button disabled={acting} onClick={() => onResolve(conflict, "dismissed", note)} className="rounded-lg border px-3 text-xs font-semibold">Dismiss</button></div>}</div>;
}

function MachineResult({ run }: { run: AnalysisRun }) {
  const grouped = useMemo(() => { const value: Record<string, MachineCandidate[]> = {}; for (const candidate of run.result_summary.candidates ?? []) (value[candidate.category] ??= []).push(candidate); return value; }, [run]);
  return <div className="space-y-4"><Card className="p-5"><p className="text-xs font-semibold uppercase tracking-wider text-blue-700">Document Summary · Machine generated</p><h3 className="mt-2 font-semibold">{run.result_summary.document_type_candidate || "Document analysis"}</h3><p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-600">{run.result_summary.document_summary || "No summary was returned."}</p></Card>{Object.entries(grouped).map(([category, candidates]) => <Card key={category} className="p-5"><h3 className="font-semibold">{categoryLabels[category] ?? category}</h3><div className="mt-3 divide-y">{candidates.map((candidate, index) => <div key={`${candidate.subject}-${index}`} className="py-3 first:pt-0 last:pb-0"><div className="flex flex-wrap items-center gap-2"><p className="text-sm font-semibold">{candidate.subject}</p><span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-slate-600">{candidate.support.replace("_", " ")}</span></div><p className="mt-1 text-sm leading-6 text-slate-700">{candidate.value}</p><div className="mt-2 flex flex-wrap gap-2">{candidate.evidence.map((source, sourceIndex) => <span key={sourceIndex} className="rounded border bg-white px-2 py-1 text-xs text-slate-600">Page {source.page_number}{source.sheet_number ? ` · ${source.sheet_number}` : ""}{source.evidence_excerpt ? ` — ${source.evidence_excerpt}` : source.visual_evidence_description ? ` — ${source.visual_evidence_description}` : ""}</span>)}</div></div>)}</div></Card>)}{(run.result_summary.unresolved_questions?.length ?? 0) > 0 && <Card className="p-5"><h3 className="font-semibold">Open Questions</h3><ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-slate-700">{run.result_summary.unresolved_questions?.map((question) => <li key={question}>{question}</li>)}</ul></Card>}</div>;
}

function RunHistory({ runs, selectedRunId, onSelect }: { runs: AnalysisRun[]; selectedRunId: number | null; onSelect: (id: number) => void }) {
  return <Card className="overflow-hidden"><div className="border-b px-4 py-3"><h3 className="font-semibold">Analysis history</h3><p className="mt-1 text-xs text-slate-500">Every explicit analytical attempt is preserved. Select a successful run to review its persisted result.</p></div><div className="divide-y">{runs.map((run) => <button type="button" key={run.id} onClick={() => onSelect(run.id)} aria-pressed={selectedRunId === run.id} className={`grid w-full gap-2 px-4 py-3 text-left text-sm transition-colors sm:grid-cols-[1fr_auto] ${selectedRunId === run.id ? "bg-blue-50" : "hover:bg-slate-50"}`}><div><p className="font-semibold">Run #{run.id} · {run.status}</p><p className="mt-1 text-xs text-slate-500">Requested {new Date(run.created_at).toLocaleString("en-CA")} by {run.requested_by} · {run.provider}/{run.model}</p><p className="mt-1 text-xs text-slate-500">Prompt {run.prompt_version} · Schema {run.schema_version} · {run.task_counts.succeeded}/{run.task_counts.total} tasks succeeded</p></div><div className="text-xs text-slate-500 sm:text-right"><p>{run.usage_metadata.total_tokens?.toLocaleString() ?? "—"} tokens</p><p>{run.usage_metadata.vision_page_count ?? 0} vision pages</p></div></button>)}{!runs.length && <p className="px-4 py-6 text-center text-sm text-slate-500">No AI analysis has been requested for this revision.</p>}</div></Card>;
}

function stateLabel(state: ReturnType<typeof deriveAnalysisState>) { return ({ unsupported: "AI analysis not supported", source_required: "Source verification required", index_required: "PDF indexing required", ready: "Ready for AI analysis", queued: "AI analysis queued", running: "Analyzing document…", succeeded: "AI analysis complete", failed: "AI analysis failed" })[state]; }
function stateDetail(state: ReturnType<typeof deriveAnalysisState>, canOperate: boolean) { if (state === "unsupported") return "M1-09 supports PDF revisions only."; if (state === "source_required") return "Verify the immutable source in Documents first."; if (state === "index_required") return "Complete the durable Page / Sheet Index in Documents first."; if (state === "ready") return canOperate ? "Starting analysis is an explicit paid operation." : "An Admin or Estimator / Operator may start analysis."; if (state === "queued") return "Waiting for an AI processing worker."; if (state === "running") return "Page tasks and document synthesis are running with bounded concurrency."; if (state === "succeeded") return "Schema-validated machine output is persisted below."; return "Review the controlled failure and retry when eligible."; }
function StateIcon({ state }: { state: ReturnType<typeof deriveAnalysisState> }) { if (state === "succeeded") return <CheckCircle2 className="h-5 w-5 text-emerald-600" />; if (state === "queued" || state === "running") return <Clock3 className="h-5 w-5 text-blue-600" />; if (state === "failed") return <AlertCircle className="h-5 w-5 text-red-600" />; return <Bot className="h-5 w-5 text-slate-500" />; }
function ModuleState({ icon: Icon, title, detail, spin = false }: { icon: typeof FileSearch; title: string; detail?: string; spin?: boolean }) { return <section className="flex min-h-64 flex-col items-center justify-center rounded-xl border border-dashed px-6 text-center"><Icon className={`h-7 w-7 text-slate-400 ${spin ? "animate-spin" : ""}`} /><h2 className="mt-4 font-semibold">{title}</h2>{detail && <p className="mt-1 max-w-lg text-sm leading-6 text-slate-500">{detail}</p>}</section>; }
