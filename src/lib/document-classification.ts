import type { DocumentCategoryCode, DocumentDisciplineCode } from "./documents.ts";

export type DocumentClassificationSuggestion = {
  category: DocumentCategoryCode;
  discipline: DocumentDisciplineCode;
  explanation: string;
};

const disciplinePatterns: Array<[RegExp, DocumentDisciplineCode]> = [
  [/(?:^|[_\s-])A(?:[_\s-]+IFC|$)/i, "architectural"],
  [/(?:^|[_\s-])M(?:[_\s-]+IFC|$)/i, "mechanical"],
  [/(?:^|[_\s-])E(?:[_\s-]+IFC|$)/i, "electrical"],
];

export function suggestDocumentClassification(
  filename: string,
): DocumentClassificationSuggestion | null {
  const stem = filename.replace(/\.[^.]+$/, "");
  const narrative = /(?:^|[_\s-])NARRATIVE(?:[_\s-]|$)/i.test(stem);
  const discipline = disciplinePatterns.find(([pattern]) => pattern.test(stem))?.[1];
  if (!narrative && !discipline) return null;

  return {
    category: narrative ? "narrative" : "drawings",
    discipline: discipline ?? "unknown",
    explanation: "Suggested from the selected filename. Confirm before applying.",
  };
}
