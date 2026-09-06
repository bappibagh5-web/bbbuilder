"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, BarChart3, Bot, FileChartColumn, Files, Gavel, LayoutDashboard, Send, Users, Wrench } from "lucide-react";
import { projectWorkflowHref, projectWorkflowNavigation } from "@/lib/project-workflow-navigation";
import { cn } from "@/lib/utils";

const icons = {
  "": LayoutDashboard,
  documents: Files,
  "ai-review": Bot,
  scopes: Wrench,
  contractors: Users,
  outreach: Send,
  bids: Gavel,
  comparisons: BarChart3,
  proposal: FileChartColumn,
  activity: Activity,
} as const;

export function ProjectWorkspaceTabs({ projectId }: { projectId: string }) {
  const path = usePathname();
  return (
    <nav aria-label="Project workflow" className="overflow-x-auto border-b border-slate-200 bg-slate-50/80 px-2 py-2 [scrollbar-width:thin] sm:px-3">
      <div className="flex min-w-max gap-1">
        {projectWorkflowNavigation.map((tab) => {
          const href = projectWorkflowHref(projectId, tab.slug);
          const active = path === href;
          const Icon = icons[tab.slug];
          return (
            <Link
              key={tab.label}
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "inline-flex min-h-10 items-center gap-2 rounded-lg border px-3 py-2 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-blue-600",
                active
                  ? "border-blue-200 bg-white text-blue-800 shadow-sm"
                  : "border-transparent text-slate-500 hover:border-slate-200 hover:bg-white/80 hover:text-slate-800",
              )}
            >
              <Icon className={cn("h-4 w-4", active ? "text-blue-700" : "text-slate-400")} />
              {tab.label}
              {"badge" in tab && tab.badge && <span className="rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-violet-700">{tab.badge}</span>}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
