import { getProject, primaryProposal } from "@/data";
import { ProposalBuilder } from "@/components/proposals/proposal-builder";
export default async function Page({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  const demoProject = getProject(projectId);
  if (!demoProject) return null;
  return (
    <ProposalBuilder
      project={demoProject}
      initial={primaryProposal}
    />
  );
}
