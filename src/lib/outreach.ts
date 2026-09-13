import { apiRequest } from "@/lib/api-client";

export type OutreachContactChoice = { id: number; name: string; title: string; email: string; is_primary: boolean };
export type OutreachCandidateChoice = { id: number; company_name: string; contacts: OutreachContactChoice[] };
export type DeliveryAttempt = { id: number; sequence: number; status: "pending" | "succeeded" | "failed"; safe_error_message: string };
export type OutreachMessageSummary = { id: number; sequence: number; attempts: DeliveryAttempt[] };
export type OutreachRecipient = { id: number; candidate_id: number; company_name: string; contact_name: string; email: string; status: "prepared" | "cancelled" | "invited"; messages: OutreachMessageSummary[] };
export type DeliveryReadiness = { ready: boolean; blockers: { code: string; label: string }[] };
export type OutreachBatch = { id: number; sequence: number; status: string; recipients: OutreachRecipient[]; send_approved: boolean; delivery_readiness: DeliveryReadiness };
export type OutreachCampaign = { id: number; status: string; batches: OutreachBatch[] };
export type OutreachTrade = { scope_package_id: number; scope_version_id: number; scope_version: number; trade: string; approved_count: number; approved_candidates: OutreachCandidateChoice[]; campaign: OutreachCampaign | null };
export type OutreachWorkspace = { trades: OutreachTrade[] };
export type RFQPreview = { template_version: number; source_scope_version_id: number; subject: string; body: string; inclusions: string[]; exclusions: string[]; clarifications: string[]; bid_deadline: string | null; questions_deadline: string | null };

function base(slug: string, projectId: number) {
  return `/organizations/${encodeURIComponent(slug)}/projects/${projectId}`;
}

export const outreachApi = {
  workspace(slug: string, projectId: number, signal?: AbortSignal) {
    return apiRequest<OutreachWorkspace>(`${base(slug, projectId)}/outreach/`, { signal });
  },
  createCampaign(slug: string, projectId: number, scopePackageId: number, scopeVersionId: number) {
    return apiRequest<{ id: number; scope_version_id: number }>(`${base(slug, projectId)}/outreach-campaigns/`, {
      method: "POST", body: JSON.stringify({ scope_package_id: scopePackageId, scope_version_id: scopeVersionId }),
    });
  },
  createBatch(slug: string, projectId: number, campaignId: number, sequence: number) {
    return apiRequest<{ id: number; sequence: number }>(`${base(slug, projectId)}/outreach-campaigns/${campaignId}/batches/`, {
      method: "POST", body: JSON.stringify({ sequence }),
    });
  },
  addRecipient(slug: string, projectId: number, batchId: number, candidateId: number, contactId: number) {
    return apiRequest<{ id: number; status: string }>(`${base(slug, projectId)}/outreach-batches/${batchId}/recipients/`, {
      method: "POST", body: JSON.stringify({ candidate_id: candidateId, contact_id: contactId }),
    });
  },
  preview(slug: string, projectId: number, campaignId: number) {
    return apiRequest<RFQPreview>(`${base(slug, projectId)}/outreach-campaigns/${campaignId}/rfq-preview/`);
  },
  deliveryAction(slug: string, projectId: number, batchId: number, action: "approve" | "prepare" | "send") {
    return apiRequest<unknown>(`${base(slug, projectId)}/outreach-batches/${batchId}/delivery/${action}/`, { method: "POST", body: "{}" });
  },
  retryMessage(slug: string, projectId: number, messageId: number) {
    return apiRequest<unknown>(`${base(slug, projectId)}/outreach-messages/${messageId}/retry/`, { method: "POST", body: "{}" });
  },
};
