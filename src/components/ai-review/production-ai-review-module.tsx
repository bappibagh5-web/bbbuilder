"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { AlertCircle, Bot, Check, CheckCircle2, ChevronDown, Clock3, ExternalLink, FileSearch, LoaderCircle, RotateCcw, ShieldCheck } from "lucide-react";
import type { OrganizationMembership } from "@/lib/auth";
import { analysisApi, type AnalysisRun, type ExtractedFinding, type FindingDecision, type FindingSource, type IntelligenceCandidateRun, type IntelligenceConflict, type IntelligenceReadiness, type IntelligenceSnapshot, type MachineCandidate, type ProjectReviewFilterKey, type ProjectReviewState } from "@/lib/analysis";
import { analysisActions, deriveAnalysisState, shouldPollAnalysis } from "@/lib/analysis-state";
import { canSubmitFindingReview, findingReviewActions } from "@/lib/finding-review-state";
import { selectedRunsRespectRevisionBoundary, snapshotActions } from "@/lib/intelligence-snapshot-state";
import { documentsApi, type ProcessingJob, type ProductionDocument, type ProductionDocumentRevision } from "@/lib/documents";
import { activeDocuments } from "@/lib/document-archive-state";
import { sourceDocumentTarget, sourcePdfViewerUrl, type DocumentSourceTarget } from "@/lib/document-source-navigation";
import { categoryLabel, decisionLabel, documentReviewScopeCopy, documentVersionLabel, emptyActiveDocumentReviewCopy, findingMatchesFilter, handlingLabel, plainAnalysisStatus, progressPresentation, projectFindingTrade, reviewCounts, reviewSectionVisibility, reviewStages, snapshotPresentation, versionDetailsButtonLabel, versionDetailsInitiallyExpanded, versionSummary, type SmartReviewFilter } from "@/lib/document-review-presentation";
import type { ProductionProject } from "@/lib/projects";
import { Card } from "@/components/ui/card";

type RevisionOption = { document: ProductionDocument; revision: ProductionDocumentRevision };

