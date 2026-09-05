export type DocumentSourceTarget = {
  documentId: number;
  revisionId: number;
  pageNumber: number;
};

export function sourceDocumentTarget(
  documentId: number,
  revisionId: number,
  pageNumber?: number,
): DocumentSourceTarget {
  return {
    documentId,
    revisionId,
    pageNumber: Number.isInteger(pageNumber) && Number(pageNumber) >= 1 ? Number(pageNumber) : 1,
  };
}

export function sourcePdfViewerUrl(blobUrl: string, pageNumber?: number) {
  const page = Number.isInteger(pageNumber) && Number(pageNumber) >= 1 ? Number(pageNumber) : 1;
  return `${blobUrl}#page=${page}`;
}
