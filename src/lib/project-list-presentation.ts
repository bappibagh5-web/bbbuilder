import type { ProjectStatusCode } from "./projects.ts";

export function projectPortfolioCounts(projects: Array<{ is_active: boolean }>) {
  const active = projects.filter((project) => project.is_active).length;
  return { total: projects.length, active, archived: projects.length - active };
}

export function projectStatusTone(status: ProjectStatusCode, archived = false) {
  if (archived) return "slate" as const;
  if (status === "awarded") return "green" as const;
  if (["human_scope_review", "human_award_review"].includes(status)) return "amber" as const;
  if (status === "ai_analysis") return "purple" as const;
  return "blue" as const;
}
