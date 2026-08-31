import {
  getProject,
  comparisonTrades,
  electricalLeveledBids,
  bidSubmissions,
  subcontractors,
} from "@/data";
import { BidComparison } from "@/components/comparisons/bid-comparison";
export default async function Page({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  const demoProject = getProject(projectId);
  if (!demoProject) return null;
  return (
    <BidComparison
      project={demoProject}
      tradeNames={comparisonTrades}
      initialLevels={
        projectId === "retail-store-coquitlam" ? electricalLeveledBids : []
      }
      bids={bidSubmissions}
      companies={subcontractors}
    />
  );
}
