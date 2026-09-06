"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { AlertCircle, Archive, ArchiveRestore, CalendarClock, Database, FileClock, MapPin, Pencil, UserRound } from "lucide-react";
import { ApiError } from "@/lib/api-client";
import type { OrganizationMembership } from "@/lib/auth";
import { formatProjectDateTime } from "@/lib/project-time";
import { projectsApi, type ProductionProject } from "@/lib/projects";
import { formatDate } from "@/lib/utils";
import { OrganizationAccessState } from "@/components/organizations/organization-access-state";
import { canEditProjects, useOrganization } from "@/components/organizations/organization-provider";
import { Card } from "@/components/ui/card";
import { ProductionDocumentsModule } from "@/components/documents/production-documents-module";
import { ProductionAIReviewModule } from "@/components/ai-review/production-ai-review-module";
import { ProductionScopesModule } from "@/components/scopes/production-scopes-module";
import { ProductionContractorsModule } from "@/components/contractors/production-contractors-module";
import { ProductionProjectForm } from "./production-project-form";
import { ProductionProjectStatus } from "./production-project-status";
import { ProjectWorkspaceTabs } from "./project-workspace-tabs";
import { ProductionProjectActivity } from "./production-project-activity";

const workflowStates: Record<string, { title: string; description: string }> = {
  documents: { title: "No documents have been added", description: "Project documents will appear here after they are uploaded." },
  "ai-review": { title: "Document review is waiting for source files", description: "Project intelligence becomes available after documents are added and processed." },
  scopes: { title: "No trade scopes are available", description: "Trade scope preparation begins after project document review." },
  contractors: { title: "Contractor discovery is not active", description: "Subcontractor sourcing begins after trade requirements are reviewed." },
  outreach: { title: "No outreach has been prepared", description: "Outreach activity will appear after recipients and bid packages are approved." },
  bids: { title: "No bids have been received", description: "Bid submissions associated with this project will appear here." },
  comparisons: { title: "No bid comparisons are available", description: "Comparisons become available after eligible bids are received and reviewed." },
  proposal: { title: "No proposal has been prepared", description: "Client proposal information will appear here when it is ready." },
};

export function ProductionProjectWorkspace({ projectId }: { projectId: string }) {
  const { memberships, activeMembership } = useOrganization();
  if (!activeMembership) return <OrganizationAccessState multiple={memberships.length > 1} />;
  return <OrganizationProjectWorkspace key={`${activeMembership.organization.slug}:${projectId}`} projectId={projectId} membership={activeMembership} />;
}

