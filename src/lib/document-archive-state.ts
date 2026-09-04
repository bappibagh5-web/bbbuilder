import type { ProductionDocument } from "./documents.ts";

export type DocumentVisibility = "active" | "archived" | "all";

export const documentArchiveConfirmation = {
  title: "Archive this document?",
  detail:
    "This hides the document from the active project workflow. Its files, revisions and review history remain preserved.",
};

export function documentStateLabel(document: Pick<ProductionDocument, "is_active">) {
  return document.is_active ? "Active" : "Archived";
}

export function visibleDocuments(
  documents: ProductionDocument[],
  visibility: DocumentVisibility,
) {
  if (visibility === "all") return documents;
  const active = visibility === "active";
  return documents.filter((document) => document.is_active === active);
}

export function activeDocuments(documents: ProductionDocument[]) {
  return documents.filter((document) => document.is_active);
}

export function canManageDocument(role: string) {
  return role === "admin" || role === "estimator_operator";
}

export function documentArchiveErrorMessage(reason: unknown, restoring: boolean) {
  const fallback = restoring
    ? "We couldn't restore this document."
    : "We couldn't archive this document.";
  if (!(reason instanceof Error)) return fallback;
  return reason.message === "The request could not be completed." ? fallback : reason.message;
}
