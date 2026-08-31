import type { ProjectStatusCode } from "@/lib/projects";
import { cn } from "@/lib/utils";

const labels: Record<ProjectStatusCode, string> = {
  draft: "Draft", documents_uploaded: "Documents Uploaded", ai_analysis: "AI Analysis",
  human_scope_review: "Human Scope Review", trade_packages_ready: "Trade Packages Ready",
  contractor_discovery: "Contractor Discovery", outreach_active: "Outreach Active",
  bid_collection: "Bid Collection", bid_leveling: "Bid Leveling",
  human_award_review: "Human Award Review", final_proposal: "Final Proposal", awarded: "Awarded",
};

export const projectStatusOptions = Object.entries(labels) as [ProjectStatusCode, string][];

export function ProductionProjectStatus({ status, archived = false }: { status: ProjectStatusCode; archived?: boolean }) {
  return <span className={cn("inline-flex whitespace-nowrap rounded-md px-2 py-1 text-xs font-semibold", archived ? "bg-slate-200 text-slate-700" : status === "awarded" ? "bg-emerald-50 text-emerald-700" : "bg-blue-50 text-blue-700")}>{archived ? "Archived" : labels[status]}</span>;
}