function OrganizationProjectWorkspace({ projectId, membership }: { projectId: string; membership: OrganizationMembership }) {
  const pathname = usePathname();
  const [project, setProject] = useState<ProductionProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ title: string; detail: string } | null>(null);
  const [editing, setEditing] = useState(false);
  const [changingArchive, setChangingArchive] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    projectsApi.retrieve(membership.organization.slug, projectId, controller.signal)
      .then(setProject)
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        if (reason instanceof ApiError && reason.status === 404) setError({ title: "Project not found", detail: "This project does not exist in the selected organization." });
        else if (reason instanceof ApiError && reason.status === 403) setError({ title: "Project access denied", detail: "Your current organization membership does not allow access to this project." });
        else setError({ title: "Project unavailable", detail: reason instanceof Error ? reason.message : "The project could not be loaded." });
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [membership, projectId]);

  if (loading) return <WorkspaceState title="Loading project…" detail="Retrieving the latest persistent project record." />;
  if (error) return <WorkspaceState title={error.title} detail={error.detail} error />;
  if (!project) return null;

  const base = `/projects/${projectId}`;
  const section = pathname === base ? "overview" : pathname.slice(base.length + 1).split("/")[0];
  const futureState = workflowStates[section];
  const canEdit = canEditProjects(membership);
  const isAdmin = membership.role === "admin";

  async function toggleArchive() {
    if (!project || !isAdmin || changingArchive) return;
    if (project.is_active && !window.confirm(`Archive ${project.project_number} — ${project.name}? The project will remain recoverable.`)) return;
    setChangingArchive(true); setError(null);
    try { setProject(await projectsApi.update(membership.organization.slug, project.id, { is_active: !project.is_active })); }
    catch (reason) { setError({ title: "Project could not be updated", detail: reason instanceof Error ? reason.message : "Try again." }); }
    finally { setChangingArchive(false); }
  }

  return (
    <div className="mx-auto max-w-[1500px] space-y-5">
      <header className={`overflow-hidden rounded-2xl border shadow-[0_12px_32px_rgba(15,42,67,.09)] ${project.is_active ? "border-blue-100 bg-white" : "border-slate-300 bg-slate-50"}`}>
        {!project.is_active && <div className="flex items-center gap-2 border-b border-slate-300 bg-slate-200/70 px-5 py-2 text-xs font-semibold text-slate-700 sm:px-7"><Archive className="h-3.5 w-3.5" />Archived project · Historical records remain available</div>}
        <div className="border-t-4 border-t-[#173f5f] p-5 sm:p-7">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-[#173f5f] px-3 py-1 text-[11px] font-bold uppercase tracking-[.12em] text-white">{project.project_number}</span><span className="inline-flex items-center gap-1 rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-blue-700"><Database className="h-3 w-3" />Production</span><ProductionProjectStatus status={project.status} archived={!project.is_active} /></div><h1 className={`mt-3 text-2xl font-semibold tracking-tight sm:text-[30px] ${project.is_active ? "text-slate-950" : "text-slate-700"}`}>{project.name}</h1><div className="mt-4 flex flex-wrap gap-2.5 text-sm"><MetadataChip icon={<UserRound />} label="Client" value={project.client_name || "Not set"} /><MetadataChip icon={<MapPin />} label="Location" value={[project.city, project.province_state].filter(Boolean).join(", ") || "Not set"} /><MetadataChip icon={<CalendarClock />} label="Bid deadline" value={formatProjectDateTime(project.bid_deadline, project.project_timezone)} /></div></div>
          <div className="flex shrink-0 flex-wrap gap-2 rounded-xl border border-slate-200 bg-slate-50/80 p-2">{canEdit && section === "overview" && <button type="button" onClick={() => setEditing((value) => !value)} className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 shadow-sm hover:border-blue-200 hover:text-blue-700"><Pencil className="h-4 w-4" />{editing ? "Close Edit" : "Edit Project"}</button>}{isAdmin && <button type="button" onClick={() => void toggleArchive()} disabled={changingArchive} className={`inline-flex h-9 items-center gap-2 rounded-lg border bg-white px-3 text-sm font-semibold shadow-sm disabled:opacity-50 ${project.is_active ? "border-slate-200 text-slate-600 hover:border-amber-300 hover:text-amber-700" : "border-emerald-200 text-emerald-700 hover:bg-emerald-50"}`}>{project.is_active ? <Archive className="h-4 w-4" /> : <ArchiveRestore className="h-4 w-4" />}{changingArchive ? "Saving…" : project.is_active ? "Archive" : "Reactivate"}</button>}</div>
        </div>
        </div>
      </header>
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_10px_30px_rgba(15,23,42,.06)]"><ProjectWorkspaceTabs projectId={projectId} /><div className="min-w-0 bg-slate-50/35 p-4 sm:p-6">{section === "overview" ? editing && canEdit ? <ProductionProjectForm key={project.updated_at} organizationSlug={membership.organization.slug} project={project} onSaved={(saved) => { setProject(saved); setEditing(false); }} onCancel={() => setEditing(false)} /> : <ProjectMetadata project={project} /> : section === "documents" ? <ProductionDocumentsModule project={project} membership={membership} onProjectDocumentsUploaded={() => setProject((current) => current?.status === "draft" ? { ...current, status: "documents_uploaded" } : current)} /> : section === "ai-review" ? <ProductionAIReviewModule project={project} membership={membership} /> : section === "scopes" ? <ProductionScopesModule project={project} membership={membership} /> : section === "contractors" ? <ProductionContractorsModule project={project} membership={membership} /> : section === "activity" ? <ProductionProjectActivity project={project} membership={membership} /> : futureState ? <FutureWorkflowState {...futureState} /> : <WorkspaceState title="Page not found" detail="This project workspace page is not available." error />}</div></div>
    </div>
  );
}

