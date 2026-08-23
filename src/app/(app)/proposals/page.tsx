import { ProposalDirectory } from "@/components/proposals/proposal-directory";
import { proposals, proposalSummary } from "@/data";
export default function Page() {
  return <ProposalDirectory items={proposals} summary={proposalSummary} />;
}
