export const PDF_CHAINING_GRACE_OBSERVATIONS = 4;

export type PdfProcessingDisplayKind =
  | "not_applicable"
  | "waiting_for_source"
  | "preparing"
  | "not_indexed"
  | "queued"
  | "running"
  | "succeeded"
  | "failed";

export type PdfProcessingDisplay = {
  kind: PdfProcessingDisplayKind;
  shouldPoll: boolean;
  showIndexAction: boolean;
  pageCount?: number;
};

export function derivePdfProcessingDisplay({
  isPdf,
  sourceStatus,
  pdfStatus,
  pdfPageCount,
  missingPdfObservationCount,
  canWrite,
}: {
  isPdf: boolean;
  sourceStatus?: "queued" | "running" | "succeeded" | "failed";
  pdfStatus?: "queued" | "running" | "succeeded" | "failed";
  pdfPageCount?: number;
  missingPdfObservationCount: number;
  canWrite: boolean;
}): PdfProcessingDisplay {
  if (!isPdf) {
    return { kind: "not_applicable", shouldPoll: false, showIndexAction: false };
  }
  if (sourceStatus !== "succeeded") {
    return {
      kind: "waiting_for_source",
      shouldPoll: sourceStatus === "queued" || sourceStatus === "running",
      showIndexAction: false,
    };
  }
  if (pdfStatus) {
    return {
      kind: pdfStatus,
      shouldPoll: pdfStatus === "queued" || pdfStatus === "running",
      showIndexAction: false,
      pageCount: pdfStatus === "succeeded" ? pdfPageCount : undefined,
    };
  }
  if (missingPdfObservationCount < PDF_CHAINING_GRACE_OBSERVATIONS) {
    return { kind: "preparing", shouldPoll: true, showIndexAction: false };
  }
  return { kind: "not_indexed", shouldPoll: false, showIndexAction: canWrite };
}
