import { apiRequest, apiResponse } from "@/lib/api-client";

export type EstimateVersionSummary = {
  id: number;
  version: number;
  status: "draft" | "frozen" | "finalized";
  status_label: string;
  supersedes_id: number | null;
  created_by: string;
  created_at: string;
};

export type ProposalVersionSummary = EstimateVersionSummary & {
  estimate_version_id: number;
  estimate_version: number;
  proposal_number: string; issue_date: string | null; introduction: string; scope_summary: string;
  commercial_notes: string; terms_conditions: string; client_contact_id: number | null; finalized_by: string | null; finalized_at: string | null;
  client_project_snapshot: Record<string, unknown>;
  commercial_snapshot: { currency?: string; pre_tax_amount?: string; tax_amount?: string; total_amount?: string; allowances?: Array<{ description: string; amount: string; currency: string }>; alternates?: Array<{ description: string; direction: string; amount: string; currency: string }>; exclusions?: Array<{ description: string }> };
  pdf_artifact: null | { id: number; filename: string; generated_at: string; version: number; template_version: string };
  pdf_update_available: boolean;
};

export type EstimateCalculation = {
  currency: string | null;
  direct_source_cost: string | null;
  leveling_adjustments: string | null;
  normalized_direct_cost: string | null;
  allowance_impact: string | null;
  included_alternate_impact: string | null;
  commercial_adjustments: string | null;
  pre_tax_subtotal: string | null;
  tax_impact: string | null;
  calculated_estimate_amount: string | null;
  blockers: string[];
  adjustment_breakdown: Array<{
    id: number; category: string; description: string; method: string; basis: string;
    basis_amount: string | null; rate: string | null; calculated_amount: string; currency: string;
  }>;
  rounding: string;
};

export type EstimateVersionDetail = {
  id: number; version: number; status: "draft" | "frozen"; frozen_at: string | null; calculation: EstimateCalculation;
  eligible_selected_reviews: Array<{
    review_id: number; review_version: number; entry_id: number; bid_revision_id: number;
    scope_version_id: number; trade: string; company_id: number; company_name: string;
    base_bid: string | null; currency: string; already_assembled: boolean;
  }>;
  source_lines: Array<{
    id: number; line_type: "source_base_bid" | "m3_leveling"; description: string;
    amount: string; currency: string; direction: "add" | "deduct"; sequence: number;
    review_id: number; comparison_entry_id: number; bid_revision_id: number;
    scope_version_id: number; company_id: number; company_name: string; trade: string;
    source_category: string; leveling_adjustment_id: number | null;
  }>;
  allowances: Array<{ id: number; description: string; amount: string | null; currency: string; treatment: string; sequence: number }>;
  alternates: Array<{ id: number; description: string; direction: string; amount: string | null; currency: string; included_in_estimate: boolean; sequence: number }>;
  exclusions: Array<{ id: number; description: string; sequence: number }>;
  financial_adjustments: Array<{ id: number; category: string; description: string; method: string; basis: string; fixed_amount: string | null; percentage_rate: string | null; calculated_amount: string | null; currency: string; sequence: number }>;
};

export type ProposalWorkspace = {
  project: { id: number; name: string; project_number: string; client_name: string };
  can_edit: boolean;
  client_contacts?: Array<{ id: number; name: string; company: string; email: string }>;
  current_estimate_version: EstimateVersionDetail | null;
  bound_proposal_estimate: null | {
    proposal_version_id: number; estimate_version_id: number; estimate_version: number;
    calculation: EstimateCalculation;
  };
  estimate: null | {
    id: number;
    title: string;
    created_by: string;
    created_at: string;
    versions: EstimateVersionSummary[];
  };
  proposal: null | {
    id: number;
    title: string;
    estimate_id: number;
    client_contact: null | { id: number; name: string; company: string; email: string };
    created_by: string;
    created_at: string;
    versions: ProposalVersionSummary[];
    current_version?: ProposalVersionSummary;
  };
};

function base(slug: string, projectId: number) {
  return `/organizations/${encodeURIComponent(slug)}/projects/${projectId}`;
}

export const proposalsApi = {
  workspace(slug: string, projectId: number, signal?: AbortSignal) {
    return apiRequest<ProposalWorkspace>(`${base(slug, projectId)}/proposal-workspace/`, { signal });
  },
  createEstimate(slug: string, projectId: number) {
    return apiRequest<ProposalWorkspace>(`${base(slug, projectId)}/estimates/`, { method: "POST", body: "{}" });
  },
  createEstimateVersion(slug: string, projectId: number, estimateId: number) {
    return apiRequest<ProposalWorkspace>(`${base(slug, projectId)}/estimates/${estimateId}/versions/`, { method: "POST", body: "{}" });
  },
  createProposal(slug: string, projectId: number, estimateVersionId: number) {
    return apiRequest<ProposalWorkspace>(`${base(slug, projectId)}/proposals/`, {
      method: "POST",
      body: JSON.stringify({ estimate_version_id: estimateVersionId }),
    });
  },
  createProposalVersion(slug: string, projectId: number, proposalId: number, estimateVersionId: number) {
    return apiRequest<ProposalWorkspace>(`${base(slug, projectId)}/proposals/${proposalId}/versions/`, {
      method: "POST",
      body: JSON.stringify({ estimate_version_id: estimateVersionId }),
    });
  },
  assemble(slug: string, projectId: number, estimateVersionId: number, reviewIds: number[]) {
    return apiRequest<ProposalWorkspace>(`${base(slug, projectId)}/estimate-versions/${estimateVersionId}/assemble/`, {
      method: "POST", body: JSON.stringify({ review_ids: reviewIds }),
    });
  },
  addCommercial(slug: string, projectId: number, estimateVersionId: number, kind: "allowances" | "alternates" | "exclusions" | "adjustments", payload: Record<string, unknown>) {
    return apiRequest<ProposalWorkspace>(`${base(slug, projectId)}/estimate-versions/${estimateVersionId}/${kind}/`, {
      method: "POST", body: JSON.stringify(payload),
    });
  },
  updateCommercial(slug: string, projectId: number, estimateVersionId: number, kind: "allowances" | "alternates" | "exclusions" | "adjustments", itemId: number, payload: Record<string, unknown>) {
    return apiRequest<ProposalWorkspace>(`${base(slug, projectId)}/estimate-versions/${estimateVersionId}/${kind}/${itemId}/`, {
      method: "PATCH", body: JSON.stringify(payload),
    });
  },
  updateProposalContent(slug: string, projectId: number, versionId: number, payload: Record<string, unknown>) {
    return apiRequest<ProposalWorkspace>(`${base(slug, projectId)}/proposal-versions/${versionId}/content/`, { method: "PATCH", body: JSON.stringify(payload) });
  },
  finalizeProposal(slug: string, projectId: number, versionId: number) {
    return apiRequest<ProposalWorkspace>(`${base(slug, projectId)}/proposal-versions/${versionId}/finalize/`, { method: "POST", body: "{}" });
  },
  generatePdf(slug: string, projectId: number, versionId: number) {
    return apiRequest<ProposalWorkspace>(`${base(slug, projectId)}/proposal-versions/${versionId}/pdf/`, { method: "POST", body: "{}" });
  },
  async downloadPdf(slug: string, projectId: number, artifactId: number) {
    const response = await apiResponse(`${base(slug, projectId)}/proposal-pdfs/${artifactId}/download/`);
    return response.blob();
  },
};
