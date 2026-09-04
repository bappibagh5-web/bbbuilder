import { apiRequest } from "@/lib/api-client";

export type ProjectStatusCode =
  | "draft"
  | "documents_uploaded"
  | "ai_analysis"
  | "human_scope_review"
  | "trade_packages_ready"
  | "contractor_discovery"
  | "outreach_active"
  | "bid_collection"
  | "bid_leveling"
  | "human_award_review"
  | "final_proposal"
  | "awarded";

export type ProjectTypeCode = "retail" | "restaurant" | "office" | "commercial" | "other";
export type AreaUnitCode = "sf" | "m2";

export type ProductionProject = {
  id: number;
  organization: string;
  project_number: string;
  name: string;
  status: ProjectStatusCode;
  status_label: string;
  created_by: string;
  client_name: string;
  site_address_line_1: string;
  site_address_line_2: string;
  city: string;
  province_state: string;
  postal_zip_code: string;
  country: string;
  project_timezone: string;
  project_type: ProjectTypeCode;
  project_type_label: string;
  description: string;
  estimated_area: string | null;
  area_unit: AreaUnitCode;
  area_unit_label: string;
  bid_deadline: string | null;
  questions_deadline: string | null;
  site_visit_date: string | null;
  planned_start_date: string | null;
  substantial_completion_date: string | null;
  opening_or_handover_date: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type ProjectWritePayload = {
  project_number: string;
  name: string;
  project_timezone: string;
  client_name?: string;
  project_type?: ProjectTypeCode;
  description?: string;
  site_address_line_1?: string;
  site_address_line_2?: string;
  city?: string;
  province_state?: string;
  postal_zip_code?: string;
  country?: string;
  estimated_area?: string | null;
  area_unit?: AreaUnitCode;
  bid_deadline?: string | null;
  questions_deadline?: string | null;
  site_visit_date?: string | null;
  planned_start_date?: string | null;
  substantial_completion_date?: string | null;
  opening_or_handover_date?: string | null;
};

export type PaginatedProjects = {
  count: number;
  next: string | null;
  previous: string | null;
  results: ProductionProject[];
};

export type ProjectAuditEvent = {
  id: number;
  action_code: string;
  target_type: string;
  target_id: string;
  actor: string;
  occurred_at: string;
};

export type PaginatedProjectAuditEvents = {
  count: number;
  next: string | null;
  previous: string | null;
  results: ProjectAuditEvent[];
};

function organizationPath(slug: string) {
  return `/organizations/${encodeURIComponent(slug)}/projects`;
}

export const projectsApi = {
  list(slug: string, page = 1, signal?: AbortSignal) {
    return apiRequest<PaginatedProjects>(`${organizationPath(slug)}/?page=${page}`, { signal });
  },
  create(slug: string, payload: ProjectWritePayload) {
    return apiRequest<ProductionProject>(`${organizationPath(slug)}/`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  retrieve(slug: string, projectId: string, signal?: AbortSignal) {
    return apiRequest<ProductionProject>(
      `${organizationPath(slug)}/${encodeURIComponent(projectId)}/`,
      { signal },
    );
  },
  update(slug: string, projectId: string | number, payload: Partial<ProjectWritePayload> & { is_active?: boolean }) {
    return apiRequest<ProductionProject>(
      `${organizationPath(slug)}/${encodeURIComponent(String(projectId))}/`,
      { method: "PATCH", body: JSON.stringify(payload) },
    );
  },
  auditEvents(slug: string, projectId: string | number, page = 1, signal?: AbortSignal) {
    return apiRequest<PaginatedProjectAuditEvents>(
      `${organizationPath(slug)}/${encodeURIComponent(String(projectId))}/audit-events/?page=${page}`,
      { signal },
    );
  },
};
