import type { ProjectStatusCode } from "@/lib/projects";
import { projectStatusTone } from "@/lib/project-list-presentation";
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
  const tone = projectStatusTone(status, archived);
  return <span className={cn(
    "inline-flex whitespace-nowrap rounded-full border px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide",
    tone === "slate" && "border-slate-200 bg-slate-100 text-slate-600",
    tone === "green" && "border-emerald-200 bg-emerald-50 text-emerald-700",
    tone === "amber" && "border-amber-200 bg-amber-50 text-amber-700",
    tone === "purple" && "border-violet-200 bg-violet-50 text-violet-700",
    tone === "blue" && "border-blue-200 bg-blue-50 text-blue-700",
  )}>{archived ? "Archived" : labels[status]}</span>;
}
