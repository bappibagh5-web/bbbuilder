import { apiRequest } from "@/lib/api-client";

export type ScopePackageStatus = "draft" | "ready";
export type ScopeItemSource = {
  id: number;
  snapshot_entry: number;
  finding_id: number;
  document_id: number;
  document_title: string;
  document_revision: number;
  revision_label: string;
  page_number: number;
  sheet_number: string;
  evidence_excerpt: string;
};
export type ScopeItem = {
  id: number;
  item_key: string;
  item_type: string;
  responsibility:
    | "supply_install"
    | "install_only"
    | "owner_supplied"
    | "landlord_supplied"
    | "existing_to_remain"
    | "relocate_reuse"
    | "by_others"
    | "unclear";
  title: string;
  description: string;
  sequence: number;
  sources: ScopeItemSource[];
};
export type ScopePackageSource = {
  id: number;
  snapshot_entry: number;
  finding_id: number;
  subject: string;
  category: string;
  provenance_count: number;
};
export type ScopePackageVersion = {
  id: number;
  version: number;
  title: string;
  description: string;
  inclusions: string[];
  exclusions: string[];
  clarifications: string[];
  status: ScopePackageStatus;
  created_by: string;
  created_at: string;
  sources: ScopePackageSource[];
  scope_items: ScopeItem[];
};
export type ScopePackage = {
  id: number;
  project: number;
  trade_key: string;
  trade_category: string;
  generation_rule_version: number;
  lifecycle: "active" | "superseded";
  source_snapshot: number;
  source_snapshot_version: number;
  source_approval_id: number;
  current_version: ScopePackageVersion;
  versions: ScopePackageVersion[];
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
};

export type ScopePackageEdit = Pick<
  ScopePackageVersion,
  "title" | "description" | "inclusions" | "exclusions" | "clarifications"
>;

function projectPath(slug: string, projectId: string | number) {
  return `/organizations/${encodeURIComponent(slug)}/projects/${encodeURIComponent(String(projectId))}/scope-packages`;
}

export const scopePackagesApi = {
  list(slug: string, projectId: string | number, signal?: AbortSignal, includeHistory = false) {
    const query = includeHistory ? "?include_history=true" : "";
    return apiRequest<ScopePackage[]>(`${projectPath(slug, projectId)}/${query}`, { signal });
  },
  generate(slug: string, projectId: string | number, snapshotId: number) {
    return apiRequest<{ created_count: number; existing_count: number; packages: ScopePackage[] }>(
      `${projectPath(slug, projectId)}/generate/`,
      { method: "POST", body: JSON.stringify({ snapshot_id: snapshotId }) },
    );
  },
  update(slug: string, projectId: string | number, packageId: number, values: ScopePackageEdit) {
    return apiRequest<ScopePackage>(`${projectPath(slug, projectId)}/${packageId}/`, {
      method: "PATCH",
      body: JSON.stringify(values),
    });
  },
  markReady(slug: string, projectId: string | number, packageId: number) {
    return apiRequest<ScopePackage>(`${projectPath(slug, projectId)}/${packageId}/ready/`, {
      method: "POST",
      body: JSON.stringify({}),
    });
  },
};
