"use client";

import { useEffect, useState } from "react";
import { Activity, AlertCircle, UserRound } from "lucide-react";
import type { OrganizationMembership } from "@/lib/auth";
import { ApiError } from "@/lib/api-client";
import {
  projectsApi,
  type ProductionProject,
  type ProjectAuditEvent,
} from "@/lib/projects";
import { Card } from "@/components/ui/card";

const actionLabels: Record<string, string> = {
  "project.created": "Project created",
  "project.updated": "Project details updated",
  "project.archived": "Project archived",
  "project.reactivated": "Project reactivated",
  "project.status_changed": "Project status changed",
  "project_contact.created": "Project contact created",
  "project_contact.updated": "Project contact updated",
  "project_contact.deactivated": "Project contact deactivated",
  "project_contact.reactivated": "Project contact reactivated",
  "file.uploaded": "Project file uploaded",
  "document.created": "Document created",
  "document.updated": "Document details updated",
  "document.archived": "Document archived",
  "document.reactivated": "Document reactivated",
  "document_revision.created": "Document revision created",
  "document.current_revision_changed": "Current document revision changed",
  "processing.requested": "Source verification requested",
  "pdf_indexing.requested": "PDF indexing requested",
  "analysis.requested": "AI analysis requested",
  "analysis.completed": "AI analysis completed",
  "findings.materialized": "Findings prepared for review",
  "finding.accepted": "Finding accepted",
  "finding.edited": "Finding edited and accepted",
  "finding.rejected": "Finding rejected",
  "finding.needs_clarification": "Finding needs clarification",
  "conflict.resolved": "Intelligence conflict resolved",
  "conflict.dismissed": "Intelligence conflict dismissed",
  "intelligence_snapshot.created": "Intelligence snapshot created",
  "intelligence_snapshot.approved": "Intelligence snapshot approved",
  "intelligence_snapshot.approval_blocked_stale": "Stale snapshot approval blocked",
};

function actionLabel(code: string) {
  return actionLabels[code] ?? code.replaceAll("_", " ").replaceAll(".", " · ");
}

function eventTime(value: string, timezone: string) {
  return new Intl.DateTimeFormat("en-CA", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timezone,
  }).format(new Date(value));
}

export function ProductionProjectActivity({
  project,
  membership,
}: {
  project: ProductionProject;
  membership: OrganizationMembership;
}) {
  const [events, setEvents] = useState<ProjectAuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    projectsApi
      .auditEvents(membership.organization.slug, project.id, 1, controller.signal)
      .then((result) => setEvents(result.results))
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(
          reason instanceof ApiError
            ? reason.message
            : "Project activity could not be loaded.",
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [membership.organization.slug, project.id]);

  if (loading) {
    return <ActivityState title="Loading project activity…" detail="Retrieving the latest persistent audit history." />;
  }
  if (error) {
    return <ActivityState title="Project activity unavailable" detail={error} error />;
  }
  if (events.length === 0) {
    return <ActivityState title="No project activity yet" detail="Business workflow events will appear here as this project is used." />;
  }

  return (
    <section aria-labelledby="project-activity-title" className="space-y-4">
      <div>
        <h2 id="project-activity-title" className="text-lg font-semibold text-slate-900">Project Activity</h2>
        <p className="mt-1 text-sm text-slate-500">Read-only business history recorded by the production backend.</p>
      </div>
      <ol className="space-y-3">
        {events.map((event) => (
          <li key={event.id}>
            <Card className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between">
              <div className="flex min-w-0 gap-3">
                <span className="mt-0.5 rounded-lg bg-slate-100 p-2 text-slate-600"><Activity className="h-4 w-4" aria-hidden="true" /></span>
                <div className="min-w-0">
                  <p className="font-medium text-slate-900">{actionLabel(event.action_code)}</p>
                  <p className="mt-1 break-words text-xs text-slate-500">{event.target_type} #{event.target_id}</p>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2 text-xs text-slate-500 sm:text-right">
                <UserRound className="h-3.5 w-3.5" aria-hidden="true" />
                <span>{event.actor}</span>
                <span aria-hidden="true">·</span>
                <time dateTime={event.occurred_at}>{eventTime(event.occurred_at, project.project_timezone)}</time>
              </div>
            </Card>
          </li>
        ))}
      </ol>
    </section>
  );
}

function ActivityState({ title, detail, error = false }: { title: string; detail: string; error?: boolean }) {
  return (
    <section role={error ? "alert" : "status"} className="flex min-h-64 flex-col items-center justify-center rounded-xl border border-dashed bg-white px-6 text-center">
      {error ? <AlertCircle className="h-6 w-6 text-red-500" aria-hidden="true" /> : <Activity className="h-6 w-6 text-slate-400" aria-hidden="true" />}
      <h2 className="mt-3 font-semibold text-slate-900">{title}</h2>
      <p className="mt-1 max-w-lg text-sm leading-6 text-slate-500">{detail}</p>
    </section>
  );
}
