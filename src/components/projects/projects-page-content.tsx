"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { AlertCircle, Archive, ArrowRight, Building2, ChevronLeft, ChevronRight, FolderCheck, FolderSearch, Plus, RefreshCw } from "lucide-react";
import { ApiError } from "@/lib/api-client";
import type { OrganizationMembership } from "@/lib/auth";
import { projectsApi, type PaginatedProjects } from "@/lib/projects";
import { projectPortfolioCounts } from "@/lib/project-list-presentation";
import { formatDate } from "@/lib/utils";
import { useOrganization, canEditProjects } from "@/components/organizations/organization-provider";
import { OrganizationAccessState } from "@/components/organizations/organization-access-state";
import { Card } from "@/components/ui/card";
import { ProjectFilters } from "./project-filters";
import { ProductionProjectStatus } from "./production-project-status";

export function ProjectsPageContent() {
  const { memberships, activeMembership } = useOrganization();
  if (!activeMembership) return <OrganizationAccessState multiple={memberships.length > 1} />;
  return <OrganizationProjects key={activeMembership.organization.slug} activeMembership={activeMembership} />;
}

function OrganizationProjects({ activeMembership }: { activeMembership: OrganizationMembership }) {
  const [data, setData] = useState<PaginatedProjects | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const [search, setSearch] = useState("");
  const [stage, setStage] = useState("all");
  const [type, setType] = useState("all");

  useEffect(() => {
    const controller = new AbortController();
    projectsApi.list(activeMembership.organization.slug, page, controller.signal)
      .then(setData)
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof ApiError && reason.status === 403
          ? "You no longer have access to this organization."
          : reason instanceof Error ? reason.message : "Projects could not be loaded.");
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [activeMembership, page, reload]);

  const projects = useMemo(() => data?.results ?? [], [data]);
  const types = useMemo(() => [...new Set(projects.map((project) => project.project_type_label))].sort(), [projects]);
  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return projects.filter((project) =>
      (!query || [project.name, project.project_number, project.client_name].some((value) => value.toLowerCase().includes(query))) &&
      (stage === "all" || project.status === stage) &&
      (type === "all" || project.project_type_label === type));
  }, [projects, search, stage, type]);

  const counts = projectPortfolioCounts(projects);

  return (
    <div className="mx-auto max-w-[1500px]">
      <div className="flex flex-col gap-4 rounded-2xl bg-[#102a43] px-6 py-7 text-white shadow-[0_14px_35px_rgba(15,42,67,.18)] sm:flex-row sm:items-end sm:justify-between sm:px-8">
        <div><div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[.12em] text-blue-200"><span>BB Builders</span><span className="text-blue-400">/</span><span>Projects</span></div><h1 className="mt-2 text-2xl font-semibold tracking-tight text-white sm:text-[28px]">Projects</h1><p className="mt-1 max-w-2xl text-sm leading-6 text-slate-300">Persistent project records for {activeMembership.organization.name}.</p></div>
        {canEditProjects(activeMembership) && <Link href="/projects/new" className="inline-flex h-10 items-center justify-center gap-2 self-start rounded-lg bg-white px-4 text-sm font-semibold text-[#173f5f] shadow-sm hover:bg-blue-50"><Plus className="h-4 w-4" />New Project</Link>}
      </div>
      <section aria-label="Project summary" className="mt-6 grid gap-4 sm:grid-cols-3">
        <SummaryCard label="Total projects" value={data?.count ?? counts.total} detail="All persistent records" icon={<Building2 className="h-5 w-5" />} tone="blue" />
        <SummaryCard label="Active projects" value={counts.active} detail="Currently in workflow" icon={<FolderCheck className="h-5 w-5" />} tone="green" />
        <SummaryCard label="Archived projects" value={counts.archived} detail="Preserved historical records" icon={<Archive className="h-5 w-5" />} tone="slate" />
      </section>
      <Card className="mt-6 overflow-hidden shadow-[0_10px_30px_rgba(15,23,42,.07)]">
        <div className="flex items-center justify-between gap-4 px-5 py-5"><div><h2 className="font-semibold text-slate-900">Project Portfolio</h2><p className="mt-0.5 text-xs text-slate-500">{data ? `${filtered.length} records shown on this page` : "Production project records"}</p></div><button type="button" onClick={() => { setLoading(true); setError(null); setReload((value) => value + 1); }} disabled={loading} className="rounded-lg border border-slate-200 bg-white p-2 text-slate-500 shadow-sm hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700 disabled:opacity-50" aria-label="Refresh projects"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /></button></div>
        <ProjectFilters search={search} onSearch={setSearch} stage={stage} onStage={setStage} type={type} onType={setType} types={types} />
        {loading && !data ? <State title="Loading projects…" /> : error ? <State title="Projects unavailable" message={error} error /> : !projects.length ? <State title="No projects yet" message={canEditProjects(activeMembership) ? "Create the first persistent project for this organization." : "No project records are available for this organization."} /> : !filtered.length ? <State title="No projects found" message="Adjust the search or filters to see matching projects." /> : (
          <div className="overflow-x-auto"><table className="w-full min-w-[980px] text-left"><thead className="border-y bg-slate-50/90 text-[11px] uppercase tracking-[.1em] text-slate-500"><tr>{["Project", "Project #", "Client / Location", "Type", "Bid Deadline", "Status", "Updated", "Action"].map((heading) => <th key={heading} className="px-5 py-3 font-semibold">{heading}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">{filtered.map((project) => <tr key={project.id} className={project.is_active ? "bg-blue-50/25 transition hover:bg-blue-50/60" : "bg-slate-50/65 text-slate-500 transition hover:bg-slate-100/80"}><td className={`border-l-4 px-5 py-4 ${project.is_active ? "border-l-blue-500" : "border-l-transparent"}`}><Link href={`/projects/${project.id}`} className={`font-semibold hover:text-blue-700 hover:underline ${project.is_active ? "text-slate-950" : "text-slate-600"}`}>{project.name}</Link><p className={`mt-1 text-[11px] font-semibold uppercase tracking-wide ${project.is_active ? "text-emerald-600" : "text-slate-400"}`}>{project.is_active ? "Active project" : "Historical record"}</p></td><td className="px-5 py-4 text-sm">{project.project_number}</td><td className="px-5 py-4 text-sm"><span className={`block font-medium ${project.is_active ? "text-slate-800" : "text-slate-500"}`}>{project.client_name || "—"}</span><span className="mt-0.5 block text-xs">{[project.city, project.province_state].filter(Boolean).join(", ") || "Location not set"}</span></td><td className="px-5 py-4 text-sm">{project.project_type_label}</td><td className="px-5 py-4 text-sm">{project.bid_deadline ? formatDate(project.bid_deadline) : "—"}</td><td className="px-5 py-4"><ProductionProjectStatus status={project.status} archived={!project.is_active} /></td><td className="px-5 py-4 text-sm">{formatDate(project.updated_at)}</td><td className="px-5 py-4"><Link href={`/projects/${project.id}`} className={project.is_active ? "inline-flex h-9 items-center gap-1.5 rounded-lg bg-[#173f5f] px-3 text-sm font-semibold text-white shadow-sm hover:bg-[#102f49]" : "inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-600 shadow-sm hover:border-blue-200 hover:text-blue-700"}>Open Project<ArrowRight className="h-3.5 w-3.5" /></Link></td></tr>)}</tbody></table></div>
        )}
        {data && (data.previous || data.next) && <div className="flex items-center justify-between border-t px-5 py-4 text-sm"><span className="text-slate-500">Page {page} · {data.count} projects</span><div className="flex gap-2"><button type="button" onClick={() => { setLoading(true); setError(null); setPage((value) => value - 1); }} disabled={!data.previous || loading} className="inline-flex h-9 items-center gap-1 rounded-lg border px-3 font-medium disabled:opacity-40"><ChevronLeft className="h-4 w-4" />Previous</button><button type="button" onClick={() => { setLoading(true); setError(null); setPage((value) => value + 1); }} disabled={!data.next || loading} className="inline-flex h-9 items-center gap-1 rounded-lg border px-3 font-medium disabled:opacity-40">Next<ChevronRight className="h-4 w-4" /></button></div></div>}
      </Card>
    </div>
  );
}

function SummaryCard({ label, value, detail, icon, tone }: { label: string; value: number; detail: string; icon: React.ReactNode; tone: "blue" | "green" | "slate" }) {
  const styles = { blue: "border-t-blue-500 bg-blue-50/35 text-blue-700", green: "border-t-emerald-500 bg-emerald-50/35 text-emerald-700", slate: "border-t-slate-400 bg-slate-50/70 text-slate-600" }[tone];
  return <Card className={`border-t-4 p-5 shadow-[0_8px_24px_rgba(15,23,42,.06)] ${styles}`}><div className="flex items-start justify-between"><div><p className="text-3xl font-semibold tabular-nums text-slate-950">{value}</p><p className="mt-1 text-sm font-semibold text-slate-800">{label}</p></div><span className="grid h-10 w-10 place-items-center rounded-xl bg-white shadow-sm">{icon}</span></div><p className="mt-3 text-xs text-slate-500">{detail}</p></Card>;
}

function State({ title, message, error = false }: { title: string; message?: string; error?: boolean }) {
  const Icon = error ? AlertCircle : FolderSearch;
  return <div className="flex min-h-56 flex-col items-center justify-center p-8 text-center"><Icon className="h-8 w-8 text-slate-400" /><h3 className="mt-3 font-semibold">{title}</h3>{message && <p className="mt-1 max-w-lg text-sm text-slate-500">{message}</p>}</div>;
}
