export function quoteImportFailure(reason: unknown): string {
  const detail = reason instanceof Error ? reason.message.toLowerCase() : "";
  if (/unsupported|not supported|file type|declared file/.test(detail)) {
    return "This quote file type is not supported. No quote was recorded.";
  }
  if (/storage|stored object/.test(detail)) {
    return "Attachment storage failed. No quote was recorded.";
  }
  if (/provider|received email|retriev|attachment location|redirect/.test(detail)) {
    return "Could not retrieve the attachment from the email provider. No quote was recorded.";
  }
  return "The quote could not be recorded. No file or submission was saved.";
}
