"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { projectWorkflowHref, projectWorkflowNavigation } from "@/lib/project-workflow-navigation";
import { cn } from "@/lib/utils";

export function ProjectWorkspaceTabs({ projectId }: { projectId: string }) {
  const path = usePathname();
  return (
    <nav aria-label="Project workflow" className="overflow-x-auto border-b">
      <div className="flex min-w-max">
        {projectWorkflowNavigation.map((tab) => {
          const href = projectWorkflowHref(projectId, tab.slug);
          const active = path === href;
          return (
            <Link
              key={tab.label}
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "border-b-2 px-4 py-3 text-sm font-medium",
                active
                  ? "border-primary text-primary"
                  : "border-transparent text-slate-500 hover:text-slate-800",
              )}
            >
              {tab.label}
              {"badge" in tab && tab.badge && <span className="ml-2 rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-semibold text-blue-700">{tab.badge}</span>}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
