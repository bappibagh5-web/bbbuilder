import {
  getProject,
  discoveryTrades,
  electricalCandidates,
  subcontractors,
  procurementStatuses,
} from "@/data";
import { ContractorDiscovery } from "@/components/contractors/contractor-discovery";
export default async function Page({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return (
    <ContractorDiscovery
      project={getProject(projectId)!}
      trades={discoveryTrades}
      initialCandidates={
        projectId === "retail-store-coquitlam" ? electricalCandidates : []
      }
      companies={subcontractors}
      procurement={procurementStatuses}
    />
  );
}
