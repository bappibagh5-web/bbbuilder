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
  coordination_required: boolean;
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

export type ScopeCoveragePreviewSource = {
  snapshot_provenance_id: number;
  document_id: number;
  document_title: string;
  document_type: string;
  discipline: string;
  document_revision_id: number;
  revision_label: string;
  page_number: number;
  sheet_number: string;
  evidence_excerpt: string;
  visual_evidence_description: string;
};
export type ScopeCoveragePreviewItem = {
  item_key: string;
  item_type: string;
  responsibility: string;
  coordination_required: boolean;
  title: string;
  description: string;
  approved_entry_ids: number[];
  provenance: ScopeCoveragePreviewSource[];
};
export type ScopeCoveragePreview = {
  source_snapshot_id: number;
  source_snapshot_version: number;
  approval_id: number;
  taxonomy_version: number;
  plan_fingerprint: string;
  total_approved_entries: number;
  proposed_package_count: number;
  proposed_scope_item_count: number;
  project_wide_requirement_count: number;
  total_requirement_count: number;
  mapped_entry_count: number;
  unmapped_entry_count: number;
  non_scope_informational_count: number;
  source_coverage_percent: number;
  unclear_responsibility_count: number;
  coordination_entry_count: number;
  duplicate_obligations_consolidated: number;
  bundled_findings_split: number;
  non_actionable_clauses_removed: number;
  passive_fire_items_removed_from_sprinklers: number;
  trade_assignments_refined: number;
  responsibility_counts: Record<string, number>;
  responsibility_explicit_count: number;
  responsibility_not_stated_count: number;
  external_responsibility_count: number;
  current_generation_package_count: number;
  current_generation_scope_item_count: number;
  new_package_names: string[];
  historical_packages_no_longer_supported: string[];
  packages: Array<{
    trade_key: string;
    name: string;
    scope_item_count: number;
    approved_entry_count: number;
    responsibility_counts: Record<string, number>;
    responsibility_explicit_count: number;
    responsibility_not_stated_count: number;
    source_document_count: number;
    source_page_count: number;
    items: ScopeCoveragePreviewItem[];
  }>;
  project_wide_requirements: {
    trade_key: string;
    name: string;
    scope_item_count: number;
    approved_entry_count: number;
    responsibility_counts: Record<string, number>;
    responsibility_explicit_count: number;
    responsibility_not_stated_count: number;
    source_document_count: number;
    source_page_count: number;
    items: ScopeCoveragePreviewItem[];
  };
  expected_scope_coverage: Array<{
    trade_key: string;
    name: string;
    status: "found" | "limited" | "not_found";
    scope_item_count: number;
  }>;
  coordination_groups: Array<Record<string, unknown>>;
  ambiguous_items: Array<Record<string, unknown>>;
  unmapped_items: Array<Record<string, unknown>>;
  non_scope_informational_items: Array<Record<string, unknown>>;
};

export type ScopePackageEdit = Pick<
  ScopePackageVersion,
  "title" | "description" | "inclusions" | "exclusions" | "clarifications"
>;

function projectPath(slug: string, projectId: string | number) {
  return `/organizations/${encodeURIComponent(slug)}/projects/${encodeURIComponent(String(projectId))}/scope-packages`;
}

export const scopePackagesApi = {
  preview(slug: string, projectId: string | number, signal?: AbortSignal) {
    const base = `/organizations/${encodeURIComponent(slug)}/projects/${encodeURIComponent(String(projectId))}`;
    return apiRequest<ScopeCoveragePreview>(`${base}/scope-coverage-preview/`, { signal });
  },
  list(slug: string, projectId: string | number, signal?: AbortSignal, includeHistory = false) {
    const query = includeHistory ? "?include_history=true" : "";
    return apiRequest<ScopePackage[]>(`${projectPath(slug, projectId)}/${query}`, { signal });
  },
  generate(slug: string, projectId: string | number, preview: ScopeCoveragePreview) {
    return apiRequest<{
      created_count: number;
      existing_count: number;
      package_count: number;
      scope_item_count: number;
      project_wide_requirement_count: number;
      source_snapshot_version: number;
      plan_fingerprint: string;
    }>(
      `${projectPath(slug, projectId)}/generate/`,
      {
        method: "POST",
        body: JSON.stringify({
          confirmed: true,
          expected_plan_fingerprint: preview.plan_fingerprint,
          expected_project_information_version: preview.source_snapshot_version,
        }),
      },
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
