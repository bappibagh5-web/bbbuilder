import {
  getProject,
  bidSubmissions,
  bidInboxSummary,
  subcontractors,
} from "@/data";
import { BidInbox } from "@/components/bids/bid-inbox";
export default async function Page({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  const demoProject = getProject(projectId);
  if (!demoProject) return null;
  return (
    <BidInbox
      project={demoProject}
      initialBids={projectId === "retail-store-coquitlam" ? bidSubmissions : []}
      companies={subcontractors}
      summary={bidInboxSummary}
    />
  );
}