function formatBytes(value: number) {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

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
  const [projectSnapshots, setProjectSnapshots] = useState<IntelligenceSnapshot[]>([]);
  const [viewMode, setViewMode] = useState<"project" | "document">("project");
  const [projectReview, setProjectReview] = useState<ProjectReviewState | null>(null);
  const [projectReviewLoading, setProjectReviewLoading] = useState(true);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const polls = useRef(0);
  const projectReviewRequest = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    documentsApi.list(slug, project.id, controller.signal).then(async ({ results }) => {
      const revisionLists = await Promise.all(activeDocuments(results).map(async (document) => ({ document, revisions: (await documentsApi.revisions(slug, project.id, document.id, controller.signal)).results })));
      const next = revisionLists.flatMap(({ document, revisions }) => revisions.map((revision) => ({ document, revision })));
      setOptions(next); setSelectedId((current) => current ?? next[0]?.revision.id ?? null);
    }).catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Documents are unavailable."); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [project.id, slug]);

  const refreshProjectReview = useCallback(async (signal?: AbortSignal) => {
    const requestId = ++projectReviewRequest.current;
    const state = await analysisApi.projectReviewState(slug, project.id, signal);
    if (requestId !== projectReviewRequest.current) return state.current_run;
    setProjectReview(state);
    return state.current_run;
  }, [project.id, slug]);

  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;
    async function loadProjectReview() {
      try {
        const nextRun = await refreshProjectReview(controller.signal);
        if (nextRun?.status === "queued" || nextRun?.status === "running") {
          timer = window.setTimeout(() => void loadProjectReview(), 5_000);
        }
      } catch (reason) {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Project review is unavailable.");
      } finally {
        if (!controller.signal.aborted) setProjectReviewLoading(false);
      }
    }
    void loadProjectReview();
    return () => { controller.abort(); if (timer) window.clearTimeout(timer); };
  }, [refreshProjectReview]);

  const selected = options.find((item) => item.revision.id === selectedId) ?? null;
  const refresh = useCallback(async (signal?: AbortSignal) => {
    if (!selected) return;
    const [nextJobs, nextRuns, nextSnapshots] = await Promise.all([
      documentsApi.processingJobs(slug, project.id, selected.document.id, selected.revision.id, signal),
      analysisApi.list(slug, project.id, selected.document.id, selected.revision.id, signal),
      analysisApi.snapshots(slug, project.id, signal),
    ]);
    setJobs(nextJobs); setRuns(nextRuns); setProjectSnapshots(nextSnapshots);
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
  const counts = reviewCounts(findings);
  const openConflicts = conflicts.filter((item) => item.status === "open").length;
  const isCurrentRevision = selected?.document.current_revision?.id === selected?.revision.id;
  const pageCount = latestPdf?.result_metadata.page_count ?? 0;
  const approved = projectSnapshots.some((snapshot) => Boolean(snapshot.approval) && !snapshot.is_stale);
  const stages = reviewStages({
    uploaded: Boolean(selected), sourceStatus: latestSource?.status, pdfStatus: latestPdf?.status,
    pageCount, runStatus: latestRun?.status, findingCount: findings.length,
    needsAttention: counts.needsAttention + counts.conflicting, approved,
  });

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

  async function viewProjectSource(source: FindingSource) {
    const preview = window.open("about:blank", "_blank");
    if (preview) preview.opener = null;
    setError(null);
    try {
      const blob = await documentsApi.download(slug, project.id, source.document, source.document_revision);
      const url = URL.createObjectURL(blob);
      if (preview) preview.location.href = sourcePdfViewerUrl(url, source.page_number);
      else window.open(sourcePdfViewerUrl(url, source.page_number), "_blank", "noopener,noreferrer");
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (reason) {
      preview?.close();
      setError(reason instanceof Error ? reason.message : "We couldn't open this source page.");
    }
  }

  if ((viewMode === "project" && projectReviewLoading) || (viewMode === "document" && loading)) return <ModuleState icon={LoaderCircle} title="Opening document review…" detail="Loading your documents and saved review progress." spin />;
  if (viewMode === "project") return <ProjectReviewView project={project} slug={slug} canOperate={canOperate} review={projectReview} snapshots={projectSnapshots} acting={acting} setActing={setActing} setError={setError} refresh={refreshProjectReview} revisionOptions={options} onSnapshotsChange={setProjectSnapshots} onViewSource={(source) => void viewProjectSource(source)} onViewIndividual={() => setViewMode("document")} />;
  const sectionVisibility = reviewSectionVisibility(options.length);
  if (sectionVisibility.showActiveEmptyState) return <div className="space-y-5"><ModuleState icon={FileSearch} title={emptyActiveDocumentReviewCopy.title} detail={emptyActiveDocumentReviewCopy.detail} /><ProjectIntelligencePanel slug={slug} projectId={project.id} canOperate={canOperate} revisionOptions={[]} onSnapshotsChange={setProjectSnapshots} /></div>;
  if (!selected) return null;

  async function viewDocument(sourceTarget?: DocumentSourceTarget) {
    if (!selected) return;
    const preview = window.open("about:blank", "_blank");
    if (preview) preview.opener = null;
    setError(null);
    try {
      const documentId = sourceTarget?.documentId ?? selected.document.id;
      const revisionId = sourceTarget?.revisionId ?? selected.revision.id;
      const blob = await documentsApi.download(slug, project.id, documentId, revisionId);
      const url = URL.createObjectURL(blob);
      if (preview) preview.location.href = sourceTarget ? sourcePdfViewerUrl(url, sourceTarget.pageNumber) : url;
      else {
        const link = document.createElement("a");
        link.href = url;
        link.download = selected.revision.source_filename;
        link.click();
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (reason) {
      preview?.close();
      setError(reason instanceof Error ? reason.message : "We couldn't open this document. Try again, or contact support if the problem continues.");
    }
  }

  return <div className="space-y-5">
    <header className="rounded-xl border bg-gradient-to-br from-slate-50 to-white p-5 sm:p-6">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2"><h2 className="text-2xl font-semibold text-slate-950">Document Review</h2><span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700">AI-assisted</span></div>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">We&apos;ve reviewed your document with AI. Please check the findings below and confirm what&apos;s relevant to your project.</p><p className="mt-1 text-sm font-medium text-slate-700">{documentReviewScopeCopy.selectedDocument}</p>
          <div className="mt-5"><p className="text-lg font-semibold text-slate-900">{selected.document.title}</p><p className="mt-1 text-sm font-medium text-blue-700">{documentVersionLabel(Boolean(isCurrentRevision), selected.revision.revision_label, selected.revision.id)}</p><div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-500"><span>Uploaded {new Date(selected.revision.received_at).toLocaleString("en-CA")}</span><span>{pageCount || "—"} pages</span><span>{formatBytes(selected.revision.project_file.file_asset.byte_size)}</span></div></div>
        </div>
        <div className="flex flex-col gap-3 sm:min-w-80"><button type="button" onClick={() => setViewMode("project")} className="h-10 rounded-lg border border-blue-200 bg-blue-50 px-4 text-sm font-semibold text-blue-800">Back to Project Review</button><details className="rounded-lg border bg-white p-3"><summary className="cursor-pointer text-sm font-semibold text-slate-700">View individual document</summary><label className="mt-3 block text-xs font-semibold text-slate-700">Choose document version<select value={selectedId ?? ""} onChange={(event) => { setSelectedId(Number(event.target.value)); setJobs([]); setRuns([]); setSelectedRunId(null); setFindings([]); setConflicts([]); }} className="mt-1 h-10 w-full rounded-lg border bg-white px-3 text-sm font-normal">{options.map(({ document, revision }) => <option key={revision.id} value={revision.id}>{document.title} — {document.current_revision?.id === revision.id ? "Current" : "Older"} {revision.revision_label || `Version ${revision.id}`}</option>)}</select></label></details><button type="button" onClick={() => void viewDocument()} className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border bg-white px-4 text-sm font-semibold text-slate-700"><ExternalLink className="h-4 w-4" />View Document</button></div>
      </div>
    </header>
    <ProgressStepper stages={stages} />
    {!canOperate && <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">You can view this document review, but only an Admin or Estimator can make changes or approve project information.</div>}
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">AI helps find relevant information and shows where it came from. You decide what belongs in the project.</div>
    {error && <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800"><strong>We couldn&apos;t complete that action.</strong><span className="ml-1">{error} Try again, or contact support if the problem continues.</span></div>}
    <Card className="p-4 sm:p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><div className="flex items-center gap-2"><StateIcon state={state} /><h3 className="font-semibold">{plainAnalysisStatus(latestRun?.status)}</h3></div><p className="mt-1 text-sm text-slate-500">{stateDetail(state, canOperate, pageCount)}</p>{latestRun && (state === "queued" || state === "running") && <div className="mt-3" aria-live="polite"><p className="text-sm font-semibold text-blue-800">{latestRun.progress.completed} of {latestRun.progress.total} pages complete</p><div className="mt-2 h-2 w-full max-w-md overflow-hidden rounded-full bg-slate-200"><div className="h-full rounded-full bg-blue-600 transition-all" style={{ width: `${latestRun.progress.total ? (latestRun.progress.completed / latestRun.progress.total) * 100 : 0}%` }} /></div>{latestRun.progress.active > 0 && <p className="mt-1 text-xs text-slate-500">Reviewing {latestRun.progress.active} page{latestRun.progress.active === 1 ? "" : "s"} now.</p>}</div>}</div><div className="flex flex-wrap gap-2">{(actions.canRun || actions.canRunAgain) && <button type="button" disabled={acting} onClick={() => void act(() => analysisApi.request(slug, project.id, selected.document.id, selected.revision.id))} className="inline-flex h-10 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50"><Bot className="h-4 w-4" />{acting ? "Starting…" : actions.canRunAgain ? "Review Again with AI" : "Review with AI"}</button>}{actions.canRetry && latestRun && <button type="button" disabled={acting} onClick={() => void act(() => analysisApi.retry(slug, project.id, latestRun.id))} className="inline-flex h-10 items-center gap-2 rounded-lg border bg-white px-4 text-sm font-semibold disabled:opacity-50"><RotateCcw className="h-4 w-4" />{acting ? "Starting…" : "Try Again"}</button>}{actions.canCancel && latestRun && <button type="button" disabled={acting} onClick={() => void act(() => analysisApi.cancel(slug, project.id, latestRun.id))} className="inline-flex h-10 items-center gap-2 rounded-lg border border-red-200 bg-white px-4 text-sm font-semibold text-red-700 disabled:opacity-50">Cancel Review</button>}</div></div>{state === "failed" && <p className="mt-3 text-sm text-red-700">We couldn&apos;t finish reviewing this document. Try again, or contact support if the problem continues.</p>}{state === "cancelled" && <p className="mt-3 text-sm text-slate-600">This review was cancelled. Completed page results were preserved.</p>}</Card>
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_19rem]">
      <main className="min-w-0 space-y-5">{selectedRun?.status === "succeeded" && <HumanReviewPanel run={selectedRun} findings={findings} conflicts={conflicts} canOperate={canOperate} actions={reviewActions} slug={slug} projectId={project.id} acting={acting} setActing={setActing} setError={setError} refresh={refreshReview} onViewSource={(source) => void viewDocument(sourceDocumentTarget(selectedRun.document, source.document_revision, source.page_number))} />}
        <ProjectIntelligencePanel slug={slug} projectId={project.id} canOperate={canOperate} revisionOptions={options} onSnapshotsChange={setProjectSnapshots} />
      </main>
      <ReviewSidebar selected={selected} pageCount={pageCount} counts={counts} analysisStarted={Boolean(latestRun)} openConflicts={openConflicts} approved={approved} onViewDocument={() => void viewDocument()} />
    </div>
    <details className="rounded-xl border bg-white"><summary className="cursor-pointer px-5 py-4 text-sm font-semibold text-slate-700">Advanced details</summary><div className="space-y-4 border-t p-5">{selectedRun?.status === "succeeded" && <MachineResult run={selectedRun} />}<RunHistory runs={runs} selectedRunId={selectedRun?.id ?? null} onSelect={(id) => { setSelectedRunId(id); setFindings([]); setConflicts([]); }} /></div></details>
  </div>;
}

function ProjectReviewView({ project, slug, canOperate, review, snapshots, acting, setActing, setError, refresh, revisionOptions, onSnapshotsChange, onViewSource, onViewIndividual }: { project: ProductionProject; slug: string; canOperate: boolean; review: ProjectReviewState | null; snapshots: IntelligenceSnapshot[]; acting: boolean; setActing: (value: boolean) => void; setError: (value: string | null) => void; refresh: () => Promise<AnalysisRun | null>; revisionOptions: RevisionOption[]; onSnapshotsChange: (snapshots: IntelligenceSnapshot[]) => void; onViewSource: (source: FindingSource) => void; onViewIndividual: () => void }) {
  const run = review?.current_run ?? undefined;
  const counts = review?.counts;
  const openConflicts = review?.open_conflict_group_count ?? 0;
  const documentCount = run?.input_manifest.documents?.length ?? 0;
  const pageCount = run?.input_manifest.page_count ?? run?.progress.total ?? 0;
  const trades = Object.entries(review?.trade_counts ?? {});
  const approved = snapshots.some((snapshot) => Boolean(snapshot.approval) && !snapshot.is_stale);
  const nextAction = !run
    ? "Choose the estimating documents and start Project Review from the Documents tab."
    : run.status === "queued" || run.status === "running"
      ? `Project Review is working through ${run.progress.completed} of ${run.progress.total} pages.`
      : run.status === "failed"
        ? "The project review needs attention before it can continue."
        : !review?.materialized
          ? "Prepare the saved project findings for your review."
          : (counts?.needs_attention ?? 0) + (counts?.conflicting ?? 0) > 0
            ? `Review ${(counts?.needs_attention ?? 0) + (counts?.conflicting ?? 0)} item${(counts?.needs_attention ?? 0) + (counts?.conflicting ?? 0) === 1 ? "" : "s"} that need your attention.`
            : approved
              ? "Project information is approved and preserved in project history."
              : "Prepare the reviewed project information for final approval.";
  return <div className="space-y-5"><header className="rounded-xl border border-violet-200 bg-gradient-to-br from-violet-50 via-white to-blue-50 p-5 shadow-sm sm:p-6"><div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between"><div><div className="flex flex-wrap items-center gap-2"><h2 className="text-2xl font-semibold text-slate-950">Project Review</h2><span className="rounded-full bg-violet-100 px-2.5 py-1 text-xs font-semibold text-violet-800">AI-assisted</span></div><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">Review coordinated information across the estimating document set. Related requirements stay connected to their exact source pages.</p>{run && <p className="mt-3 text-sm font-semibold text-slate-800">{documentCount} documents · {pageCount} pages/slides reviewed</p>}</div><button type="button" onClick={onViewIndividual} className="h-10 rounded-lg border bg-white px-4 text-sm font-semibold text-slate-700 shadow-sm">View individual document</button></div></header>{!canOperate && <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">You can view Project Review, but only an Admin or Estimator can confirm items or prepare project information.</div>}<div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6"><SummaryMetric value={documentCount} label="Documents reviewed" tone="slate" /><SummaryMetric value={pageCount} label="Pages / slides" tone="slate" /><SummaryMetric value={counts?.total ?? 0} label="Project findings" tone="slate" /><SummaryMetric value={counts?.ai_handled ?? 0} label="AI handled" tone="emerald" /><SummaryMetric value={counts?.needs_attention ?? 0} label="Needs attention" tone={counts?.needs_attention ? "amber" : "slate"} /><ConflictSummaryMetric groups={openConflicts} items={counts?.conflicting ?? 0} /></div><Card className="p-5"><div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-wider text-blue-700">Next action</p><p className="mt-2 text-sm font-semibold text-slate-900">{nextAction}</p></div>{!run && <a href={`/projects/${project.id}/documents`} className="inline-flex h-10 items-center rounded-lg bg-primary px-4 text-sm font-semibold text-white">Open Documents</a>}</div>{trades.length > 0 && <div className="mt-4"><p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Trade coverage</p><div className="mt-2 flex flex-wrap gap-2">{trades.map(([trade, tradeCounts]) => <span key={trade} className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-800">{trade} · {tradeCounts.all}</span>)}</div></div>}</Card>{run?.status === "succeeded" && review && <LazyProjectReviewPanel run={run} review={review} canOperate={canOperate} slug={slug} projectId={project.id} acting={acting} setActing={setActing} setError={setError} refresh={refresh} onViewSource={onViewSource} />}<ProjectIntelligencePanel slug={slug} projectId={project.id} canOperate={canOperate} revisionOptions={revisionOptions} onSnapshotsChange={onSnapshotsChange} /><details className="rounded-xl border bg-white"><summary className="cursor-pointer px-5 py-4 text-sm font-semibold text-slate-700">Advanced project-review details</summary><div className="space-y-5 border-t p-5">{run ? <RunHistory runs={[run]} selectedRunId={run.id} onSelect={() => undefined} /> : <p className="text-sm text-slate-500">No project-wide review has been started.</p>}{run && <LazyConflictHistory slug={slug} projectId={project.id} runId={run.id} />}</div></details></div>;
}

function LazyConflictHistory({ slug, projectId, runId }: { slug: string; projectId: number; runId: number }) {
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [conflicts, setConflicts] = useState<IntelligenceConflict[]>([]);
  async function load() {
    setLoading(true);
    try {
      const next = await analysisApi.conflicts(slug, projectId);
      setConflicts(next.filter((conflict) => conflict.analysis_run === runId && conflict.status !== "open"));
      setLoaded(true);
    } finally {
      setLoading(false);
    }
  }
  if (!loaded) return <button type="button" disabled={loading} onClick={() => void load()} className="rounded-lg border bg-white px-3 py-2 text-xs font-semibold text-slate-700">{loading ? "Loading conflict history…" : "Load resolved and dismissed conflict history"}</button>;
  return <ConflictHistory conflicts={conflicts} />;
}

const projectFilterKeys: Record<SmartReviewFilter, ProjectReviewFilterKey> = {
  All: "all",
  "AI handled": "ai_handled",
  "Needs your attention": "needs_attention",
  Conflicts: "conflicts",
  "Reviewed by you": "reviewed_by_you",
};

type LazyFindingBatch = {
  items: ExtractedFinding[];
  total: number;
  page: number;
  loading: boolean;
  error: string | null;
};

function LazyProjectReviewPanel({ run, review, canOperate, slug, projectId, acting, setActing, setError, refresh, onViewSource }: { run: AnalysisRun; review: ProjectReviewState; canOperate: boolean; slug: string; projectId: number; acting: boolean; setActing: (value: boolean) => void; setError: (value: string | null) => void; refresh: () => Promise<AnalysisRun | null>; onViewSource: (source: FindingSource) => void }) {
  const [filter, setFilter] = useState<SmartReviewFilter>("All");
  const [expandedTrade, setExpandedTrade] = useState<string | null>(null);
  const [batches, setBatches] = useState<Record<string, LazyFindingBatch>>({});
  const [conflicts, setConflicts] = useState<IntelligenceConflict[]>([]);
  const actions = findingReviewActions(canOperate);
  const filters: SmartReviewFilter[] = ["All", "AI handled", "Needs your attention", "Conflicts", "Reviewed by you"];
  const filterKey = projectFilterKeys[filter];
  const trades = Object.entries(review.trade_counts).filter(([, counts]) => counts[filterKey] > 0);
  const cacheKey = (trade: string) => `${run.id}:${filterKey}:${trade}`;

  async function loadTrade(trade: string, page = 1, append = false) {
    const key = cacheKey(trade);
    setBatches((current) => ({ ...current, [key]: { items: append ? current[key]?.items ?? [] : [], total: current[key]?.total ?? 0, page, loading: true, error: null } }));
    try {
      const result = await analysisApi.projectReviewFindings(slug, projectId, { trade, filter: filterKey, page });
      setBatches((current) => ({ ...current, [key]: { items: append ? [...(current[key]?.items ?? []), ...result.results] : result.results, total: result.count, page: result.page, loading: false, error: null } }));
    } catch (reason) {
      setBatches((current) => ({ ...current, [key]: { items: current[key]?.items ?? [], total: current[key]?.total ?? 0, page, loading: false, error: reason instanceof Error ? reason.message : "These items could not be loaded." } }));
    }
  }

  async function perform(action: () => Promise<unknown>, trade?: string) {
    if (acting) return;
    setActing(true);
    setError(null);
    try {
      await action();
      await refresh();
      setBatches({});
      if (trade) await loadTrade(trade);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The review action failed.");
    } finally {
      setActing(false);
    }
  }

  async function toggleTrade(trade: string) {
    if (expandedTrade === trade) {
      setExpandedTrade(null);
      return;
    }
    setExpandedTrade(trade);
    const key = cacheKey(trade);
    if (!batches[key]) await loadTrade(trade);
    if (filter === "Conflicts" && conflicts.length === 0) {
      const next = await analysisApi.conflicts(slug, projectId);
      setConflicts(next.filter((conflict) => conflict.analysis_run === run.id && conflict.status === "open"));
    }
  }

  if (!review.materialized) return <Card className="border-blue-200 p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wider text-blue-700">Your Review</p><h3 className="mt-1 font-semibold">AI found items to prepare for your review</h3><p className="mt-1 text-sm text-slate-600">Prepare the saved results so you can confirm what is relevant. This does not run AI again or approve anything.</p></div>{actions.canMaterialize && <button type="button" disabled={acting} onClick={() => void perform(() => analysisApi.materialize(slug, projectId, run.id))} className="h-10 rounded-lg bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50">{acting ? "Preparing…" : "Prepare Items for Review"}</button>}</div></Card>;

  return <section className="space-y-4"><Card className="p-5"><p className="text-xs font-semibold uppercase tracking-wider text-blue-700">Your Review</p><h3 className="mt-2 text-xl font-semibold">AI found {review.counts.total} items across this project set.</h3><div className="mt-4 grid gap-3 sm:grid-cols-3"><SummaryMetric value={review.counts.ai_handled} label="AI handled" helper="Strongly grounded items that do not need your attention." tone="emerald" /><SummaryMetric value={review.counts.needs_attention} label="Needs your attention" helper="Items that need a decision or follow-up." tone={review.counts.needs_attention ? "amber" : "slate"} /><SummaryMetric value={review.counts.conflicting} label="Conflicting items" helper="Sources contain information that may disagree." tone={review.counts.conflicting ? "red" : "slate"} /></div>{review.counts.reviewed_by_human > 0 && <p className="mt-3 text-sm text-slate-600">Reviewed by you: <span className="font-semibold">{review.counts.reviewed_by_human}</span></p>}</Card><div className="flex gap-2 overflow-x-auto pb-1" aria-label="Finding review filters">{filters.map((item) => <button type="button" key={item} onClick={() => { setFilter(item); setExpandedTrade(null); }} className={`shrink-0 rounded-full border px-3 py-1.5 text-xs font-semibold ${filter === item ? "border-blue-700 bg-blue-700 text-white" : "bg-white text-slate-600"}`}>{item}</button>)}</div>{trades.length === 0 ? <Card className="p-5 text-sm text-slate-600">No items match this filter.</Card> : <div className="space-y-3">{trades.map(([trade, tradeCounts]) => { const key = cacheKey(trade); const batch = batches[key]; const expanded = expandedTrade === trade; return <section key={trade} className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"><button type="button" aria-expanded={expanded} onClick={() => void toggleTrade(trade)} className="flex w-full items-center justify-between gap-4 bg-slate-900 px-4 py-3 text-left text-white"><span className="font-semibold">{trade}</span><span className="flex items-center gap-3"><span className="rounded-full bg-white/10 px-2.5 py-1 text-xs font-semibold">{tradeCounts[filterKey]} items</span><ChevronDown className={`h-4 w-4 transition-transform ${expanded ? "rotate-180" : ""}`} /></span></button>{expanded && <div className="space-y-3 border-t bg-slate-50/60 p-3 sm:p-4">{batch?.loading && batch.items.length === 0 && <p className="py-6 text-center text-sm text-slate-500">Loading {trade} items…</p>}{batch?.error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{batch.error}</p>}{batch?.items.map((finding) => <FindingCard key={finding.id} finding={finding} canReview={actions.canReview} acting={acting} onViewSource={onViewSource} onReview={(decision, reviewedValue, reviewNote) => perform(() => analysisApi.review(slug, projectId, finding.id, { decision, reviewed_value: reviewedValue, review_note: reviewNote }), trade)} />)}{batch && batch.items.length < batch.total && <button type="button" disabled={batch.loading} onClick={() => void loadTrade(trade, batch.page + 1, true)} className="h-10 rounded-lg border bg-white px-4 text-sm font-semibold text-slate-700 disabled:opacity-50">{batch.loading ? "Loading…" : `Load more (${batch.total - batch.items.length} remaining)`}</button>}{filter === "Conflicts" && conflicts.length > 0 && <ConflictPanel conflicts={conflicts} canResolve={actions.canResolveConflict} acting={acting} onResolve={(conflict, status, note) => perform(() => analysisApi.resolveConflict(slug, projectId, conflict.id, { status, resolution_note: note }), trade)} />}</div>}</section>; })}</div>}</section>;
}

function ProgressStepper({ stages }: { stages: ReturnType<typeof reviewStages> }) {
  return <ol aria-label="Document review progress" className="grid gap-2 sm:grid-cols-5">{stages.map((stage, index) => <li key={stage.key} className={`rounded-xl border p-3 ${stage.state === "completed" ? "border-emerald-200 bg-emerald-50" : stage.state === "current" ? "border-blue-300 bg-blue-50 ring-1 ring-blue-200" : stage.state === "blocked" ? "border-red-200 bg-red-50" : "bg-slate-50 text-slate-500"}`}><div className="flex items-center gap-2"><span className={`grid h-6 w-6 shrink-0 place-items-center rounded-full text-xs font-bold ${stage.state === "completed" ? "bg-emerald-600 text-white" : stage.state === "current" ? "bg-blue-700 text-white" : stage.state === "blocked" ? "bg-red-600 text-white" : "bg-slate-200 text-slate-600"}`}>{stage.state === "completed" ? <Check className="h-3.5 w-3.5" /> : index + 1}</span><span className="text-sm font-semibold">{stage.label}</span></div><p className="mt-2 text-xs leading-5 opacity-80">{stage.detail}</p></li>)}</ol>;
}

function ReviewSidebar({ selected, pageCount, counts, analysisStarted, openConflicts, approved, onViewDocument }: { selected: RevisionOption; pageCount: number; counts: ReturnType<typeof reviewCounts>; analysisStarted: boolean; openConflicts: number; approved: boolean; onViewDocument: () => void }) {
  const progress = progressPresentation(analysisStarted, counts);
  return <aside className="space-y-4 xl:sticky xl:top-4 xl:self-start"><Card className="p-4"><p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Document</p><div className="mt-3 grid min-h-36 place-items-center rounded-lg bg-slate-100 text-center text-slate-500"><FileSearch className="h-8 w-8" /><div><p className="text-sm font-semibold text-slate-700">{pageCount || "—"} pages</p><p className="mt-1 text-xs">{selected.document.title}</p></div></div><button type="button" onClick={onViewDocument} className="mt-3 inline-flex h-9 w-full items-center justify-center gap-2 rounded-lg border text-sm font-semibold"><ExternalLink className="h-4 w-4" />Open Full Document</button></Card><Card className="p-4"><h3 className="font-semibold">Your Progress</h3><p className="mt-3 text-xl font-semibold text-slate-950">{progress.heading}</p><p className="mt-1 text-xs leading-5 text-slate-500">{progress.detail}</p>{analysisStarted && <dl className="mt-4 space-y-2 text-sm"><div className="flex justify-between"><dt>Confirmed</dt><dd className="font-semibold">{counts.confirmed}</dd></div><div className="flex justify-between"><dt>Not relevant</dt><dd className="font-semibold">{counts.notRelevant}</dd></div><div className="flex justify-between"><dt>Needs attention</dt><dd className="font-semibold">{counts.needsAttention}</dd></div><div className="flex justify-between"><dt>Conflicting</dt><dd className="font-semibold">{openConflicts}</dd></div></dl>}</Card><Card className="p-4"><h3 className="font-semibold">Next Steps</h3><p className="mt-2 text-sm leading-6 text-slate-600">{approved ? "Project information is approved and preserved in project history." : progress.nextStep}</p></Card><Card className="p-4"><h3 className="font-semibold">How this helps</h3><ul className="mt-3 space-y-2 text-sm text-slate-600"><li>✓ Finds important information quickly</li><li>✓ Shows exactly where it came from</li><li>✓ You stay in control</li><li>✓ Helps reduce missed details</li></ul></Card></aside>;
}

function HumanReviewPanel({ run, findings, conflicts, canOperate, actions, slug, projectId, acting, setActing, setError, refresh, onViewSource, groupByTrade = false, tradeForFinding = projectFindingTrade }: { run: AnalysisRun; findings: ExtractedFinding[]; conflicts: IntelligenceConflict[]; canOperate: boolean; actions: ReturnType<typeof findingReviewActions>; slug: string; projectId: number; acting: boolean; setActing: (value: boolean) => void; setError: (value: string | null) => void; refresh: () => Promise<void>; onViewSource: (source: FindingSource) => void; groupByTrade?: boolean; tradeForFinding?: (finding: ExtractedFinding) => string }) {
  const [filter, setFilter] = useState<SmartReviewFilter>("All");
  const [expandedTrade, setExpandedTrade] = useState<string | null>(null);
  const [focusedFindingId, setFocusedFindingId] = useState<number | null>(null);
  const progress = reviewCounts(findings);
  const currentConflicts = conflicts.filter((conflict) => conflict.status === "open");
  const filters: SmartReviewFilter[] = ["All", "AI handled", "Needs your attention", "Conflicts", "Reviewed by you"];
  const visible = findings.filter((finding) => findingMatchesFilter(finding, filter));
  const tradeGroups = Object.entries(visible.reduce<Record<string, ExtractedFinding[]>>((groups, finding) => {
    (groups[tradeForFinding(finding)] ??= []).push(finding);
    return groups;
  }, {})).sort(([left], [right]) => left.localeCompare(right));
  useEffect(() => {
    if (focusedFindingId === null) return;
    const timer = window.setTimeout(() => {
      document.getElementById(`project-finding-${focusedFindingId}`)?.focus();
      document.getElementById(`project-finding-${focusedFindingId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
      setFocusedFindingId(null);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [expandedTrade, filter, focusedFindingId]);
  function jumpToFinding(finding: ExtractedFinding) {
    setFilter("All");
    setExpandedTrade(tradeForFinding(finding));
    setFocusedFindingId(finding.id);
  }
  async function perform(action: () => Promise<unknown>) {
    if (acting) return;
    setActing(true); setError(null);
    try { await action(); await refresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The review action failed."); }
    finally { setActing(false); }
  }
  if (!findings.length) return <Card className="border-blue-200 p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wider text-blue-700">Your Review</p><h3 className="mt-1 font-semibold">AI found items to prepare for your review</h3><p className="mt-1 text-sm text-slate-600">Prepare the saved results so you can confirm what is relevant. This does not run AI again or approve anything.</p></div>{actions.canMaterialize && <button type="button" disabled={acting} onClick={() => void perform(() => analysisApi.materialize(slug, projectId, run.id))} className="h-10 rounded-lg bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50">{acting ? "Preparing…" : "Prepare Items for Review"}</button>}</div>{!canOperate && <p className="mt-3 text-sm text-slate-500">An Admin or Estimator can prepare these items.</p>}</Card>;
  const cards = (items: ExtractedFinding[]) => items.map((finding) => <div key={finding.id} id={`project-finding-${finding.id}`} tabIndex={-1} className="scroll-mt-6 rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"><FindingCard finding={finding} canReview={actions.canReview} acting={acting} onViewSource={onViewSource} onReview={(decision, reviewedValue, reviewNote) => perform(() => analysisApi.review(slug, projectId, finding.id, { decision, reviewed_value: reviewedValue, review_note: reviewNote }))} /></div>);
  const firstAttention = findings.find((finding) => ["needs_attention", "human_needs_follow_up", "conflicting"].includes(finding.handling_status));
  return <section className="space-y-4"><Card className="p-5"><p className="text-xs font-semibold uppercase tracking-wider text-blue-700">Your Review</p><h3 className="mt-2 text-xl font-semibold">AI found {progress.total} items {run.run_kind === "project_set" ? "across this project set" : "in this document"}.</h3><div className="mt-4 grid gap-3 sm:grid-cols-3"><SummaryMetric value={progress.aiHandled} label="AI handled" helper="Strongly grounded items that do not need your attention." tone="emerald" /><SummaryMetric value={progress.needsAttention} label="Needs your attention" helper="Items that need a decision or follow-up." tone={progress.needsAttention ? "amber" : "slate"} /><SummaryMetric value={progress.conflicting} label="Conflicting items" helper="Sources contain information that may disagree." tone={progress.conflicting ? "red" : "slate"} /></div>{progress.reviewedByHuman > 0 && <p className="mt-3 text-sm text-slate-600">Reviewed by you: <span className="font-semibold">{progress.reviewedByHuman}</span></p>}{progress.complete ? <div className="mt-4 rounded-lg bg-emerald-50 p-4 text-emerald-900"><p className="font-semibold">Review complete</p><p className="mt-1 text-sm">Straightforward items were handled by AI. Final project information still requires authorized human approval.</p></div> : <div className="mt-4 flex flex-wrap items-center justify-between gap-3"><p className="text-sm text-slate-600">Focus on the items needing your attention or conflict resolution. AI-handled items remain available for optional review.</p>{groupByTrade && firstAttention && <button type="button" onClick={() => jumpToFinding(firstAttention)} className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-900">Go to first item needing attention</button>}</div>}</Card><div className="flex gap-2 overflow-x-auto pb-1" aria-label="Finding review filters">{filters.map((item) => <button type="button" key={item} onClick={() => setFilter(item)} className={`shrink-0 rounded-full border px-3 py-1.5 text-xs font-semibold ${filter === item ? "border-blue-700 bg-blue-700 text-white" : "bg-white text-slate-600"}`}>{item}</button>)}</div>{groupByTrade ? <div className="space-y-3">{tradeGroups.map(([trade, items]) => <TradeFindingGroup key={trade} trade={trade} items={items ?? []} expanded={expandedTrade === trade} onToggle={() => setExpandedTrade((current) => current === trade ? null : trade)} renderCards={cards} />)}</div> : <div className="space-y-3">{cards(visible)}</div>}<ConflictPanel conflicts={currentConflicts} canResolve={actions.canResolveConflict} acting={acting} onViewFinding={groupByTrade ? jumpToFinding : undefined} onResolve={(conflict, status, note) => perform(() => analysisApi.resolveConflict(slug, projectId, conflict.id, { status, resolution_note: note }))} /></section>;
}

function TradeFindingGroup({ trade, items, expanded, onToggle, renderCards }: { trade: string; items: ExtractedFinding[]; expanded: boolean; onToggle: () => void; renderCards: (items: ExtractedFinding[]) => ReactNode }) {
  const panelId = `trade-findings-${trade.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  return <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"><button type="button" aria-expanded={expanded} aria-controls={panelId} onClick={onToggle} className="flex w-full items-center justify-between gap-4 bg-slate-900 px-4 py-3 text-left text-white transition-colors hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"><span className="font-semibold">{trade}</span><span className="flex shrink-0 items-center gap-3"><span className="rounded-full bg-white/10 px-2.5 py-1 text-xs font-semibold">{items.length} items</span><ChevronDown aria-hidden="true" className={`h-4 w-4 transition-transform ${expanded ? "rotate-180" : ""}`} /></span></button>{expanded && <div id={panelId} className="space-y-3 border-t border-slate-200 bg-slate-50/60 p-3 sm:p-4">{renderCards(items)}</div>}</section>;
}

function SummaryMetric({ value, label, helper, tone }: { value: number; label: string; helper?: string; tone: "emerald" | "amber" | "red" | "slate" }) {
  const tones = { emerald: "bg-emerald-50 text-emerald-900", amber: "bg-amber-50 text-amber-900", red: "bg-red-50 text-red-900", slate: "bg-slate-50 text-slate-800" };
  return <div className={`rounded-lg p-3 ${tones[tone]}`}><p className="text-2xl font-semibold">{value}</p><p className="mt-1 text-xs font-semibold">{label}</p>{helper && <p className="mt-1 text-xs leading-5 opacity-80">{helper}</p>}</div>;
}

function ConflictSummaryMetric({ groups, items }: { groups: number; items: number }) {
  const tone = groups ? "bg-red-50 text-red-900" : "bg-slate-50 text-slate-800";
  return <div className={`rounded-lg p-3 ${tone}`}><p className="text-lg font-semibold leading-7">{groups} conflict groups · {items} conflicting items</p><p className="mt-1 text-xs font-semibold">Conflicts</p></div>;
}

function ProjectIntelligencePanel({ slug, projectId, canOperate, onSnapshotsChange }: { slug: string; projectId: number; canOperate: boolean; revisionOptions: RevisionOption[]; onSnapshotsChange: (snapshots: IntelligenceSnapshot[]) => void }) {
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
    onSnapshotsChange(history);
  }, [onSnapshotsChange, projectId, slug]);
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
      await load(); setMessage("Project information version prepared for approval.");
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : "We couldn't prepare the project information. Try again."); }
    finally { setBusy(false); }
  }
  async function approve(snapshot: IntelligenceSnapshot) {
    if (!actions.canApprove(snapshot)) return;
    const count = snapshot.summary_counts.approved_entries ?? 0;
    if (!window.confirm(`Approve Project Information Version ${snapshot.version} with ${count} included items? Once approved, this version is preserved in project history. Future changes create a new version.`)) return;
    setBusy(true); setMessage(null);
    try {
      await analysisApi.approveSnapshot(slug, projectId, snapshot.id);
      await load(); setMessage(`Project Information Version ${snapshot.version} approved.`);
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : "We couldn't approve this version. Refresh its readiness and try again."); }
    finally { setBusy(false); }
  }
  const projectSetCandidates = candidates.filter((candidate) => candidate.run_kind === "project_set");
  const currentProjectReview = projectSetCandidates[0];
  const historicalCandidates = candidates.filter(
    (candidate) => candidate.id !== currentProjectReview?.id,
  );
  return <section className="space-y-4 border-t-4 border-slate-200 pt-5"><Card className="p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex flex-wrap items-center gap-2"><p className="text-xs font-semibold uppercase tracking-wider text-blue-700">{documentReviewScopeCopy.projectWideHeading}</p><span className="rounded-full bg-violet-50 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-violet-700">{documentReviewScopeCopy.projectWideBadge}</span></div><h3 className="mt-2 font-semibold">Project information for approval</h3><p className="mt-1 max-w-2xl text-sm text-slate-600">{documentReviewScopeCopy.projectWideExplanation}</p></div><div className="flex flex-wrap gap-2"><button type="button" disabled={busy} onClick={() => void load()} className="h-10 rounded-lg border px-3 text-sm font-semibold disabled:opacity-50">Refresh</button>{canOperate && <button type="button" disabled={busy || !actions.canCreate} onClick={() => void createSnapshot()} className="h-10 rounded-lg bg-primary px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40">Prepare Project Information for Approval</button>}</div></div>{message && <p className="mt-3 text-sm text-slate-700">{message}</p>}<div className="mt-5"><p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Current project-wide review</p>{currentProjectReview ? <div className="mt-2 rounded-xl border border-violet-200 bg-violet-50/60 p-4"><label className="flex items-start gap-3"><input type="checkbox" checked={selected.includes(currentProjectReview.id)} disabled={!canOperate} onChange={() => toggle(currentProjectReview)} className="mt-1" /><span className="min-w-0 flex-1"><span className="flex flex-wrap items-center justify-between gap-2"><span className="font-semibold text-slate-900">Project-wide review</span><span className="rounded-full bg-violet-100 px-2.5 py-1 text-xs font-semibold text-violet-800">{currentProjectReview.document_count} documents · {currentProjectReview.page_count} pages/slides</span></span><span className="mt-2 block text-sm text-slate-700">{currentProjectReview.finding_count} items · {currentProjectReview.unreviewed_count} still need review · {currentProjectReview.needs_clarification_count} need follow-up</span></span></label></div> : <p className="mt-2 text-sm text-slate-500">No completed project-wide review is ready yet.</p>}</div>{selected.length > 0 && readiness && <div className={`mt-4 rounded-lg border p-3 text-sm ${readiness.eligible ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-amber-200 bg-amber-50 text-amber-900"}`}><p className="font-semibold">{readiness.eligible ? "Project information is ready for approval" : "More review is needed"}</p>{readiness.blockers.map((blocker) => <p key={`${blocker.code}-${blocker.message}`} className="mt-1">{blocker.message}</p>)}</div>}{!canOperate && <p className="mt-3 text-sm text-slate-500">You can view this review, but only an Admin or Estimator can prepare or approve project information.</p>}<details className="mt-5 rounded-xl border bg-slate-50"><summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-slate-700">History · {historicalCandidates.length} earlier reviews · {snapshots.length} project information versions</summary><div className="space-y-4 border-t p-4">{historicalCandidates.length > 0 && <div className="space-y-2"><p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Earlier reviews</p>{historicalCandidates.map((candidate) => <label key={candidate.id} className="flex gap-3 rounded-lg border bg-white p-3 text-slate-600"><input type="checkbox" checked={selected.includes(candidate.id)} disabled={!canOperate || (candidate.run_kind === "document" && !candidate.is_current_revision)} onChange={() => toggle(candidate)} className="mt-1" /><span className="min-w-0"><span className="block text-sm font-semibold">{candidate.run_kind === "project_set" ? `Earlier project-wide review · ${candidate.document_count} documents · ${candidate.page_count} pages/slides` : `${candidate.document_title} · ${candidate.is_current_revision ? "Current" : "Older"} Version (${candidate.revision_label || candidate.document_revision_id})`}</span><span className="mt-1 block text-xs">{candidate.finding_count} items · {candidate.unreviewed_count} still need review · {candidate.needs_clarification_count} need follow-up</span></span></label>)}</div>}<SnapshotHistory snapshots={snapshots} canOperate={canOperate} busy={busy} onApprove={approve} /></div></details></Card></section>;
}

function SnapshotHistory({ snapshots, canOperate, busy, onApprove }: { snapshots: IntelligenceSnapshot[]; canOperate: boolean; busy: boolean; onApprove: (snapshot: IntelligenceSnapshot) => void }) {
  const actions = snapshotActions(canOperate, null);
  return <Card className="p-5"><h3 className="font-semibold">Project information versions</h3><p className="mt-1 text-sm text-slate-500">Each version preserves exactly what was reviewed. Later changes create a new version instead of changing an approved one.</p><div className="mt-4 space-y-4">{snapshots.map((snapshot) => <SnapshotVersionCard key={snapshot.id} snapshot={snapshot} canApprove={actions.canApprove(snapshot)} busy={busy} onApprove={onApprove} />)}{!snapshots.length && <p className="text-sm text-slate-500">No project information versions have been prepared.</p>}</div></Card>;
}

function SnapshotVersionCard({ snapshot: sourceSnapshot, canApprove, busy, onApprove }: { snapshot: IntelligenceSnapshot; canApprove: boolean; busy: boolean; onApprove: (snapshot: IntelligenceSnapshot) => void }) {
  const snapshot = { ...sourceSnapshot, approval_blockers: sourceSnapshot.approval_blockers ?? [] };
  const [expanded, setExpanded] = useState(versionDetailsInitiallyExpanded);
  const summary = versionSummary(snapshot);
  return <article className="rounded-lg border bg-white p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="font-semibold">Version {snapshot.version} · {snapshotPresentation(snapshot)}</p><p className="mt-2 text-sm text-slate-700">{summary.included} item{summary.included === 1 ? "" : "s"} included</p><p className="text-sm text-slate-700">{summary.notRelevant} item{summary.notRelevant === 1 ? "" : "s"} marked not relevant</p>{summary.sources.map((source) => <p key={source} className="mt-2 text-xs text-slate-500">Source: {source}</p>)}<p className="mt-1 text-xs text-slate-500">Prepared by {snapshot.created_by} · {new Date(snapshot.created_at).toLocaleString("en-CA")}</p></div><div className="flex flex-wrap gap-2"><button type="button" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)} className="h-9 rounded-lg border px-3 text-xs font-semibold">{versionDetailsButtonLabel(expanded)}</button>{canApprove && <button type="button" disabled={busy} onClick={() => void onApprove(snapshot)} className="h-9 rounded-lg bg-primary px-3 text-xs font-semibold text-white disabled:opacity-50">Approve Project Information</button>}</div></div>{snapshot.is_stale && <p className="mt-3 rounded bg-amber-50 p-2 text-sm text-amber-900">This version is based on earlier document or review information. Prepare a new version before approval. Any earlier approval remains preserved.</p>}{!snapshot.approval && snapshot.approval_blockers.map((blocker) => <p key={blocker.code} className="mt-3 rounded bg-amber-50 p-2 text-sm text-amber-900"><span className="font-semibold">Approval blocked.</span> {blocker.message} Restore the document or prepare a new project-information version.</p>)}{snapshot.approval && <div className="mt-3 rounded bg-emerald-50 p-3 text-sm text-emerald-900"><p className="flex items-center gap-2 font-semibold"><ShieldCheck className="h-4 w-4" />Project information approved</p><p className="mt-1">Approved by {snapshot.approval.approver} on {new Date(snapshot.approval.approved_at).toLocaleString("en-CA")}</p><p className="mt-1 text-xs">This approved version is preserved in project history.</p></div>}{expanded && <div className="mt-4 border-t pt-4">{snapshot.sources.map((source) => <div key={source.id} className="rounded-lg bg-slate-50 p-3"><p className="text-sm font-semibold">{source.document_title} · {source.revision_label || `Version ${source.document_revision}`} {!source.document_is_active && <span className="ml-2 rounded bg-slate-200 px-2 py-0.5 text-[10px] uppercase text-slate-700">Source document archived</span>}</p>{source.entries.map((entry) => <div key={entry.id} className="mt-2 border-t pt-2 text-sm"><p className="font-medium">{entry.subject} · {decisionLabel(entry.decision)}</p><p className="text-slate-700">{entry.included_in_intelligence ? entry.effective_value : "Marked not relevant — preserved in version history."}</p><p className="mt-1 text-xs text-slate-500">{entry.provenance.map((item) => `Page ${item.page_number}${item.sheet_number ? ` · ${item.sheet_number}` : ""}`).join(", ")}</p></div>)}</div>)}<details className="mt-3 rounded border bg-slate-50 p-3 text-xs text-slate-600"><summary className="cursor-pointer font-semibold">Advanced version details</summary><p className="mt-2 break-all">Fingerprint: {snapshot.fingerprint}</p><p className="mt-1">Internal version ID: {snapshot.id}</p></details></div>}</article>;
}

function FindingCard({ finding, canReview, acting, onReview, onViewSource }: { finding: ExtractedFinding; canReview: boolean; acting: boolean; onReview: (decision: FindingDecision, value: string, note: string) => void; onViewSource: (source: FindingSource) => void }) {
  const [editing, setEditing] = useState(false); const [value, setValue] = useState(finding.effective_value || finding.machine_value); const [note, setNote] = useState("");
  const currentReview = finding.reviews.at(-1);
  const canAccept = canSubmitFindingReview(canReview, currentReview, "accepted", "", note);
  const canReject = canSubmitFindingReview(canReview, currentReview, "rejected", "", note);
  const canClarify = canSubmitFindingReview(canReview, currentReview, "needs_clarification", "", note);
  const statusTone = finding.handling_status === "conflicting" ? "bg-red-50 text-red-900" : finding.handling_status === "needs_attention" || finding.handling_status === "human_needs_follow_up" ? "bg-amber-50 text-amber-900" : finding.handling_status === "human_rejected" ? "bg-slate-100 text-slate-700" : "bg-emerald-50 text-emerald-900";
  const needsAttention = finding.handling_status === "needs_attention" || finding.handling_status === "human_needs_follow_up" || finding.handling_status === "conflicting";
  return <Card className={`p-5 ${needsAttention ? "border-amber-200" : finding.handling_status === "ai_handled" ? "border-slate-200 bg-slate-50/40" : ""}`}><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wider text-blue-700">{categoryLabel(finding.category)}</p><h3 className="mt-1 text-lg font-semibold text-slate-950">{finding.subject}</h3></div><span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${statusTone}`}>{handlingLabel(finding.handling_status)}</span></div>{finding.handling_status === "ai_handled" && <p className="mt-3 text-xs text-slate-600">Strong source evidence lets AI handle this item. You can still review or override it.</p>}<div className="mt-4"><p className="text-xs font-semibold uppercase tracking-wider text-slate-500">AI found</p><p className="mt-1 text-sm leading-6 text-slate-700">“{finding.machine_value}”</p></div><div className="mt-4 rounded-lg bg-slate-50 p-3"><p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Where this came from</p>{finding.sources.map((source) => <div key={source.id} className="mt-2 text-sm"><p className="font-medium text-slate-900">{source.document_title}</p><p className="mt-0.5 text-slate-600">{source.revision_label || `Version ${source.document_revision}`} · Page {source.page_number}{source.sheet_number ? ` · ${source.sheet_number}${source.sheet_title ? ` ${source.sheet_title}` : ""}` : ""}</p><p className="mt-2 border-l-2 border-slate-300 pl-3 text-slate-600">{source.evidence_excerpt ? `“${source.evidence_excerpt}”` : `Visual evidence: ${source.visual_evidence_description}`}</p><button type="button" onClick={() => onViewSource(source)} className="mt-2 inline-flex items-center gap-1.5 text-xs font-semibold text-blue-700"><ExternalLink className="h-3.5 w-3.5" />View source · Page {source.page_number}</button></div>)}</div>{currentReview && <div className={`mt-4 rounded-lg p-3 text-sm ${finding.review_status === "rejected" ? "bg-slate-50" : "bg-emerald-50"}`}><p className="font-semibold">{decisionLabel(finding.review_status)}</p>{finding.effective_value && finding.effective_value !== finding.machine_value && <p className="mt-1">Confirmed value: {finding.effective_value}</p>}<p className="mt-1 text-xs text-slate-600">{finding.review_status === "rejected" ? "Marked not relevant" : "Reviewed"} by {currentReview.reviewer} · {new Date(currentReview.created_at).toLocaleString("en-CA")}</p>{currentReview.review_note && <p className="mt-1 text-xs text-slate-600">{currentReview.review_note}</p>}</div>}{canReview && <div className="mt-4 space-y-2">{editing && <textarea value={value} onChange={(event) => setValue(event.target.value)} maxLength={2000} className="min-h-20 w-full rounded-lg border p-2 text-sm" aria-label="Confirmed value" />}<input value={note} onChange={(event) => setNote(event.target.value)} maxLength={1000} placeholder="Add a note (optional)" className="h-10 w-full rounded-lg border px-3 text-sm" /><div className="flex flex-wrap gap-2"><button disabled={acting || !canAccept} onClick={() => onReview("accepted", "", note)} className="rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500">Confirm</button><button disabled={acting} onClick={() => editing ? onReview("edited_accepted", value, note) : setEditing(true)} className="rounded-lg border px-3 py-2 text-xs font-semibold disabled:opacity-50">{editing ? "Save & Confirm" : "Edit & Confirm"}</button><button disabled={acting || !canReject} onClick={() => onReview("rejected", "", note)} className="rounded-lg border px-3 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400">Not relevant</button><button disabled={acting || !canClarify} onClick={() => onReview("needs_clarification", "", note)} className="rounded-lg border px-3 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400">Needs follow-up</button></div></div>}<details className="mt-4 text-xs text-slate-500"><summary className="cursor-pointer font-semibold">Item history</summary><p className="mt-2">{finding.reviews.length} human decision{finding.reviews.length === 1 ? "" : "s"} preserved · Internal item #{finding.id}</p></details></Card>;
}

function ConflictPanel({ conflicts, canResolve, acting, onResolve, onViewFinding }: { conflicts: IntelligenceConflict[]; canResolve: boolean; acting: boolean; onResolve: (conflict: IntelligenceConflict, status: "resolved" | "dismissed", note: string) => void; onViewFinding?: (finding: ExtractedFinding) => void }) {
  if (!conflicts.length) return <Card className="p-5"><h3 className="font-semibold">Conflicting information</h3><p className="mt-1 text-sm text-slate-500">No conflicts need review.</p></Card>;
  return <Card className="p-5"><h3 className="font-semibold">Conflicting information</h3><p className="mt-1 text-sm text-slate-600">The system found reviewed items that may disagree. Please check them before approval.</p><div className="mt-3 space-y-4">{conflicts.map((conflict) => <ConflictItem key={conflict.id} conflict={conflict} canResolve={canResolve} acting={acting} onResolve={onResolve} onViewFinding={onViewFinding} />)}</div></Card>;
}

function ConflictHistory({ conflicts }: { conflicts: IntelligenceConflict[] }) {
  if (!conflicts.length) return null;
  return <details className="rounded-lg border bg-slate-50"><summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-slate-700">Resolved and dismissed conflict history · {conflicts.length}</summary><div className="space-y-3 border-t p-4">{conflicts.map((conflict) => <ConflictItem key={conflict.id} conflict={conflict} canResolve={false} acting={false} onResolve={() => undefined} />)}</div></details>;
}

function ConflictItem({ conflict, canResolve, acting, onResolve, onViewFinding }: { conflict: IntelligenceConflict; canResolve: boolean; acting: boolean; onResolve: (conflict: IntelligenceConflict, status: "resolved" | "dismissed", note: string) => void; onViewFinding?: (finding: ExtractedFinding) => void }) {
  const [note, setNote] = useState("");
  return <div className="rounded-lg border p-3"><div className="flex justify-between gap-2"><p className="text-sm font-semibold">Information needs comparison</p><span className="text-xs font-semibold uppercase">{conflict.status === "open" ? "Needs review" : conflict.status}</span></div><p className="mt-1 text-sm text-slate-600">{conflict.explanation}</p><ul className="mt-2 space-y-2 text-sm">{conflict.findings.map((finding) => <li key={finding.id}><p>{finding.subject}: {finding.machine_value}</p><p className="text-xs text-slate-500">{finding.sources.map((source) => `Page ${source.page_number}${source.sheet_number ? ` · ${source.sheet_number}` : ""}`).join(", ")}</p>{onViewFinding && <button type="button" onClick={() => onViewFinding(finding)} className="mt-1 text-xs font-semibold text-blue-700">View this item</button>}</li>)}</ul>{conflict.status === "open" && canResolve && <div className="mt-3 flex flex-wrap gap-2"><input value={note} onChange={(event) => setNote(event.target.value)} maxLength={1000} placeholder="Why this was resolved" className="h-9 min-w-56 flex-1 rounded-lg border px-3 text-sm" /><button disabled={acting} onClick={() => onResolve(conflict, "resolved", note)} className="rounded-lg border px-3 py-2 text-xs font-semibold">Mark resolved</button><button disabled={acting} onClick={() => onResolve(conflict, "dismissed", note)} className="rounded-lg border px-3 py-2 text-xs font-semibold">Not a conflict</button></div>}</div>;
}

function MachineResult({ run }: { run: AnalysisRun }) {
  const grouped = useMemo(() => { const value: Record<string, MachineCandidate[]> = {}; for (const candidate of run.result_summary.candidates ?? []) (value[candidate.category] ??= []).push(candidate); return value; }, [run]);
  return <div className="space-y-4"><Card className="p-5"><p className="text-xs font-semibold uppercase tracking-wider text-blue-700">AI document summary</p><h3 className="mt-2 font-semibold">{run.result_summary.document_type_candidate || "Document review"}</h3><p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-600">{run.result_summary.document_summary || "No summary was returned."}</p></Card>{Object.entries(grouped).map(([category, candidates]) => <Card key={category} className="p-5"><h3 className="font-semibold">{categoryLabel(category)}</h3><div className="mt-3 divide-y">{candidates.map((candidate, index) => <div key={`${candidate.subject}-${index}`} className="py-3 first:pt-0 last:pb-0"><div className="flex flex-wrap items-center gap-2"><p className="text-sm font-semibold">{candidate.subject}</p><span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-slate-600">{candidate.support.replace("_", " ")}</span></div><p className="mt-1 text-sm leading-6 text-slate-700">{candidate.value}</p><div className="mt-2 flex flex-wrap gap-2">{candidate.evidence.map((source, sourceIndex) => <span key={sourceIndex} className="rounded border bg-white px-2 py-1 text-xs text-slate-600">Page {source.page_number}{source.sheet_number ? ` · ${source.sheet_number}` : ""}{source.evidence_excerpt ? ` — ${source.evidence_excerpt}` : source.visual_evidence_description ? ` — ${source.visual_evidence_description}` : ""}</span>)}</div></div>)}</div></Card>)}{(run.result_summary.unresolved_questions?.length ?? 0) > 0 && <Card className="p-5"><h3 className="font-semibold">Questions to Follow Up</h3><ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-slate-700">{run.result_summary.unresolved_questions?.map((question) => <li key={question}>{question}</li>)}</ul></Card>}</div>;
}

function RunHistory({ runs, selectedRunId, onSelect }: { runs: AnalysisRun[]; selectedRunId: number | null; onSelect: (id: number) => void }) {
  return <Card className="overflow-hidden"><div className="border-b px-4 py-3"><h3 className="font-semibold">Previous AI reviews</h3><p className="mt-1 text-xs text-slate-500">Technical review history is preserved for support and audit purposes.</p></div><div className="divide-y">{runs.map((run) => <button type="button" key={run.id} onClick={() => onSelect(run.id)} aria-pressed={selectedRunId === run.id} className={`grid w-full gap-2 px-4 py-3 text-left text-sm transition-colors sm:grid-cols-[1fr_auto] ${selectedRunId === run.id ? "bg-blue-50" : "hover:bg-slate-50"}`}><div><p className="font-semibold">AI review #{run.id} · {plainAnalysisStatus(run.status)}</p><p className="mt-1 text-xs text-slate-500">Requested {new Date(run.created_at).toLocaleString("en-CA")} by {run.requested_by} · {run.provider}/{run.model}</p><p className="mt-1 text-xs text-slate-500">Prompt {run.prompt_version} · Schema {run.schema_version} · {run.task_counts.succeeded}/{run.task_counts.total} technical tasks succeeded</p></div><div className="text-xs text-slate-500 sm:text-right"><p>{run.usage_metadata.total_tokens?.toLocaleString() ?? "—"} tokens</p><p>{run.usage_metadata.vision_page_count ?? 0} vision pages</p></div></button>)}{!runs.length && <p className="px-4 py-6 text-center text-sm text-slate-500">No previous AI reviews are available for this version.</p>}</div></Card>;
}

function stateDetail(state: ReturnType<typeof deriveAnalysisState>, canOperate: boolean, pageCount: number) { if (state === "unsupported") return "This file type can be stored safely, but document review currently supports PDFs."; if (state === "source_required") return "Checking file. This confirms the uploaded document is available and intact."; if (state === "index_required") return "Reading and organizing pages. Return shortly to continue."; if (state === "ready") return canOperate ? `${pageCount} pages are prepared and ready for an explicit AI-assisted review.` : "An Admin or Estimator can start the AI-assisted review."; if (state === "queued") return `Preparing to review ${pageCount || "the document's"} pages.`; if (state === "running") return `Reviewing ${pageCount || "the document's"} pages for project requirements, responsibilities, dates and questions.`; if (state === "succeeded") return "AI found relevant information below. Please confirm what applies to your project."; if (state === "cancelled") return "The review stopped safely; completed page results remain available for a future retry."; return "Try again, or contact support if the problem continues."; }
function StateIcon({ state }: { state: ReturnType<typeof deriveAnalysisState> }) { if (state === "succeeded") return <CheckCircle2 className="h-5 w-5 text-emerald-600" />; if (state === "queued" || state === "running") return <Clock3 className="h-5 w-5 text-blue-600" />; if (state === "failed") return <AlertCircle className="h-5 w-5 text-red-600" />; return <Bot className="h-5 w-5 text-slate-500" />; }
function ModuleState({ icon: Icon, title, detail, spin = false }: { icon: typeof FileSearch; title: string; detail?: string; spin?: boolean }) { return <section className="flex min-h-64 flex-col items-center justify-center rounded-xl border border-dashed px-6 text-center"><Icon className={`h-7 w-7 text-slate-400 ${spin ? "animate-spin" : ""}`} /><h2 className="mt-4 font-semibold">{title}</h2>{detail && <p className="mt-1 max-w-lg text-sm leading-6 text-slate-500">{detail}</p>}</section>; }
