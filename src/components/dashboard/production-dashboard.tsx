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
import { ApiError } from "@/lib/api-client";
import { dashboardApi, type DashboardActivity, type DashboardProjectSummary, type DashboardSummary } from "@/lib/dashboard";
import { dashboardActivityLabel, dashboardAttentionDescription } from "@/lib/dashboard-state";

export function ProductionDashboard() {
  const { memberships, activeMembership } = useOrganization();
  if (!activeMembership) return <OrganizationAccessState multiple={memberships.length > 1} />;
  return <OrganizationDashboard key={activeMembership.organization.slug} slug={activeMembership.organization.slug} organizationName={activeMembership.organization.name} />;
}

function OrganizationDashboard({ slug, organizationName }: { slug: string; organizationName: string }) {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [activity, setActivity] = useState<DashboardActivity[]>([]);
  const [loading, setLoading] = useState(true);
  const [activityLoading, setActivityLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activityError, setActivityError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    dashboardApi.summary(slug, controller.signal)
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

  useEffect(() => {
    const controller = new AbortController();
    dashboardApi.activity(slug, controller.signal)
      .then((response) => setActivity(response.results))
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setActivityError(reason instanceof Error ? reason.message : "Recent activity could not be loaded.");
        }
      })
      .finally(() => { if (!controller.signal.aborted) setActivityLoading(false); });
    return () => controller.abort();
  }, [slug, reload]);

  const projects = data?.projects ?? [];
  const summary = data?.summary;
  const refresh = () => {
    setLoading(true);
    setActivityLoading(true);
    setError(null);
    setActivityError(null);
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

      {error && data && <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">Showing the last loaded dashboard. Refresh failed: {error}</div>}

      {!data && loading ? <DashboardSkeleton /> : error && !data ? <DashboardState title="Dashboard unavailable" message={error} retry={refresh} /> : <>
        <section aria-label="Production overview" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard label="Active projects" value={summary?.active_projects ?? 0} detail="Persistent production projects" icon={<Building2 />} tone="blue" />
          <KpiCard label="Needs attention" value={summary?.needs_attention ?? 0} detail={summary?.needs_attention ? "Project reviews needing follow-up" : "No unresolved review exceptions"} icon={<AlertTriangle />} tone={summary?.needs_attention ? "amber" : "green"} />
          <KpiCard label="Project reviews complete" value={summary?.project_reviews_complete ?? 0} detail="Current active project reviews" icon={<FileCheck2 />} tone="indigo" />
          <KpiCard label="Approved information" value={summary?.approved_information ?? 0} detail="Approved project information versions" icon={<BadgeCheck />} tone="green" />
        </section>

      <section aria-labelledby="active-projects-heading">
        <div className="mb-3 flex items-end justify-between gap-4">
          <div><h2 id="active-projects-heading" className="text-lg font-semibold text-slate-900">Active Projects</h2><p className="mt-1 text-sm text-slate-500">Current project stage and review readiness.</p></div>
          <Link href="/projects" className="hidden items-center gap-1 text-sm font-semibold text-blue-700 hover:underline sm:inline-flex">View all projects<ArrowRight className="h-4 w-4" /></Link>
        </div>
        {projects.length ? <div className="grid gap-5">{projects.map((overview) => <ProjectCard key={overview.project.id} overview={overview} />)}</div> : <Card className="border-dashed p-10 text-center"><FolderKanban className="mx-auto h-9 w-9 text-slate-300" /><h3 className="mt-3 font-semibold text-slate-800">No active projects</h3><p className="mt-1 text-sm text-slate-500">Active production projects will appear here.</p></Card>}
      </section>

      <section className="grid gap-6 xl:grid-cols-[.85fr_1.15fr]">
        <AttentionCard projects={projects.filter((project) => project.needs_attention)} />
        <ActivityCard events={activity} loading={activityLoading} error={activityError} />
      </section>
      </>}
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

function ProjectCard({ overview }: { overview: DashboardProjectSummary }) {
  const { project, review, approved_snapshot: approvedSnapshot } = overview;
  const location = [project.city, project.province_state].filter(Boolean).join(", ") || "Location not set";
  const progress = projectProgress(overview);
  return <Card className="overflow-hidden shadow-[0_10px_28px_rgba(15,23,42,.07)]">
    <div className="grid lg:grid-cols-[1.3fr_.7fr]">
      <div className="p-5 sm:p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div><div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-blue-100 px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide text-blue-700">{project.status_label}</span>{review.complete && <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide text-emerald-700"><CheckCircle2 className="h-3 w-3" />{overview.review_mode === "project_set" ? "Project review complete" : "Document review complete"}</span>}</div><h3 className="mt-3 text-xl font-semibold text-slate-950">{project.name}</h3><p className="mt-1 text-sm text-slate-500">{project.project_number} <span className="px-1 text-slate-300">·</span> <span className="inline-flex items-center gap-1"><MapPin className="h-3.5 w-3.5" />{location}</span></p></div>
          <Link href={`/projects/${project.id}`} className="inline-flex h-10 items-center justify-center gap-2 self-start rounded-lg bg-[#173f5f] px-4 text-sm font-semibold text-white hover:bg-[#102f49]">Open Project<ArrowRight className="h-4 w-4" /></Link>
        </div>
        <div className="mt-6"><div className="mb-2 flex items-center justify-between text-xs"><span className="font-semibold text-slate-700">Milestone 1 progress</span><span className="font-bold text-blue-700">{progress}%</span></div><div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-blue-600 transition-all" style={{ width: `${progress}%` }} /></div><div className="mt-2 grid grid-cols-5 text-[10px] font-medium text-slate-400"><span>Intake</span><span className="text-center">Documents</span><span className="text-center">AI Review</span><span className="text-center">Human Review</span><span className="text-right">Approved</span></div></div>
        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4"><MiniMetric icon={<ClipboardCheck />} value={review.total} label="Findings" tone="blue" /><MiniMetric icon={<Bot />} value={review.ai_handled} label="AI handled" tone="purple" /><MiniMetric icon={<UserCheck />} value={review.reviewed_by_user} label="Reviewed by user" tone="sky" /><MiniMetric icon={<AlertTriangle />} value={review.needs_attention + review.conflicts} label="Needs attention" tone="amber" /></div>
      </div>
      <div className="border-t bg-slate-50/80 p-5 sm:p-6 lg:border-l lg:border-t-0">
        <p className="text-xs font-semibold uppercase tracking-[.12em] text-slate-500">Project information</p>
        {approvedSnapshot ? <div className="mt-4 rounded-xl border border-emerald-200 bg-white p-4 shadow-sm"><div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-100 text-emerald-700"><BadgeCheck className="h-5 w-5" /></span><div><p className="font-semibold text-slate-900">Version {approvedSnapshot.version} approved</p><p className="text-xs text-slate-500">Final human approval recorded</p></div></div><dl className="mt-4 space-y-2 border-t pt-3 text-xs"><div className="flex justify-between gap-3"><dt className="text-slate-500">Approved by</dt><dd className="text-right font-medium text-slate-700">{approvedSnapshot.approver}</dd></div><div className="flex justify-between gap-3"><dt className="text-slate-500">Approved</dt><dd className="text-right font-medium text-slate-700">{formatDashboardDate(approvedSnapshot.approved_at)}</dd></div></dl></div> : <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4"><p className="font-semibold text-amber-900">Approval not yet recorded</p><p className="mt-1 text-xs leading-5 text-amber-800">Complete current document review and prepare project information for approval.</p></div>}
        {overview.project_review ? <div className="mt-4 rounded-xl border bg-white p-4"><p className="text-xs text-slate-500">Estimating set reviewed</p><p className="mt-1 text-sm font-semibold text-slate-800">{overview.project_review.document_count} documents · {overview.project_review.page_count} pages/slides</p>{!overview.project_review.current && <p className="mt-1 text-xs text-amber-700">The selected document set has changed since this review.</p>}</div> : <div className="mt-4 rounded-xl border bg-white p-4"><div className="flex justify-between text-xs"><span className="text-slate-500">Document coverage</span><span className="font-semibold text-slate-800">{overview.reviewed_document_count} of {overview.active_document_count}</span></div><div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-indigo-500" style={{ width: `${overview.active_document_count ? Math.round(overview.reviewed_document_count / overview.active_document_count * 100) : 0}%` }} /></div></div>}
        <Link href={`/projects/${project.id}/ai-review`} className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-blue-700 hover:underline">Open Document Review<ArrowRight className="h-4 w-4" /></Link>
      </div>
    </div>
  </Card>;
}

function MiniMetric({ icon, value, label, tone }: { icon: ReactNode; value: number; label: string; tone: "blue" | "purple" | "sky" | "amber" }) {
  const style = { blue: "bg-blue-50 text-blue-700", purple: "bg-violet-50 text-violet-700", sky: "bg-cyan-50 text-cyan-700", amber: "bg-amber-50 text-amber-700" }[tone];
  return <div className={`rounded-xl border border-slate-100 p-3 ${style}`}><div className="flex items-center gap-2 [&_svg]:h-4 [&_svg]:w-4">{icon}<strong className="text-xl tabular-nums text-slate-950">{value}</strong></div><p className="mt-1 text-[11px] font-semibold text-slate-600">{label}</p></div>;
}

function AttentionCard({ projects }: { projects: DashboardProjectSummary[] }) {
  return <Card className="p-5 shadow-[0_8px_24px_rgba(15,23,42,.05)]"><div className="flex items-center gap-3"><span className={`grid h-10 w-10 place-items-center rounded-xl ${projects.length ? "bg-amber-100 text-amber-700" : "bg-emerald-100 text-emerald-700"}`}>{projects.length ? <AlertTriangle className="h-5 w-5" /> : <CheckCircle2 className="h-5 w-5" />}</span><div><h2 className="font-semibold text-slate-900">Needs Attention</h2><p className="text-xs text-slate-500">Current project-review exceptions</p></div></div>{projects.length ? <div className="mt-4 space-y-3">{projects.map((item) => <Link key={item.project.id} href={`/projects/${item.project.id}/ai-review`} className="flex items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50/60 p-4 hover:bg-amber-50"><div><p className="text-sm font-semibold text-slate-900">{item.project.name}</p><p className="mt-1 text-xs text-slate-600">{dashboardAttentionDescription(item)}</p></div><ArrowRight className="h-4 w-4 shrink-0 text-amber-700" /></Link>)}</div> : <div className="mt-5 rounded-xl bg-emerald-50 p-4"><p className="text-sm font-semibold text-emerald-900">No unresolved review exceptions</p><p className="mt-1 text-xs leading-5 text-emerald-700">Current project reviews have no items needing follow-up or open conflicts.</p></div>}</Card>;
}

function ActivityCard({ events, loading, error }: { events: DashboardActivity[]; loading: boolean; error: string | null }) {
  return <Card className="overflow-hidden shadow-[0_8px_24px_rgba(15,23,42,.05)]"><div className="flex items-center gap-3 border-b px-5 py-4"><span className="grid h-10 w-10 place-items-center rounded-xl bg-blue-100 text-blue-700"><Activity className="h-5 w-5" /></span><div><h2 className="font-semibold text-slate-900">Recent Activity</h2><p className="text-xs text-slate-500">Recorded production workflow events</p></div></div>{error && <p className="border-b border-amber-200 bg-amber-50 px-5 py-2 text-xs text-amber-800">Recent activity could not be refreshed. Showing the last loaded activity.</p>}{loading && !events.length ? <div className="space-y-3 p-5" aria-label="Loading recent activity">{[1, 2, 3].map((item) => <div key={item} className="h-10 animate-pulse rounded-lg bg-slate-100" />)}</div> : events.length ? <ol className="divide-y">{events.map((event) => <li key={`${event.project_id}-${event.id}`} className="flex gap-3 px-5 py-3.5"><span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-blue-500 ring-4 ring-blue-50" /><div className="min-w-0 flex-1"><div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between"><p className="text-sm font-medium text-slate-800">{dashboardActivityLabel(event.action_code)}</p><time className="shrink-0 text-[11px] text-slate-400">{formatDashboardDate(event.occurred_at)}</time></div><Link href={`/projects/${event.project_id}/activity`} className="mt-0.5 block truncate text-xs text-slate-500 hover:text-blue-700 hover:underline">{event.project_name}</Link></div></li>)}</ol> : <div className="p-8 text-center text-sm text-slate-500">{error ? "Recent activity is temporarily unavailable." : "No production activity has been recorded."}</div>}</Card>;
}

function DashboardSkeleton() {
  return <div className="space-y-6" aria-label="Loading dashboard summary"><section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[1, 2, 3, 4].map((item) => <Card key={item} className="h-32 animate-pulse border-t-4 border-t-slate-200 bg-slate-50" />)}</section><Card className="h-64 animate-pulse bg-slate-50" /></div>;
}

function DashboardState({ title, message, retry }: { title: string; message?: string; retry?: () => void }) {
  return <Card className="mx-auto flex min-h-72 max-w-2xl flex-col items-center justify-center p-8 text-center"><FolderKanban className="h-9 w-9 text-slate-300" /><h1 className="mt-4 text-lg font-semibold text-slate-900">{title}</h1>{message && <p className="mt-2 text-sm text-slate-500">{message}</p>}{retry && <button type="button" onClick={retry} className="mt-4 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white">Try again</button>}</Card>;
}

function projectProgress(overview: DashboardProjectSummary) {
  if (overview.approved_snapshot && overview.review.complete) return 100;
  if (overview.review.complete) return 80;
  if (overview.review.total) return 60;
  if (overview.active_document_count) return 40;
  return 20;
}

function formatDashboardDate(value?: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-CA", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value));
}
