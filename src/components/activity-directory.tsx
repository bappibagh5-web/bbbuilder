"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Activity, ChevronLeft, ChevronRight } from "lucide-react";
import { OrganizationAccessState } from "@/components/organizations/organization-access-state";
import { useOrganization } from "@/components/organizations/organization-provider";
import { Card } from "@/components/ui/card";
import { getOrganizationActivity, type ActivityDirectoryResponse } from "@/lib/activity-directory";
import { formatDateTime } from "@/lib/utils";

export function ActivityDirectory() {
  const { memberships, activeMembership } = useOrganization();
  const [project, setProject] = useState("");
  const [family, setFamily] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<ActivityDirectoryResponse | null>(null);
  const [loadedSlug, setLoadedSlug] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!activeMembership) return;
    const controller = new AbortController();
    const query = new URLSearchParams({ page: String(page), page_size: "25" });
    if (project) query.set("project", project);
    if (family) query.set("family", family);
    const slug = activeMembership.organization.slug;
    getOrganizationActivity(slug, query, controller.signal)
      .then((response) => { setData(response); setLoadedSlug(slug); })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Activity could not be loaded.");
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [activeMembership, family, page, project]);

  if (!activeMembership) return <OrganizationAccessState multiple={memberships.length > 1} />;
  const awaitingOrganization = loadedSlug !== activeMembership.organization.slug;
  const filtered = Boolean(project || family);
  const changeFilter = (setter: (value: string) => void, value: string) => {
    setLoading(true);
    setError("");
    setter(value);
    setPage(1);
  };

  return (
    <Card className="mt-6 overflow-hidden">
      <div className="flex flex-col gap-3 border-b p-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="font-semibold text-slate-900">Workspace Activity</h2>
          <p className="mt-1 text-xs text-slate-500">A real, organization-wide history of project and procurement work.</p>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="text-xs font-medium text-slate-600">Project
            <select aria-label="Project" value={project} onChange={(event) => changeFilter(setProject, event.target.value)} className="mt-1 block h-10 w-full rounded-lg border bg-white px-3 text-sm">
              <option value="">All projects</option>
              {(data?.filters.projects ?? []).map((item) => <option key={item.id} value={item.id}>{item.project_number} · {item.name}</option>)}
            </select>
          </label>
          <label className="text-xs font-medium text-slate-600">Activity type
            <select aria-label="Activity type" value={family} onChange={(event) => changeFilter(setFamily, event.target.value)} className="mt-1 block h-10 w-full rounded-lg border bg-white px-3 text-sm">
              <option value="">All activity</option>
              {(data?.filters.families ?? []).map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
          </label>
        </div>
      </div>
      {error ? <State title="Activity unavailable" detail={error} /> : (loading && !data) || awaitingOrganization ? <State title="Loading activity…" /> : !data?.results.length ? <State title={filtered ? "No activity matches these filters" : "No activity recorded yet"} detail={filtered ? "Adjust the project or activity type." : "New project work will appear here."} /> : (
        <>
          <ul className={`divide-y ${loading ? "opacity-60" : ""}`}>
            {data.results.map((item) => (
              <li key={item.id} className="grid gap-3 px-4 py-4 sm:grid-cols-[40px_minmax(0,1fr)_auto] sm:items-center">
                <span className="grid h-10 w-10 place-items-center rounded-lg bg-blue-50 text-blue-700"><Activity className="h-4 w-4" /></span>
                <div className="min-w-0">
                  {item.route ? <Link href={item.route} className="text-sm font-medium text-slate-900 hover:text-blue-700 hover:underline">{item.label}</Link> : <p className="text-sm font-medium text-slate-900">{item.label}</p>}
                  <p className="mt-1 text-xs text-slate-500">{item.project ? `${item.project.project_number} · ${item.project.name} · ` : ""}{item.actor}</p>
                </div>
                <div className="sm:text-right"><span className="inline-flex rounded-md bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-700">{item.family_label}</span><time className="mt-1 block text-xs text-slate-500" dateTime={item.timestamp}>{formatDateTime(item.timestamp)}</time></div>
              </li>
            ))}
          </ul>
          <div className="flex items-center justify-between border-t px-4 py-3 text-sm">
            <span>Page {data.page} · {data.count} events</span>
            <div className="flex gap-2"><button aria-label="Previous page" disabled={!data.previous || loading} onClick={() => { setLoading(true); setError(""); setPage((value) => Math.max(1, value - 1)); }} className="rounded border p-2 disabled:opacity-40"><ChevronLeft className="h-4 w-4" /></button><button aria-label="Next page" disabled={!data.next || loading} onClick={() => { setLoading(true); setError(""); setPage((value) => value + 1); }} className="rounded border p-2 disabled:opacity-40"><ChevronRight className="h-4 w-4" /></button></div>
          </div>
        </>
      )}
    </Card>
  );
}

function State({ title, detail }: { title: string; detail?: string }) {
  return <div className="flex min-h-56 flex-col items-center justify-center p-8 text-center"><Activity className="h-8 w-8 text-slate-400" /><h2 className="mt-3 font-semibold">{title}</h2>{detail && <p className="mt-1 text-sm text-slate-500">{detail}</p>}</div>;
}
