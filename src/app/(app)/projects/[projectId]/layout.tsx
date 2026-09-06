import type { Metadata } from "next";
import { getProject, getProjectDetails, projects } from "@/data";
import { ProductionProjectWorkspace } from "@/components/projects/production-project-workspace";
import { ProjectWorkspaceHeader } from "@/components/projects/project-workspace-header";
import { ProjectWorkspaceTabs } from "@/components/projects/project-workspace-tabs";
import { ProjectWorkflow } from "@/components/projects/project-workflow";

export function generateStaticParams() {
  return projects.map((project) => ({ projectId: project.id }));
}

export async function generateMetadata({ params }: { params: Promise<{ projectId: string }> }): Promise<Metadata> {
  const { projectId } = await params;
  const project = getProject(projectId);
  return project ? { title: project.name, description: `${project.projectNumber} demo project workspace for ${project.client}.`, openGraph: { images: [] }, twitter: { images: [] } } : { title: "Project Workspace" };
}

export default async function WorkspaceLayout({ children, params }: { children: React.ReactNode; params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  const demoProject = getProject(projectId);
  if (!demoProject) return <ProductionProjectWorkspace projectId={projectId} />;
  const details = getProjectDetails(projectId);
  return <div className="mx-auto max-w-[1500px] space-y-5"><ProjectWorkspaceHeader project={demoProject} /><div className="overflow-x-auto"><ProjectWorkflow stages={details.workflow} /></div><div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_10px_30px_rgba(15,23,42,.06)]"><ProjectWorkspaceTabs projectId={projectId} /><div className="bg-slate-50/35 p-4 sm:p-6">{children}</div></div></div>;
}
