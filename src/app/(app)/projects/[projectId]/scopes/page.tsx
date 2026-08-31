import { getProject, getTradeScopes } from "@/data";
import { ScopeBuilder } from "@/components/scopes/scope-builder";

export default async function Page({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  const demoProject = getProject(projectId);
  return demoProject ? <ScopeBuilder project={demoProject} initialScopes={getTradeScopes(projectId)} /> : null;
}
