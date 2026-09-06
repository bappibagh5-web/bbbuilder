"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  Bot,
  Building2,
  CheckCircle2,
  ClipboardCheck,
  FileCheck2,
  FolderKanban,
  MapPin,
  RefreshCw,
  ShieldCheck,
  UserCheck,
} from "lucide-react";
import { useOrganization } from "@/components/organizations/organization-provider";
import { OrganizationAccessState } from "@/components/organizations/organization-access-state";
import { Card } from "@/components/ui/card";
import { analysisApi, type IntelligenceSnapshot } from "@/lib/analysis";
import { ApiError } from "@/lib/api-client";
import { dashboardActivityLabel, dashboardReviewCounts, projectNeedsAttention, type DashboardReviewCounts } from "@/lib/dashboard-state";
import { documentsApi } from "@/lib/documents";
import { projectsApi, type ProductionProject, type ProjectAuditEvent } from "@/lib/projects";

type ProjectOverview = {
  project: ProductionProject;
  activeDocuments: number;
  reviewedDocuments: number;
  review: DashboardReviewCounts;
  approvedSnapshot: IntelligenceSnapshot | null;
  approvedSnapshotCount: number;
  needsAttention: boolean;
};

type ActivityItem = ProjectAuditEvent & { projectId: number; projectName: string };
type DashboardData = { projects: ProjectOverview[]; activity: ActivityItem[] };

export function ProductionDashboard() {
  const { memberships, activeMembership } = useOrganization();
  if (!activeMembership) return <OrganizationAccessState multiple={memberships.length > 1} />;
  return <OrganizationDashboard key={activeMembership.organization.slug} slug={activeMembership.organization.slug} organizationName={activeMembership.organization.name} />;
}

function OrganizationDashboard({ slug, organizationName }: { slug: string; organizationName: string }) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    loadDashboard(slug, controller.signal)
      .then(setData)
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof ApiError && reason.status === 403
          ? "You no longer have access to this organization."
          : reason instanceof Error ? reason.message : "Dashboard data could not be loaded.");
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [slug, reload]);

  if (loading && !data) return <DashboardState title="Loading your preconstruction dashboard…" />;
  if (error && !data) return <DashboardState title="Dashboard unavailable" message={error} retry={() => setReload((value) => value + 1)} />;

  const projects = data?.projects ?? [];
  const activeCount = projects.length;
  const attentionCount = projects.filter((project) => project.needsAttention).length;
  const completedReviews = projects.reduce((total, project) => total + project.reviewedDocuments, 0);
  const approvedVersions = projects.reduce((total, project) => total + project.approvedSnapshotCount, 0);
  const refresh = () => {
    setLoading(true);
    setError(null);
    setReload((value) => value + 1);
  };

  return (
    <div className="mx-auto max-w-[1500px] space-y-6">
      <header className="overflow-hidden rounded-2xl bg-[#102a43] px-6 py-7 text-white shadow-[0_14px_35px_rgba(15,42,67,.18)] sm:px-8">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <span className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-blue-100"><ShieldCheck className="h-3.5 w-3.5" />Production data</span>
            <h1 className="mt-4 text-2xl font-semibold tracking-tight sm:text-3xl">Preconstruction Dashboard</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">A live view of project intake, document review, approved information, and work that needs attention for {organizationName}.</p>
          </div>
          <button type="button" onClick={refresh} disabled={loading} className="inline-flex h-10 items-center justify-center gap-2 self-start rounded-lg border border-white/20 bg-white/10 px-4 text-sm font-semibold hover:bg-white/15 disabled:opacity-50"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />Refresh</button>
        </div>
      </header>

      {error && <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">Showing the last loaded dashboard. Refresh failed: {error}</div>}

      <section aria-label="Production overview" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="Active projects" value={activeCount} detail="Persistent production projects" icon={<Building2 />} tone="blue" />
        <KpiCard label="Needs attention" value={attentionCount} detail={attentionCount ? "Review exceptions or incomplete documents" : "No unresolved review exceptions"} icon={<AlertTriangle />} tone={attentionCount ? "amber" : "green"} />
        <KpiCard label="Document reviews complete" value={completedReviews} detail="Current active documents" icon={<FileCheck2 />} tone="indigo" />
        <KpiCard label="Approved information" value={approvedVersions} detail="Projects with an approved version" icon={<BadgeCheck />} tone="green" />
      </section>

      <section aria-labelledby="active-projects-heading">
        <div className="mb-3 flex items-end justify-between gap-4">
          <div><h2 id="active-projects-heading" className="text-lg font-semibold text-slate-900">Active Projects</h2><p className="mt-1 text-sm text-slate-500">Current project stage and document-review readiness.</p></div>
          <Link href="/projects" className="hidden items-center gap-1 text-sm font-semibold text-blue-700 hover:underline sm:inline-flex">View all projects<ArrowRight className="h-4 w-4" /></Link>
        </div>
        {projects.length ? <div className="grid gap-5">{projects.map((overview) => <ProjectCard key={overview.project.id} overview={overview} />)}</div> : <Card className="border-dashed p-10 text-center"><FolderKanban className="mx-auto h-9 w-9 text-slate-300" /><h3 className="mt-3 font-semibold text-slate-800">No active projects</h3><p className="mt-1 text-sm text-slate-500">Active production projects will appear here.</p></Card>}
      </section>

      <section className="grid gap-6 xl:grid-cols-[.85fr_1.15fr]">
        <AttentionCard projects={projects.filter((project) => project.needsAttention)} />
        <ActivityCard events={data?.activity ?? []} />
      </section>
    </div>
  );
}

