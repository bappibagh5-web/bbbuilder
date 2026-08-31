"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { AlertCircle, ChevronLeft, ChevronRight, FolderSearch, Plus, RefreshCw } from "lucide-react";
import { ApiError } from "@/lib/api-client";
import type { OrganizationMembership } from "@/lib/auth";
import { projectsApi, type PaginatedProjects } from "@/lib/projects";
import { formatDate } from "@/lib/utils";
import { useOrganization, canEditProjects } from "@/components/organizations/organization-provider";
import { OrganizationAccessState } from "@/components/organizations/organization-access-state";
import { PageHeader } from "@/components/page-header";
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

  const activeCount = projects.filter((project) => project.is_active).length;
  const archivedCount = projects.length - activeCount;

  return (
    <div className="mx-auto max-w-[1500px]">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <PageHeader title="Projects" description={`Persistent project records for ${activeMembership.organization.name}.`} />
        {canEditProjects(activeMembership) && <Link href="/projects/new" className="inline-flex h-10 items-center justify-center gap-2 self-start rounded-lg bg-primary px-4 text-sm font-semibold text-white hover:bg-[#204563]"><Plus className="h-4 w-4" />New Project</Link>}
      </div>
      <section aria-label="Project summary" className="mt-7 grid gap-3 sm:grid-cols-3">
        {[["All projects", data?.count ?? 0], ["Active on this page", activeCount], ["Archived on this page", archivedCount]].map(([label, value]) => <Card key={label} className="p-4"><p className="text-2xl font-semibold text-slate-900">{value}</p><p className="text-xs font-medium text-slate-500">{label}</p></Card>)}
      </section>
      <Card className="mt-6 overflow-hidden">
        <div className="flex items-center justify-between gap-4 px-5 py-4"><div><h2 className="font-semibold text-slate-900">Project Portfolio</h2><p className="mt-0.5 text-xs text-slate-500">{data ? `${filtered.length} records shown on this page` : "Production project records"}</p></div><button type="button" onClick={() => { setLoading(true); setError(null); setReload((value) => value + 1); }} disabled={loading} className="rounded-lg border p-2 text-slate-500 hover:bg-slate-50 disabled:opacity-50" aria-label="Refresh projects"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /></button></div>
        <ProjectFilters search={search} onSearch={setSearch} stage={stage} onStage={setStage} type={type} onType={setType} types={types} />
        {loading && !data ? <State title="Loading projects…" /> : error ? <State title="Projects unavailable" message={error} error /> : !projects.length ? <State title="No projects yet" message={canEditProjects(activeMembership) ? "Create the first persistent project for this organization." : "No project records are available for this organization."} /> : !filtered.length ? <State title="No projects found" message="Adjust the search or filters to see matching projects." /> : (
          <div className="overflow-x-auto"><table className="w-full min-w-[980px] text-left"><thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500"><tr>{["Project", "Project #", "Client / Location", "Type", "Bid Deadline", "Status", "Updated", "Action"].map((heading) => <th key={heading} className="px-4 py-3 font-semibold">{heading}</th>)}</tr></thead><tbody className="divide-y">{filtered.map((project) => <tr key={project.id} className="hover:bg-slate-50/70"><td className="px-4 py-4"><Link href={`/projects/${project.id}`} className="font-medium text-slate-900 hover:text-blue-700 hover:underline">{project.name}</Link>{!project.is_active && <p className="mt-1 text-xs font-medium text-slate-500">Archived project</p>}</td><td className="px-4 py-4 text-sm text-slate-600">{project.project_number}</td><td className="px-4 py-4 text-sm text-slate-600"><span className="block text-slate-800">{project.client_name || "—"}</span><span className="text-xs">{[project.city, project.province_state].filter(Boolean).join(", ") || "Location not set"}</span></td><td className="px-4 py-4 text-sm text-slate-600">{project.project_type_label}</td><td className="px-4 py-4 text-sm text-slate-600">{project.bid_deadline ? formatDate(project.bid_deadline) : "—"}</td><td className="px-4 py-4"><ProductionProjectStatus status={project.status} archived={!project.is_active} /></td><td className="px-4 py-4 text-sm text-slate-600">{formatDate(project.updated_at)}</td><td className="px-4 py-4"><Link href={`/projects/${project.id}`} className="text-sm font-semibold text-blue-700 hover:underline">Open Project</Link></td></tr>)}</tbody></table></div>
        )}
        {data && (data.previous || data.next) && <div className="flex items-center justify-between border-t px-5 py-4 text-sm"><span className="text-slate-500">Page {page} · {data.count} projects</span><div className="flex gap-2"><button type="button" onClick={() => { setLoading(true); setError(null); setPage((value) => value - 1); }} disabled={!data.previous || loading} className="inline-flex h-9 items-center gap-1 rounded-lg border px-3 font-medium disabled:opacity-40"><ChevronLeft className="h-4 w-4" />Previous</button><button type="button" onClick={() => { setLoading(true); setError(null); setPage((value) => value + 1); }} disabled={!data.next || loading} className="inline-flex h-9 items-center gap-1 rounded-lg border px-3 font-medium disabled:opacity-40">Next<ChevronRight className="h-4 w-4" /></button></div></div>}
      </Card>
    </div>
  );
}

function State({ title, message, error = false }: { title: string; message?: string; error?: boolean }) {
  const Icon = error ? AlertCircle : FolderSearch;
  return <div className="flex min-h-56 flex-col items-center justify-center p-8 text-center"><Icon className="h-8 w-8 text-slate-400" /><h3 className="mt-3 font-semibold">{title}</h3>{message && <p className="mt-1 max-w-lg text-sm text-slate-500">{message}</p>}</div>;
}
