export type AnalysisReadinessInput = {
  isPdf: boolean;
  sourceStatus?: string;
  pdfStatus?: string;
  pageCount: number;
  runStatus?: string;
};

export function deriveAnalysisState(input: AnalysisReadinessInput) {
  if (!input.isPdf) return "unsupported" as const;
  if (input.sourceStatus !== "succeeded") return "source_required" as const;
  if (input.pdfStatus !== "succeeded" || input.pageCount < 1) return "index_required" as const;
  if (input.runStatus === "queued") return "queued" as const;
  if (input.runStatus === "running") return "running" as const;
  if (input.runStatus === "succeeded") return "succeeded" as const;
  if (input.runStatus === "failed") return "failed" as const;
  return "ready" as const;
}

export function analysisActions(state: ReturnType<typeof deriveAnalysisState>, canOperate: boolean) {
  return {
    canRun: canOperate && state === "ready",
    canRunAgain: canOperate && state === "succeeded",
    canRetry: canOperate && state === "failed",
  };
}

export function shouldPollAnalysis(state: ReturnType<typeof deriveAnalysisState>, pollCount: number) {
  return (state === "queued" || state === "running") && pollCount < 60;
}

export const MACHINE_REVIEW_WARNING = "Machine generated — not yet human reviewed.";