function ProjectMetadata({ project }: { project: ProductionProject }) {
  const rows = [
    ["Project number", project.project_number], ["Client", project.client_name || "—"], ["Project type", project.project_type_label],
    ["Project timezone", project.project_timezone], ["Area", project.estimated_area ? `${Number(project.estimated_area).toLocaleString("en-CA")} ${project.area_unit_label.toLowerCase()}` : "—"],
    ["Address", [project.site_address_line_1, project.site_address_line_2, project.city, project.province_state, project.postal_zip_code, project.country].filter(Boolean).join(", ") || "—"],
    ["Questions deadline", formatProjectDateTime(project.questions_deadline, project.project_timezone)], ["Site visit", project.site_visit_date ? formatDate(project.site_visit_date) : "—"],
    ["Planned start", project.planned_start_date ? formatDate(project.planned_start_date) : "—"], ["Substantial completion", project.substantial_completion_date ? formatDate(project.substantial_completion_date) : "—"],
    ["Opening / handover", project.opening_or_handover_date ? formatDate(project.opening_or_handover_date) : "—"], ["Created by", project.created_by],
    ["Created", formatProjectDateTime(project.created_at, project.project_timezone)], ["Updated", formatProjectDateTime(project.updated_at, project.project_timezone)],
  ];
  return <div className="space-y-5"><div><h2 className="text-lg font-semibold text-slate-900">Project Details</h2><p className="mt-1 text-sm text-slate-500">Persistent project information used across the preconstruction workspace.</p></div><section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{rows.map(([label, value], index) => <Card key={label} className={`border-slate-200 p-4 shadow-sm ${index < 3 ? "border-t-2 border-t-blue-400 bg-blue-50/20" : "bg-white"}`}><dt className="text-[11px] font-bold uppercase tracking-[.1em] text-slate-500">{label}</dt><dd className="mt-2 text-sm font-semibold leading-6 text-slate-800">{value}</dd></Card>)}</section>{project.description && <Card className="overflow-hidden border-slate-200 shadow-sm"><div className="border-b bg-slate-50 px-5 py-3"><h2 className="font-semibold text-slate-900">Project Description</h2></div><p className="whitespace-pre-wrap px-5 py-4 text-sm leading-6 text-slate-600">{project.description}</p></Card>}</div>;
}

function MetadataChip({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return <span className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50/80 px-3 py-2 text-slate-600 shadow-sm [&_svg]:h-4 [&_svg]:w-4 [&_svg]:text-blue-600"><span aria-hidden="true">{icon}</span><span><span className="sr-only">{label}: </span>{value}</span></span>;
}

function FutureWorkflowState({ title, description }: { title: string; description: string }) {
  return <section className="flex min-h-64 flex-col items-center justify-center rounded-xl border border-dashed bg-white px-6 text-center"><div className="rounded-xl bg-slate-100 p-3 text-slate-500"><FileClock className="h-5 w-5" /></div><h2 className="mt-4 font-semibold">{title}</h2><p className="mt-1 max-w-lg text-sm leading-6 text-slate-500">{description}</p></section>;
}

function WorkspaceState({ title, detail, error = false }: { title: string; detail: string; error?: boolean }) {
  return <Card className="mx-auto flex min-h-64 max-w-2xl flex-col items-center justify-center p-8 text-center">{error && <AlertCircle className="h-7 w-7 text-red-500" />}<h1 className="mt-3 text-xl font-semibold">{title}</h1><p className="mt-2 text-sm text-slate-500">{detail}</p><Link href="/projects" className="mt-5 text-sm font-semibold text-blue-700 hover:underline">Back to Projects</Link></Card>;
}
