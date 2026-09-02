import { apiRequest, apiResponse } from "@/lib/api-client";

export type DocumentCategoryCode =
  | "drawings"
  | "specifications"
  | "addendum"
  | "client_scope"
  | "landlord_requirements"
  | "responsibility_schedule"
  | "bid_requirements"
  | "schedule"
  | "spreadsheet"
  | "image_reference"
  | "other"
  | "unknown";

export type DocumentDisciplineCode =
  | ""
  | "general"
  | "architectural"
  | "structural"
  | "civil"
  | "mechanical"
  | "plumbing"
  | "electrical"
  | "fire_protection"
  | "interiors"
  | "landscape"
  | "other"
  | "unknown";

export type FileAssetMetadata = {
  id: number;
  storage_backend: "s3";
  original_filename: string;
  declared_mime_type: string;
  detected_mime_type: string;
  byte_size: number;
  checksum_algorithm: "sha256" | "sha512";
  checksum: string;
  created_at: string;
};

export type ProductionDocumentRevision = {
  id: number;
  document: number;
  project_file: {
    id: number;
    display_name: string;
    file_asset: FileAssetMetadata;
    created_at: string;
  };
  revision_label: string;
  issued_date: string | null;
  received_at: string;
  source_filename: string;
  notes: string;
  supersedes: number | null;
  created_by: number;
  created_at: string;
};

export type ProductionDocument = {
  id: number;
  project: number;
  title: string;
  category: DocumentCategoryCode;
  discipline: DocumentDisciplineCode;
  description: string;
  is_active: boolean;
  current_revision: ProductionDocumentRevision | null;
  revision_count: number;
  created_by: number;
  created_at: string;
  updated_at: string;
};

export type PaginatedDocuments = {
  count: number;
  next: string | null;
  previous: string | null;
  results: ProductionDocument[];
};

export type PaginatedRevisions = {
  count: number;
  next: string | null;
  previous: string | null;
  results: ProductionDocumentRevision[];
};

function projectPath(slug: string, projectId: string | number) {
  return `/organizations/${encodeURIComponent(slug)}/projects/${encodeURIComponent(String(projectId))}`;
}

function append(form: FormData, key: string, value: string | boolean | number | null | undefined) {
  if (value === null || value === undefined || value === "") return;
  form.append(key, String(value));
}

export const documentsApi = {
  list(slug: string, projectId: string | number, signal?: AbortSignal) {
    return apiRequest<PaginatedDocuments>(`${projectPath(slug, projectId)}/documents/`, {
      signal,
    });
  },
  revisions(
    slug: string,
    projectId: string | number,
    documentId: number,
    signal?: AbortSignal,
  ) {
    return apiRequest<PaginatedRevisions>(
      `${projectPath(slug, projectId)}/documents/${documentId}/revisions/`,
      { signal },
    );
  },
  uploadDocument(
    slug: string,
    projectId: string | number,
    values: {
      file: File;
      title: string;
      category: DocumentCategoryCode;
      discipline: DocumentDisciplineCode;
      description: string;
      revisionLabel: string;
      issuedDate: string;
      revisionNotes: string;
    },
  ) {
    const form = new FormData();
    form.append("file", values.file);
    append(form, "title", values.title);
    append(form, "category", values.category);
    append(form, "discipline", values.discipline);
    append(form, "description", values.description);
    append(form, "revision_label", values.revisionLabel);
    append(form, "issued_date", values.issuedDate);
    append(form, "revision_notes", values.revisionNotes);
    return apiRequest<ProductionDocument>(`${projectPath(slug, projectId)}/documents/upload/`, {
      method: "POST",
      body: form,
    });
  },
  uploadRevision(
    slug: string,
    projectId: string | number,
    documentId: number,
    values: {
      file: File;
      revisionLabel: string;
      issuedDate: string;
      revisionNotes: string;
      supersedes: number | null;
      makeCurrent: boolean;
    },
  ) {
    const form = new FormData();
    form.append("file", values.file);
    append(form, "revision_label", values.revisionLabel);
    append(form, "issued_date", values.issuedDate);
    append(form, "revision_notes", values.revisionNotes);
    append(form, "supersedes", values.supersedes);
    append(form, "make_current", values.makeCurrent);
    return apiRequest<ProductionDocumentRevision>(
      `${projectPath(slug, projectId)}/documents/${documentId}/revisions/upload/`,
      { method: "POST", body: form },
    );
  },
  setCurrent(slug: string, projectId: string | number, documentId: number, revisionId: number) {
    return apiRequest<ProductionDocument>(
      `${projectPath(slug, projectId)}/documents/${documentId}/revisions/${revisionId}/set-current/`,
      { method: "POST", body: JSON.stringify({}) },
    );
  },
  update(
    slug: string,
    projectId: string | number,
    documentId: number,
    values: Partial<Pick<ProductionDocument, "title" | "category" | "discipline" | "description" | "is_active">>,
  ) {
    return apiRequest<ProductionDocument>(
      `${projectPath(slug, projectId)}/documents/${documentId}/`,
      { method: "PATCH", body: JSON.stringify(values) },
    );
  },
  download(slug: string, projectId: string | number, documentId: number, revisionId: number) {
    return apiResponse(
      `${projectPath(slug, projectId)}/documents/${documentId}/revisions/${revisionId}/download/`,
    ).then((response) => response.blob());
  },
};

export const documentCategoryOptions: Array<[DocumentCategoryCode, string]> = [
  ["unknown", "Unknown"],
  ["drawings", "Drawings"],
  ["specifications", "Specifications"],
  ["addendum", "Addendum"],
  ["client_scope", "Client scope"],
  ["landlord_requirements", "Landlord requirements"],
  ["responsibility_schedule", "Responsibility schedule"],
  ["bid_requirements", "Bid requirements / form"],
  ["schedule", "Schedule"],
  ["spreadsheet", "Spreadsheet"],
  ["image_reference", "Image / reference"],
  ["other", "Other"],
];

export const documentDisciplineOptions: Array<[DocumentDisciplineCode, string]> = [
  ["", "Not classified"],
  ["unknown", "Unknown"],
  ["general", "General"],
  ["architectural", "Architectural"],
  ["structural", "Structural"],
  ["civil", "Civil"],
  ["mechanical", "Mechanical"],
  ["plumbing", "Plumbing"],
  ["electrical", "Electrical"],
  ["fire_protection", "Fire protection"],
  ["interiors", "Interiors"],
  ["landscape", "Landscape"],
  ["other", "Other"],
];
