import { getProject, primaryProposal } from "@/data";
import { ProposalBuilder } from "@/components/proposals/proposal-builder";
export default async function Page({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return (
    <ProposalBuilder
      project={getProject(projectId)!}
      initial={primaryProposal}
    />
  );
}
