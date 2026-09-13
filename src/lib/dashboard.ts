import { apiRequest } from "./api-client";

export type DashboardProject = {
  id: number;
  project_number: string;
  name: string;
  status: string;
  status_label: string;
  city: string;
  province_state: string;
  is_active: boolean;
};

export type DashboardProjectSummary = {
  project: DashboardProject;
  active_document_count: number;
  reviewed_document_count: number;
  review_mode: "project_set" | "document";
  project_review: {
    run_id: number;
    document_count: number;
    page_count: number;
    current: boolean;
  } | null;
  review: {
    total: number;
    ai_handled: number;
    reviewed_by_user: number;
    needs_attention: number;
    conflicts: number;
    complete: boolean;
  };
  approved_snapshot: { version: number; approver: string; approved_at: string } | null;
  approved_snapshot_count: number;
  needs_attention: boolean;
};

export type DashboardSummary = {
  summary: {
    active_projects: number;
    needs_attention: number;
    project_reviews_complete: number;
    approved_information: number;
  };
  projects: DashboardProjectSummary[];
};

export type DashboardActivity = {
  id: number;
  action_code: string;
  target_type: string;
  target_id: string;
  actor: string;
  occurred_at: string;
  project_id: number;
  project_name: string;
};

function dashboardPath(slug: string) {
  return `/organizations/${encodeURIComponent(slug)}/dashboard`;
}

export const dashboardApi = {
  summary(slug: string, signal?: AbortSignal) {
    return apiRequest<DashboardSummary>(`${dashboardPath(slug)}/`, { signal });
  },
  activity(slug: string, signal?: AbortSignal) {
    return apiRequest<{ results: DashboardActivity[] }>(`${dashboardPath(slug)}/activity/`, {
      signal,
    });
  },
};
