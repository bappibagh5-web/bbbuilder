import { apiRequest } from "@/lib/api-client";

export type OutreachContactChoice = { id: number; name: string; title: string; email: string; is_primary: boolean };
export type OutreachCandidateChoice = { id: number; company_name: string; contacts: OutreachContactChoice[] };
export type DeliveryAttempt = { id: number; sequence: number; status: "pending" | "succeeded" | "failed" | "uncertain"; safe_error_message: string };
export type OutreachMessageSummary = { id: number; sequence: number; attempts: DeliveryAttempt[]; from_name: string; from_address: string; reply_to: string; to_address: string; subject: string; body: string; template_version: number; scope_version_id: number };
export type OutreachRecipient = { id: number; candidate_id: number; company_name: string; contact_name: string; email: string; status: "prepared" | "cancelled" | "invited"; messages: OutreachMessageSummary[] };
export type DeliveryReadiness = { ready: boolean; blockers: { code: string; label: string }[]; send_approved: boolean };
export type OutreachBatch = { id: number; sequence: number; status: string; recipients: OutreachRecipient[]; send_approved: boolean; delivery_readiness: DeliveryReadiness };
export type OutreachCampaign = { id: number; status: string; batches: OutreachBatch[]; bid_due_local: string; questions_due_local: string; project_timezone: string; setup_version: number };
export type OutreachTrade = { scope_package_id: number; scope_version_id: number; scope_version: number; trade: string; approved_count: number; approved_candidates: OutreachCandidateChoice[]; campaign: OutreachCampaign | null };
export type ProviderStatus = { provider: string; state: string; label: string; host_configured: boolean; port_configured: boolean; username_configured: boolean; password_saved: boolean; encryption_ready: boolean; tls_mode: string };
export type SMTPSettings = { provider: ProviderStatus; host?: string; port?: number; username?: string; password_saved?: boolean; security?: "starttls" | "ssl" | "none"; timeout_seconds?: number; is_enabled?: boolean; last_test_status?: string };
export type SMTPTestResult = { success: boolean; code: string; message: string };
export type OutreachSender = { display_name: string; from_address: string; reply_to: string; is_enabled?: boolean; configured?: boolean; provider?: ProviderStatus };
export type OutreachWorkspace = { trades: OutreachTrade[]; sender: OutreachSender; provider: ProviderStatus };
export type RFQPreview = { template_version: number; source_scope_version_id: number; subject: string; body: string; inclusions: string[]; exclusions: string[]; clarifications: string[]; bid_deadline: string | null; questions_deadline: string | null };

function base(slug: string, projectId: number) {
  return `/organizations/${encodeURIComponent(slug)}/projects/${projectId}`;
}

export const outreachApi = {
  smtpSettings(slug: string) { return apiRequest<SMTPSettings>(`/organizations/${encodeURIComponent(slug)}/outreach-smtp/`); },
  saveSMTPSettings(slug: string, data: { host: string; port: number; username: string; password: string; clear_password: boolean; security: "starttls" | "ssl" | "none"; timeout_seconds: number; is_enabled: boolean }) {
    return apiRequest<SMTPSettings>(`/organizations/${encodeURIComponent(slug)}/outreach-smtp/`, { method: "PUT", body: JSON.stringify(data) });
  },
  testSMTPConnection(slug: string) {
    return apiRequest<SMTPTestResult>(`/organizations/${encodeURIComponent(slug)}/outreach-smtp/test-connection/`, { method: "POST", body: "{}" });
  },
  sendSMTPTestEmail(slug: string, recipientEmail: string) {
    return apiRequest<SMTPTestResult>(`/organizations/${encodeURIComponent(slug)}/outreach-smtp/test-email/`, { method: "POST", body: JSON.stringify({ recipient_email: recipientEmail, confirmed: true }) });
  },
  sender(slug: string) { return apiRequest<OutreachSender>(`/organizations/${encodeURIComponent(slug)}/outreach-sender/`); },
  saveSender(slug: string, data: Pick<OutreachSender, "display_name" | "from_address" | "reply_to" | "is_enabled">) {
    return apiRequest<OutreachSender>(`/organizations/${encodeURIComponent(slug)}/outreach-sender/`, { method: "PUT", body: JSON.stringify(data) });
  },
  saveCampaignSetup(slug: string, projectId: number, campaignId: number, bidDueLocal: string, questionsDueLocal: string) {
    return apiRequest<OutreachCampaign>(`${base(slug, projectId)}/outreach-campaigns/${campaignId}/setup/`, {
      method: "PUT", body: JSON.stringify({ bid_due_local: bidDueLocal, questions_due_local: questionsDueLocal }),
    });
  },
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
