"use client";

import { useState } from "react";
import { Activity } from "lucide-react";
import type { GlobalActivityItem } from "@/data/global-activity";
import { formatDateTime } from "@/lib/utils";
import { Card } from "./ui/card";

export function ActivityDirectory({ items }: { items: GlobalActivityItem[] }) {
  const [project, setProject] = useState("All projects");
  const [type, setType] = useState("All activity");
  const projects = [...new Set(items.map((item) => item.projectName))];
  const types = [...new Set(items.map((item) => item.type))];
  const visible = items.filter(
    (item) =>
      (project === "All projects" || item.projectName === project) &&
      (type === "All activity" || item.type === type),
  );
  return (
    <Card className="mt-6 overflow-hidden">
      <div className="flex flex-col gap-3 border-b p-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="font-semibold text-slate-900">Workspace Activity</h2>
          <p className="mt-1 text-xs text-slate-500">
            A unified fictional audit trail for the completed demo workflow.
          </p>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="text-xs font-medium text-slate-600">
            Project
            <select
              value={project}
              onChange={(event) => setProject(event.target.value)}
              className="mt-1 block h-10 w-full rounded-lg border bg-white px-3 text-sm"
            >
              <option>All projects</option>
              {projects.map((name) => (
                <option key={name}>{name}</option>
              ))}
            </select>
          </label>
          <label className="text-xs font-medium text-slate-600">
            Activity type
            <select
              value={type}
              onChange={(event) => setType(event.target.value)}
              className="mt-1 block h-10 w-full rounded-lg border bg-white px-3 text-sm"
            >
              <option>All activity</option>
              {types.map((name) => (
                <option key={name}>{name}</option>
              ))}
            </select>
          </label>
        </div>
      </div>
      {visible.length ? (
        <ul className="divide-y">
          {visible.map((item) => (
            <li
              key={item.id}
              className="grid gap-3 px-4 py-4 sm:grid-cols-[40px_minmax(0,1fr)_auto] sm:items-center"
            >
              <span className="grid h-10 w-10 place-items-center rounded-lg bg-slate-100 text-slate-600">
                <Activity className="h-4 w-4" />
              </span>
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-900">
                  {item.title}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  {item.projectName} · {item.actor}
                </p>
              </div>
              <div className="sm:text-right">
                <span className="inline-flex rounded-md bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-700">
                  {item.type}
                </span>
                <time
                  className="mt-1 block text-xs text-slate-500"
                  dateTime={item.occurredAt}
                >
                  {formatDateTime(item.occurredAt)}
                </time>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <div className="p-10 text-center">
          <p className="font-medium text-slate-800">
            No activity matches these filters.
          </p>
          <p className="mt-1 text-sm text-slate-500">
            Adjust the project or activity type.
          </p>
        </div>
      )}
    </Card>
  );
}
