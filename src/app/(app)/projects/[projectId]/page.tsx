import { getProject, getProjectDetails } from "@/data";
import { ProjectOverview } from "@/components/projects/project-overview";

export default async function Page({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  const demoProject = getProject(projectId);
  return demoProject ? <ProjectOverview project={demoProject} details={getProjectDetails(projectId)} /> : null;
}
