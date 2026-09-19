import { apiRequest } from "@/lib/api-client";

export type EstimateVersionSummary = {
  id: number;
  version: number;
  status: "draft";
  status_label: string;
  supersedes_id: number | null;
  created_by: string;
  created_at: string;
};

export type ProposalVersionSummary = EstimateVersionSummary & {
  estimate_version_id: number;
  estimate_version: number;
};

export type ProposalWorkspace = {
  project: { id: number; name: string; project_number: string; client_name: string };
  can_edit: boolean;
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
};
