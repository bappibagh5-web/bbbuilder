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
  return (
    <BidComparison
      project={getProject(projectId)!}
      tradeNames={comparisonTrades}
      initialLevels={
        projectId === "retail-store-coquitlam" ? electricalLeveledBids : []
      }
      bids={bidSubmissions}
      companies={subcontractors}
    />
  );
}
