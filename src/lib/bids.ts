import { apiRequest, apiResponse } from "@/lib/api-client";

export type QuoteAttachment = { id: number; filename: string; content_type: string; byte_size: number };
export type QuoteSubmission = {
  id: number; recipient_id: number; campaign_id: number; batch_id: number;
  company_id: number; contact_id: number; trade: string; scope_version_id: number;
  company_name: string; source: "inbound_email" | "manual_upload";
  status: string; received_at: string; file_count: number; attachments: QuoteAttachment[];
};
export type QuoteRecipientChoice = { id: number; label: string };

function base(slug: string, projectId: number) {
  return `/organizations/${encodeURIComponent(slug)}/projects/${projectId}`;
}

export const bidsApi = {
  list(slug: string, projectId: number, signal?: AbortSignal) {
    return apiRequest<{ submissions: QuoteSubmission[]; recipient_choices: QuoteRecipientChoice[] }>(`${base(slug, projectId)}/bid-submissions/`, { signal });
  },
  upload(slug: string, projectId: number, recipientId: number, receivedAt: string, files: File[], note: string, requestKey: string) {
    const body = new FormData();
    body.set("recipient_id", String(recipientId));
    body.set("received_at", receivedAt);
    body.set("request_key", requestKey);
    body.set("note", note);
    for (const file of files) body.append("files", file);
    return apiRequest<QuoteSubmission>(`${base(slug, projectId)}/bid-submissions/`, { method: "POST", body });
  },
  importReceived(slug: string, projectId: number, responseId: number) {
    return apiRequest<QuoteSubmission>(`${base(slug, projectId)}/inbound-responses/${responseId}/import-quote/`, { method: "POST", body: "{}" });
  },
  download(slug: string, projectId: number, submissionId: number, attachmentId: number) {
    return apiResponse(`${base(slug, projectId)}/bid-submissions/${submissionId}/attachments/${attachmentId}/download/`).then((response) => response.blob());
  },
};
