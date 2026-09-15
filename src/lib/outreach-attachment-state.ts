export type ReceivedAttachmentNotice = { id: number; attachment_count: number };

export function pendingQuoteAttachments(recipient: {
  inbound_attachment_responses?: ReceivedAttachmentNotice[] | null;
  imported_response_ids?: number[] | null;
}): ReceivedAttachmentNotice[] {
  if (!Array.isArray(recipient.inbound_attachment_responses)) return [];
  const imported = new Set(Array.isArray(recipient.imported_response_ids) ? recipient.imported_response_ids : []);
  return recipient.inbound_attachment_responses.filter(
    (item) => Number.isInteger(item.id) && item.attachment_count > 0 && !imported.has(item.id),
  );
}
