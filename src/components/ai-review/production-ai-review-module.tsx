"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, Bot, CheckCircle2, Clock3, FileSearch, LoaderCircle, RotateCcw } from "lucide-react";
import type { OrganizationMembership } from "@/lib/auth";
import { analysisApi, type AnalysisRun, type MachineCandidate } from "@/lib/analysis";
import { analysisActions, deriveAnalysisState, MACHINE_REVIEW_WARNING, shouldPollAnalysis } from "@/lib/analysis-state";
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
      <label className="block min-w-0 text-xs font-semibold sm:w-96">Document revision<select value={selectedId ?? ""} onChange={(event) => { setSelectedId(Number(event.target.value)); setJobs([]); setRuns([]); setSelectedRunId(null); }} className="mt-1 h-10 w-full rounded-lg border bg-white px-3 text-sm font-normal">{options.map(({ document, revision }) => <option key={revision.id} value={revision.id}>{document.title} — {revision.revision_label || `Revision #${revision.id}`}</option>)}</select></label>
    </section>
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm font-medium text-amber-900">{MACHINE_REVIEW_WARNING} Results are candidates, not approved project intelligence.</div>
    {error && <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</div>}
    <Card className="p-4 sm:p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><div className="flex items-center gap-2"><StateIcon state={state} /><h3 className="font-semibold">{stateLabel(state)}</h3></div><p className="mt-1 text-sm text-slate-500">{stateDetail(state, canOperate)}</p></div><div className="flex gap-2">{(actions.canRun || actions.canRunAgain) && selected && <button type="button" disabled={acting} onClick={() => void act(() => analysisApi.request(slug, project.id, selected.document.id, selected.revision.id))} className="inline-flex h-10 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50"><Bot className="h-4 w-4" />{acting ? "Requesting…" : actions.canRunAgain ? "Run AI Analysis Again" : "Run AI Analysis"}</button>}{actions.canRetry && latestRun && <button type="button" disabled={acting} onClick={() => void act(() => analysisApi.retry(slug, project.id, latestRun.id))} className="inline-flex h-10 items-center gap-2 rounded-lg border bg-white px-4 text-sm font-semibold disabled:opacity-50"><RotateCcw className="h-4 w-4" />{acting ? "Requesting…" : "Retry Analysis"}</button>}</div></div>{state === "failed" && latestRun?.safe_failure_message && <p className="mt-3 text-sm text-red-700">{latestRun.safe_failure_message}</p>}</Card>
    {selectedRun?.status === "succeeded" && <MachineResult run={selectedRun} />}
    <RunHistory runs={runs} selectedRunId={selectedRun?.id ?? null} onSelect={setSelectedRunId} />
  </div>;
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