function KpiCard({ label, value, detail, icon, tone }: { label: string; value: number; detail: string; icon: ReactNode; tone: "blue" | "green" | "amber" | "indigo" }) {
  const styles = {
    blue: "border-t-blue-500 bg-blue-50/35 text-blue-700",
    green: "border-t-emerald-500 bg-emerald-50/35 text-emerald-700",
    amber: "border-t-amber-500 bg-amber-50/40 text-amber-700",
    indigo: "border-t-indigo-500 bg-indigo-50/35 text-indigo-700",
  }[tone];
  return <Card className={`border-t-4 p-5 shadow-[0_8px_24px_rgba(15,23,42,.06)] ${styles}`}><div className="flex items-start justify-between"><div><p className="text-xs font-semibold uppercase tracking-[.12em] text-slate-500">{label}</p><p className="mt-2 text-3xl font-semibold tabular-nums text-slate-950">{value}</p></div><span className="grid h-10 w-10 place-items-center rounded-xl bg-white shadow-sm [&_svg]:h-5 [&_svg]:w-5">{icon}</span></div><p className="mt-3 text-xs leading-5 text-slate-500">{detail}</p></Card>;
}

function ProjectCard({ overview }: { overview: ProjectOverview }) {
  const { project, review, approvedSnapshot } = overview;
  const location = [project.city, project.province_state].filter(Boolean).join(", ") || "Location not set";
  const progress = projectProgress(overview);
  return <Card className="overflow-hidden shadow-[0_10px_28px_rgba(15,23,42,.07)]">
    <div className="grid lg:grid-cols-[1.3fr_.7fr]">
      <div className="p-5 sm:p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div><div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-blue-100 px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide text-blue-700">{project.status_label}</span>{overview.activeDocuments > 0 && overview.reviewedDocuments === overview.activeDocuments && <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide text-emerald-700"><CheckCircle2 className="h-3 w-3" />Document review complete</span>}</div><h3 className="mt-3 text-xl font-semibold text-slate-950">{project.name}</h3><p className="mt-1 text-sm text-slate-500">{project.project_number} <span className="px-1 text-slate-300">·</span> <span className="inline-flex items-center gap-1"><MapPin className="h-3.5 w-3.5" />{location}</span></p></div>
          <Link href={`/projects/${project.id}`} className="inline-flex h-10 items-center justify-center gap-2 self-start rounded-lg bg-[#173f5f] px-4 text-sm font-semibold text-white hover:bg-[#102f49]">Open Project<ArrowRight className="h-4 w-4" /></Link>
        </div>
        <div className="mt-6"><div className="mb-2 flex items-center justify-between text-xs"><span className="font-semibold text-slate-700">Milestone 1 progress</span><span className="font-bold text-blue-700">{progress}%</span></div><div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-blue-600 transition-all" style={{ width: `${progress}%` }} /></div><div className="mt-2 grid grid-cols-5 text-[10px] font-medium text-slate-400"><span>Intake</span><span className="text-center">Documents</span><span className="text-center">AI Review</span><span className="text-center">Human Review</span><span className="text-right">Approved</span></div></div>
        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4"><MiniMetric icon={<ClipboardCheck />} value={review.total} label="Findings" tone="blue" /><MiniMetric icon={<Bot />} value={review.aiHandled} label="AI handled" tone="purple" /><MiniMetric icon={<UserCheck />} value={review.reviewedByUser} label="Reviewed by user" tone="sky" /><MiniMetric icon={<AlertTriangle />} value={review.needsAttention + review.conflicts} label="Needs attention" tone="amber" /></div>
      </div>
      <div className="border-t bg-slate-50/80 p-5 sm:p-6 lg:border-l lg:border-t-0">
        <p className="text-xs font-semibold uppercase tracking-[.12em] text-slate-500">Project information</p>
        {approvedSnapshot ? <div className="mt-4 rounded-xl border border-emerald-200 bg-white p-4 shadow-sm"><div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-100 text-emerald-700"><BadgeCheck className="h-5 w-5" /></span><div><p className="font-semibold text-slate-900">Version {approvedSnapshot.version} approved</p><p className="text-xs text-slate-500">Final human approval recorded</p></div></div><dl className="mt-4 space-y-2 border-t pt-3 text-xs"><div className="flex justify-between gap-3"><dt className="text-slate-500">Approved by</dt><dd className="text-right font-medium text-slate-700">{approvedSnapshot.approval?.approver}</dd></div><div className="flex justify-between gap-3"><dt className="text-slate-500">Approved</dt><dd className="text-right font-medium text-slate-700">{formatDashboardDate(approvedSnapshot.approval?.approved_at)}</dd></div></dl></div> : <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4"><p className="font-semibold text-amber-900">Approval not yet recorded</p><p className="mt-1 text-xs leading-5 text-amber-800">Complete current document review and prepare project information for approval.</p></div>}
        <div className="mt-4 rounded-xl border bg-white p-4"><div className="flex justify-between text-xs"><span className="text-slate-500">Document coverage</span><span className="font-semibold text-slate-800">{overview.reviewedDocuments} of {overview.activeDocuments}</span></div><div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-indigo-500" style={{ width: `${overview.activeDocuments ? Math.round(overview.reviewedDocuments / overview.activeDocuments * 100) : 0}%` }} /></div></div>
        <Link href={`/projects/${project.id}/ai-review`} className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-blue-700 hover:underline">Open Document Review<ArrowRight className="h-4 w-4" /></Link>
      </div>
    </div>
  </Card>;
}

function MiniMetric({ icon, value, label, tone }: { icon: ReactNode; value: number; label: string; tone: "blue" | "purple" | "sky" | "amber" }) {
  const style = { blue: "bg-blue-50 text-blue-700", purple: "bg-violet-50 text-violet-700", sky: "bg-cyan-50 text-cyan-700", amber: "bg-amber-50 text-amber-700" }[tone];
  return <div className={`rounded-xl border border-slate-100 p-3 ${style}`}><div className="flex items-center gap-2 [&_svg]:h-4 [&_svg]:w-4">{icon}<strong className="text-xl tabular-nums text-slate-950">{value}</strong></div><p className="mt-1 text-[11px] font-semibold text-slate-600">{label}</p></div>;
}

function AttentionCard({ projects }: { projects: ProjectOverview[] }) {
  return <Card className="p-5 shadow-[0_8px_24px_rgba(15,23,42,.05)]"><div className="flex items-center gap-3"><span className={`grid h-10 w-10 place-items-center rounded-xl ${projects.length ? "bg-amber-100 text-amber-700" : "bg-emerald-100 text-emerald-700"}`}>{projects.length ? <AlertTriangle className="h-5 w-5" /> : <CheckCircle2 className="h-5 w-5" />}</span><div><h2 className="font-semibold text-slate-900">Needs Attention</h2><p className="text-xs text-slate-500">Current document-review exceptions</p></div></div>{projects.length ? <div className="mt-4 space-y-3">{projects.map((item) => <Link key={item.project.id} href={`/projects/${item.project.id}/ai-review`} className="flex items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50/60 p-4 hover:bg-amber-50"><div><p className="text-sm font-semibold text-slate-900">{item.project.name}</p><p className="mt-1 text-xs text-slate-600">{attentionDescription(item)}</p></div><ArrowRight className="h-4 w-4 shrink-0 text-amber-700" /></Link>)}</div> : <div className="mt-5 rounded-xl bg-emerald-50 p-4"><p className="text-sm font-semibold text-emerald-900">No unresolved review exceptions</p><p className="mt-1 text-xs leading-5 text-emerald-700">Current active project documents have completed review and no open conflicts.</p></div>}</Card>;
}

function ActivityCard({ events }: { events: ActivityItem[] }) {
  return <Card className="overflow-hidden shadow-[0_8px_24px_rgba(15,23,42,.05)]"><div className="flex items-center gap-3 border-b px-5 py-4"><span className="grid h-10 w-10 place-items-center rounded-xl bg-blue-100 text-blue-700"><Activity className="h-5 w-5" /></span><div><h2 className="font-semibold text-slate-900">Recent Activity</h2><p className="text-xs text-slate-500">Recorded production workflow events</p></div></div>{events.length ? <ol className="divide-y">{events.slice(0, 8).map((event) => <li key={`${event.projectId}-${event.id}`} className="flex gap-3 px-5 py-3.5"><span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-blue-500 ring-4 ring-blue-50" /><div className="min-w-0 flex-1"><div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between"><p className="text-sm font-medium text-slate-800">{dashboardActivityLabel(event.action_code)}</p><time className="shrink-0 text-[11px] text-slate-400">{formatDashboardDate(event.occurred_at)}</time></div><Link href={`/projects/${event.projectId}/activity`} className="mt-0.5 block truncate text-xs text-slate-500 hover:text-blue-700 hover:underline">{event.projectName}</Link></div></li>)}</ol> : <div className="p-8 text-center text-sm text-slate-500">No production activity has been recorded.</div>}</Card>;
}

function DashboardState({ title, message, retry }: { title: string; message?: string; retry?: () => void }) {
  return <Card className="mx-auto flex min-h-72 max-w-2xl flex-col items-center justify-center p-8 text-center"><FolderKanban className="h-9 w-9 text-slate-300" /><h1 className="mt-4 text-lg font-semibold text-slate-900">{title}</h1>{message && <p className="mt-2 text-sm text-slate-500">{message}</p>}{retry && <button type="button" onClick={retry} className="mt-4 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white">Try again</button>}</Card>;
}

async function loadDashboard(slug: string, signal: AbortSignal): Promise<DashboardData> {
  const allProjects: ProductionProject[] = [];
  let page = 1;
  let hasNext = true;
  while (hasNext) {
    const response = await projectsApi.list(slug, page, signal);
    allProjects.push(...response.results);
    hasNext = Boolean(response.next);
    page += 1;
  }
  const activeProjects = allProjects.filter((project) => project.is_active);
  const loaded = await Promise.all(activeProjects.map(async (project) => {
    const [documents, conflicts, snapshots, activity] = await Promise.all([
      documentsApi.list(slug, project.id, signal), analysisApi.conflicts(slug, project.id, signal),
      analysisApi.snapshots(slug, project.id, signal), projectsApi.auditEvents(slug, project.id, 1, signal),
    ]);
    const currentDocuments = documents.results.filter((document) => document.is_active && document.current_revision);
    const runFindings = await Promise.all(currentDocuments.map(async (document) => {
      const revision = document.current_revision!;
      const runs = await analysisApi.list(slug, project.id, document.id, revision.id, signal);
      const run = runs.filter((candidate) => candidate.status === "succeeded").sort((a, b) => b.id - a.id)[0];
      return run ? { runId: run.id, findings: await analysisApi.findings(slug, project.id, run.id, signal) } : null;
    }));
    const selectedRunIds = new Set(runFindings.flatMap((item) => item ? [item.runId] : []));
    const findings = runFindings.flatMap((item) => item?.findings ?? []);
    const relevantConflicts = conflicts.filter((conflict) => selectedRunIds.has(conflict.analysis_run));
    const review = dashboardReviewCounts(findings, relevantConflicts);
    const reviewedDocuments = runFindings.filter((item) => item && dashboardReviewCounts(item.findings, relevantConflicts.filter((conflict) => conflict.analysis_run === item.runId)).complete).length;
    const approvedSnapshots = snapshots.filter((snapshot) => snapshot.approval);
    const approvedSnapshot = [...approvedSnapshots].sort((a, b) => b.version - a.version)[0] ?? null;
    const overview: ProjectOverview = { project, activeDocuments: currentDocuments.length, reviewedDocuments, review, approvedSnapshot, approvedSnapshotCount: approvedSnapshots.length, needsAttention: projectNeedsAttention({ activeDocumentCount: currentDocuments.length, reviewedDocumentCount: reviewedDocuments, needsAttention: review.needsAttention, conflicts: review.conflicts }) };
    return { overview, activity: activity.results.map((event) => ({ ...event, projectId: project.id, projectName: project.name })) };
  }));
  return { projects: loaded.map((item) => item.overview), activity: loaded.flatMap((item) => item.activity).sort((a, b) => Date.parse(b.occurred_at) - Date.parse(a.occurred_at)) };
}

function attentionDescription(item: ProjectOverview) {
  const parts: string[] = [];
  const incomplete = item.activeDocuments - item.reviewedDocuments;
  if (incomplete > 0) parts.push(`${incomplete} current document${incomplete === 1 ? "" : "s"} not fully reviewed`);
  if (item.review.needsAttention) parts.push(`${item.review.needsAttention} finding${item.review.needsAttention === 1 ? "" : "s"} need follow-up`);
  if (item.review.conflicts) parts.push(`${item.review.conflicts} open conflict${item.review.conflicts === 1 ? "" : "s"}`);
  return parts.join(" · ");
}

function projectProgress(overview: ProjectOverview) {
  if (overview.approvedSnapshot) return 100;
  if (overview.review.complete) return 80;
  if (overview.review.total) return 60;
  if (overview.activeDocuments) return 40;
  return 20;
}

function formatDashboardDate(value?: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-CA", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value));
}
