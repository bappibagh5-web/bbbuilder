import Link from "next/link";
import type { Project } from "@/types";
import { formatDate } from "@/lib/utils";
import { StatusBadge } from "./status-badge";
import { ProgressBar } from "./progress-bar";
import { Card } from "./ui/card";
export function ProjectTable({ projects }: { projects: Project[] }) {
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between border-b px-5 py-4">
        <div>
          <h2 className="font-semibold text-slate-900">Active Projects</h2>
          <p className="mt-0.5 text-xs text-slate-500">
            Current preconstruction pipeline
          </p>
        </div>
        <span className="rounded-md bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">
          {projects.length} projects
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[980px] text-left">
          <caption className="sr-only">
            Active bid projects and their progress
          </caption>
          <thead className="bg-slate-50/80 text-[11px] uppercase tracking-wider text-slate-500">
            <tr>
              {[
                "Project",
                "Location",
                "Bid deadline",
                "Trades",
                "Bid submissions",
                "Stage",
                "Progress",
                "Action",
              ].map((h) => (
                <th key={h} className="px-5 py-3 font-semibold">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y">
            {projects.map((project) => (
              <tr
                key={project.id}
                className="transition-colors hover:bg-slate-50/70"
              >
                <td className="min-w-64 px-5 py-4">
                  <Link
                    href={`/projects/${project.id}`}
                    className="font-medium text-slate-900 hover:text-blue-700 hover:underline focus-visible:outline-2 focus-visible:outline-blue-700"
                  >
                    {project.name}
                  </Link>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {project.projectNumber} · {project.client}
                  </p>
                </td>
                <td className="whitespace-nowrap px-5 py-4 text-sm text-slate-600">
                  {project.city}, {project.province}
                </td>
                <td className="whitespace-nowrap px-5 py-4 text-sm font-medium text-slate-700">
                  {formatDate(project.bidDeadline)}
                </td>
                <td className="px-5 py-4 text-right text-sm tabular-nums text-slate-600">
                  {project.requiredTrades}
                </td>
                <td className="px-5 py-4 text-right text-sm tabular-nums text-slate-600">
                  {project.bidsReceived}
                </td>
                <td className="px-5 py-4">
                  <StatusBadge status={project.status} />
                </td>
                <td className="min-w-32 px-5 py-4">
                  <ProgressBar value={project.progress} />
                </td>
                <td className="px-5 py-4">
                  <Link
                    href={`/projects/${project.id}`}
                    className="whitespace-nowrap text-sm font-semibold text-blue-700 hover:underline"
                  >
                    Open Project
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
