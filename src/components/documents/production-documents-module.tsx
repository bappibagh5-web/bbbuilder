"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, Archive, ArchiveRestore, CheckCircle2, Download, FileText, History, LoaderCircle, MoreVertical, Pencil, Upload, X } from "lucide-react";
import type { OrganizationMembership } from "@/lib/auth";
import { documentCategoryOptions, documentDisciplineOptions, documentsApi, type DocumentCategoryCode, type DocumentDisciplineCode, type DocumentPageIndex, type ProcessingJob, type ProjectDocumentSet, type ProductionDocument, type ProductionDocumentRevision } from "@/lib/documents";
import type { ProductionProject } from "@/lib/projects";
import { suggestDocumentClassification, type DocumentClassificationSuggestion } from "@/lib/document-classification";
import { canManageDocument, documentArchiveConfirmation, documentArchiveErrorMessage, type DocumentVisibility, visibleDocuments } from "@/lib/document-archive-state";
import { PDF_CHAINING_GRACE_OBSERVATIONS, derivePdfProcessingDisplay } from "@/lib/pdf-processing-state";
import { Card } from "@/components/ui/card";
import { ApiError } from "@/lib/api-client";
import { analysisApi, type AnalysisRun } from "@/lib/analysis";

const acceptedFiles = ".pdf,.pptx,.docx,.doc,.xlsx,.xls,.csv,.txt,.png,.jpg,.jpeg";

function categoryLabel(code: DocumentCategoryCode) {
  return documentCategoryOptions.find(([value]) => value === code)?.[1] ?? code;
}

function disciplineLabel(code: DocumentDisciplineCode) {
  return documentDisciplineOptions.find(([value]) => value === code)?.[1] ?? code;
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatTimestamp(value: string) {
  return new Intl.DateTimeFormat("en-CA", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function filenameTitle(filename: string) {
  return filename
    .replace(/\.[^.]+$/, "")
    .replace(/[-_]+/g, " ")
    .trim();
}

type Notice = { tone: "success" | "error"; message: string } | null;

function documentSetErrorMessage(reason: unknown, action: "load" | "update") {
  if (reason instanceof ApiError) {
    if (reason.status === 403) return "You do not have permission to change this estimating document set.";
    if (reason.status === 0) return "The estimating document set service is unavailable. Check the backend connection and try again.";
    if (reason.message && reason.message !== "The request could not be completed.") return reason.message;
  }
  return action === "load" ? "The estimating document set could not be loaded. Refresh the page or ask an administrator to verify database migrations." : "The estimating document set could not be updated. Your previous selection was preserved.";
}

export function ProductionDocumentsModule({ project, membership, onProjectDocumentsUploaded }: { project: ProductionProject; membership: OrganizationMembership; onProjectDocumentsUploaded: () => void }) {
  const slug = membership.organization.slug;
  const canManageArchive = canManageDocument(membership.role);
  const canWrite = project.is_active && canManageArchive;
  const [documents, setDocuments] = useState<ProductionDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const [selected, setSelected] = useState<ProductionDocument | null>(null);
  const [classificationDocument, setClassificationDocument] = useState<ProductionDocument | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [visibility, setVisibility] = useState<DocumentVisibility>("active");
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<DocumentCategoryCode | "all">("all");
  const [disciplineFilter, setDisciplineFilter] = useState<DocumentDisciplineCode | "all">("all");
  const shownDocuments = visibleDocuments(documents, visibility).filter((document) => {
    const query = search.trim().toLocaleLowerCase();
    const matchesSearch = !query || [document.title, document.current_revision?.source_filename ?? "", categoryLabel(document.category), disciplineLabel(document.discipline)].some((value) => value.toLocaleLowerCase().includes(query));
    return matchesSearch && (typeFilter === "all" || document.category === typeFilter) && (disciplineFilter === "all" || document.discipline === disciplineFilter);
  });

  const loadDocuments = useCallback(
    async (signal?: AbortSignal) => {
      const response = await documentsApi.list(slug, project.id, signal);
      setDocuments(response.results);
      setSelected((current) => (current ? (visibleDocuments(response.results, visibility).find((document) => document.id === current.id) ?? null) : null));
    },
    [project.id, slug, visibility],
  );

  useEffect(() => {
    const controller = new AbortController();
    documentsApi
      .list(slug, project.id, controller.signal)
      .then((response) => setDocuments(response.results))
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setLoadError(reason instanceof Error ? reason.message : "Documents could not be loaded.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [project.id, slug]);

  async function refresh(message?: string) {
    await loadDocuments();
    if (message) setNotice({ tone: "success", message });
  }

  async function downloadCurrent(document: ProductionDocument) {
    if (!document.current_revision) return;
    setNotice(null);
    try {
      const revision = document.current_revision;
      const blob = await documentsApi.download(slug, project.id, document.id, revision.id);
      const url = URL.createObjectURL(blob);
      const anchor = window.document.createElement("a");
      anchor.href = url;
      anchor.download = revision.source_filename;
      window.document.body.append(anchor);
      try {
        anchor.click();
      } finally {
        anchor.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
      }
    } catch (reason) {
      setNotice({
        tone: "error",
        message: reason instanceof Error ? reason.message : "The file could not be downloaded.",
      });
    }
  }

  async function changeArchiveState(document: ProductionDocument, isActive: boolean) {
    setNotice(null);
    try {
      if (isActive) {
        await documentsApi.reactivate(slug, project.id, document.id);
        await refresh("Document restored to the active project workflow.");
      } else {
        await documentsApi.archive(slug, project.id, document.id);
        await refresh("Document archived. Its files, revisions and review history remain preserved.");
      }
    } catch (reason) {
      setNotice({
        tone: "error",
        message: documentArchiveErrorMessage(reason, isActive),
      });
    }
  }

  async function updateClassification(document: ProductionDocument, category: DocumentCategoryCode, discipline: DocumentDisciplineCode) {
    const updated = await documentsApi.update(slug, project.id, document.id, {
      category,
      discipline,
    });
    setDocuments((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    setSelected((current) => (current?.id === updated.id ? updated : current));
    setClassificationDocument(null);
    setNotice({
      tone: "success",
      message: "Document classification updated. Files, revisions, and review history were unchanged.",
    });
  }

  if (loading) {
    return <ModuleState icon={LoaderCircle} title="Loading project documents…" spin />;
  }
  if (loadError) {
    return <ModuleState icon={AlertCircle} title="Documents are unavailable" detail={loadError} />;
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">Project Documents</h2>
          <p className="mt-1 text-sm leading-6 text-slate-500">Preserve source files and their revision history in private project storage.</p>
        </div>
        {canWrite && (
          <button type="button" onClick={() => setShowUpload((value) => !value)} className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-primary px-4 text-sm font-semibold text-white">
            {showUpload ? <X className="h-4 w-4" /> : <Upload className="h-4 w-4" />}
            {showUpload ? "Close Upload" : "Upload Document"}
          </button>
        )}
      </div>

      {!project.is_active && <Notice tone="error" message="This project is archived. Documents remain readable, but uploads and changes are disabled." />}
      {notice && <Notice {...notice} />}
      <ProjectDocumentSetPanel projectId={project.id} slug={slug} canWrite={canWrite} />
      <div className="flex flex-wrap items-center gap-2" aria-label="Document visibility">
        {(["active", "archived", "all"] as const).map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => {
              setVisibility(value);
              setSelected(null);
            }}
            className={`rounded-lg border px-3 py-2 text-sm font-semibold capitalize ${visibility === value ? "border-primary bg-primary text-white" : "bg-white text-slate-700"}`}
          >
            {value}
          </button>
        ))}
      </div>
      <div className="grid gap-3 rounded-xl border bg-slate-50/70 p-3 md:grid-cols-[minmax(0,1fr)_14rem_14rem]">
        <label className="text-xs font-semibold text-slate-600">
          Search documents
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Title, filename, type, or discipline" className="mt-1 h-10 w-full rounded-lg border bg-white px-3 text-sm font-normal" />
        </label>
        <SelectField label="Document Type" value={typeFilter} onChange={(value) => setTypeFilter(value as DocumentCategoryCode | "all")} options={[["all", "All document types"], ...documentCategoryOptions]} />
        <SelectField label="Discipline" value={disciplineFilter} onChange={(value) => setDisciplineFilter(value as DocumentDisciplineCode | "all")} options={[["all", "All disciplines"], ...documentDisciplineOptions]} />
      </div>
      {showUpload && canWrite && (
        <NewDocumentForm
          onCancel={() => setShowUpload(false)}
          onSubmit={async (values) => {
            await documentsApi.uploadDocument(slug, project.id, values);
            setShowUpload(false);
            onProjectDocumentsUploaded();
            await refresh("Document uploaded. Its first revision was explicitly set as current.");
          }}
        />
      )}

      {!shownDocuments.length ? (
        <ModuleState icon={FileText} title={documents.length ? `No ${visibility} documents` : "No documents have been uploaded"} detail={canWrite ? "Upload a drawing set, specification, addendum, spreadsheet, image, or supporting project file." : "An Admin or Estimator / Operator can add the first project document."} />
      ) : (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(360px,0.8fr)]">
          <div className="space-y-3">
            {shownDocuments.map((document) => {
              const current = document.current_revision;
              return (
                <Card key={document.id} className="p-4 sm:p-5">
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-semibold text-slate-900">{document.title}</h3>
                        {!document.is_active && <span className="rounded bg-slate-200 px-2 py-0.5 text-[10px] font-semibold uppercase text-slate-700">Archived</span>}
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2 text-xs font-semibold">
                        <span className="rounded bg-blue-50 px-2 py-1 text-blue-700">Type: {categoryLabel(document.category)}</span>
                        <span className="rounded bg-indigo-50 px-2 py-1 text-indigo-700">Discipline: {disciplineLabel(document.discipline || "unknown")}</span>
                      </div>
                      {current ? (
                        <div className="mt-3 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-900">
                          <p className="font-semibold">Current revision: {current.revision_label || "Unlabelled"}</p>
                          <p className="mt-1 break-all text-xs">
                            {current.source_filename} · {formatSize(current.project_file.file_asset.byte_size)} · {formatTimestamp(current.received_at)}
                          </p>
                        </div>
                      ) : (
                        <p className="mt-3 text-sm text-amber-700">No current revision selected.</p>
                      )}
                    </div>
                    <details className="relative shrink-0">
                      <summary aria-label={`Actions for ${document.title}`} className="flex h-9 w-9 cursor-pointer list-none items-center justify-center rounded-lg border bg-white text-slate-700">
                        <MoreVertical className="h-4 w-4" />
                      </summary>
                      <div className="absolute right-0 z-10 mt-1 w-52 space-y-1 rounded-lg border bg-white p-2 shadow-lg">
                        <button type="button" onClick={() => setSelected(document)} className="block w-full rounded px-3 py-2 text-left text-sm hover:bg-slate-50">
                          Open Document
                        </button>
                        {current && (
                          <button type="button" onClick={() => void downloadCurrent(document)} className="block w-full rounded px-3 py-2 text-left text-sm hover:bg-slate-50">
                            Download
                          </button>
                        )}
                        <button type="button" onClick={() => setSelected(document)} className="block w-full rounded px-3 py-2 text-left text-sm hover:bg-slate-50">
                          Revision History
                        </button>
                        {canWrite && (
                          <button type="button" onClick={() => setClassificationDocument(document)} className="block w-full rounded px-3 py-2 text-left text-sm hover:bg-slate-50">
                            Edit Classification
                          </button>
                        )}
                        {canManageArchive && document.is_active && (
                          <button
                            type="button"
                            onClick={async () => {
                              if (!window.confirm(`${documentArchiveConfirmation.title}\n\n${documentArchiveConfirmation.detail}`)) return;
                              await changeArchiveState(document, false);
                            }}
                            className="block w-full rounded px-3 py-2 text-left text-sm font-semibold text-amber-800 hover:bg-amber-50"
                          >
                            Archive Document
                          </button>
                        )}
                        {canManageArchive && !document.is_active && (
                          <button
                            type="button"
                            onClick={async () => {
                              await changeArchiveState(document, true);
                            }}
                            className="block w-full rounded px-3 py-2 text-left text-sm font-semibold text-emerald-800 hover:bg-emerald-50"
                          >
                            Restore Document
                          </button>
                        )}
                      </div>
                    </details>
                  </div>
                </Card>
              );
            })}
          </div>
          <Card className="min-w-0 p-4 sm:p-5">
            {selected ? (
              <RevisionHistory
                key={`${selected.id}:${selected.updated_at}`}
                document={selected}
                project={project}
                slug={slug}
                canWrite={canWrite}
                canManageArchive={canManageArchive}
                onChanged={async (message) => {
                  await refresh(message);
                }}
                onClose={() => setSelected(null)}
              />
            ) : (
              <div className="flex min-h-64 flex-col items-center justify-center text-center">
                <History className="h-7 w-7 text-slate-400" />
                <h3 className="mt-3 font-semibold">Revision history</h3>
                <p className="mt-1 max-w-sm text-sm leading-6 text-slate-500">Select a document to inspect, download, or manage its immutable revisions.</p>
              </div>
            )}
          </Card>
        </div>
      )}
      {classificationDocument && canWrite && <ClassificationDialog document={classificationDocument} onCancel={() => setClassificationDocument(null)} onSave={(category, discipline) => updateClassification(classificationDocument, category, discipline)} />}
    </div>
  );
}

function ProjectDocumentSetPanel({ projectId, slug, canWrite }: { projectId: number; slug: string; canWrite: boolean }) {
  const [documentSet, setDocumentSet] = useState<ProjectDocumentSet | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyDocumentId, setBusyDocumentId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [projectReviewNotice, setProjectReviewNotice] = useState<string | null>(null);
  const [projectRuns, setProjectRuns] = useState<AnalysisRun[]>([]);
  const latestProjectRun = projectRuns[0] ?? null;

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([documentsApi.documentSet(slug, projectId, controller.signal), analysisApi.projectSetRuns(slug, projectId, controller.signal)])
      .then(([set, runs]) => {
        setDocumentSet(set);
        setProjectRuns(runs);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(documentSetErrorMessage(reason, "load"));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [projectId, slug]);

  async function setIncluded(documentId: number, included: boolean) {
    if (busyDocumentId !== null) return;
    setBusyDocumentId(documentId);
    setError(null);
    try {
      setDocumentSet(await documentsApi.setDocumentIncluded(slug, projectId, documentId, included));
    } catch (reason) {
      setError(documentSetErrorMessage(reason, "update"));
    } finally {
      setBusyDocumentId(null);
    }
  }

  async function startProjectReview() {
    if (busyDocumentId !== null) return;
    setBusyDocumentId(-1);
    setError(null);
    try {
      const run = await analysisApi.requestProjectSetRun(slug, projectId);
      setProjectRuns((current) => [run, ...current]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Project-wide review could not start.");
    } finally {
      setBusyDocumentId(null);
    }
  }

  async function prepareProjectItems() {
    if (busyDocumentId !== null || !latestProjectRun) return;
    setBusyDocumentId(-2);
    setError(null);
    setProjectReviewNotice(null);
    try {
      await analysisApi.materialize(slug, projectId, latestProjectRun.id);
      setProjectReviewNotice("Project-wide items are ready for human review in Document Review.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Project-wide items could not be prepared for review.");
    } finally {
      setBusyDocumentId(null);
    }
  }

  useEffect(() => {
    if (!latestProjectRun || !["queued", "running"].includes(latestProjectRun.status)) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      analysisApi
        .retrieve(slug, projectId, latestProjectRun.id, controller.signal)
        .then((run) => setProjectRuns((current) => [run, ...current.filter((item) => item.id !== run.id)]))
        .catch(() => undefined);
    }, 3_000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [latestProjectRun, projectId, slug]);

  return (
    <Card className="overflow-hidden border-blue-200">
      <div className="border-b bg-gradient-to-r from-blue-50 to-indigo-50 p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-blue-700">Project-wide source selection</p>
            <h3 className="mt-1 text-lg font-semibold text-slate-900">Estimating Document Set</h3>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-600">Choose the prepared current documents that belong in the next project-wide review. Selection binds the exact document revision and preserves page or slide provenance.</p>
          </div>
          {documentSet && (
            <div className="rounded-xl border border-blue-200 bg-white px-4 py-2 text-right shadow-sm">
              <p className="text-lg font-semibold text-slate-900">{documentSet.included_document_count} documents</p>
              <p className="text-xs text-slate-500">{documentSet.included_page_count} pages / slides selected</p>
            </div>
          )}
        </div>
      </div>
      <div className="space-y-4 p-4 sm:p-5">
        {loading && <p className="text-sm text-slate-500">Loading prepared documents…</p>}
        {error && (
          <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
            {error}
          </p>
        )}
        {documentSet?.groups.map((group) => (
          <section key={`${group.category}:${group.discipline}`} className="rounded-xl border">
            <div className="flex flex-wrap items-center gap-2 border-b bg-slate-50 px-3 py-2.5">
              <span className="rounded bg-blue-100 px-2 py-1 text-xs font-semibold text-blue-800">{group.category_label}</span>
              <span className="rounded bg-indigo-100 px-2 py-1 text-xs font-semibold text-indigo-800">{group.discipline_label}</span>
            </div>
            <ul className="divide-y">
              {group.documents.map((document) => {
                const selectable = document.preparation_status === "prepared";
                return (
                  <li key={document.document_id} className="flex flex-col gap-3 p-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-slate-900">{document.document_title}</p>
                      <p className="mt-1 text-xs text-slate-500">
                        Current {document.revision_label || document.current_revision_id || "revision not selected"} · {document.page_count || 0} pages / slides · <span className={selectable ? "font-semibold text-emerald-700" : document.preparation_status === "failed" ? "font-semibold text-red-700" : "font-semibold text-amber-700"}>{document.preparation_status.replaceAll("_", " ")}</span>
                      </p>
                      {document.warnings.map((warning) => (
                        <p key={warning.code} className="mt-1 text-xs font-medium text-amber-700">
                          Warning: {warning.message}
                        </p>
                      ))}
                    </div>
                    <button type="button" disabled={!canWrite || !selectable || busyDocumentId !== null} onClick={() => void setIncluded(document.document_id, !document.included)} className={`h-9 shrink-0 rounded-lg border px-3 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-40 ${document.included ? "border-emerald-300 bg-emerald-50 text-emerald-800" : "bg-white text-slate-700"}`}>
                      {busyDocumentId === document.document_id ? "Saving…" : document.included ? "Exclude from Set" : "Include in Set"}
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
        {documentSet && documentSet.groups.length === 0 && <p className="text-sm text-slate-500">No active documents are available. Upload and prepare documents before building the estimating set.</p>}
        {documentSet && documentSet.coordination.flags.length > 0 && (
          <section className="rounded-xl border border-amber-200 bg-amber-50 p-3">
            <p className="text-xs font-semibold uppercase tracking-wider text-amber-800">Coordination checks</p>
            <ul className="mt-2 space-y-1.5">
              {documentSet.coordination.flags.map((flag, index) => (
                <li key={`${flag.code}:${flag.source_discipline}:${flag.related_discipline}:${index}`} className="text-sm text-amber-900">
                  {flag.message}
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-amber-800">These are deterministic review prompts, not generated scope or approval decisions.</p>
          </section>
        )}
        {documentSet && (
          <section className="rounded-xl border border-indigo-200 bg-indigo-50/50 p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-indigo-700">Multi-discipline review</p>
                <h4 className="mt-1 font-semibold text-slate-900">Review the selected project set together</h4>
                <p className="mt-1 text-sm leading-6 text-slate-600">Cross-checks selected disciplines, preserves exact page provenance, flags uncertainty, and prepares information for human review before scopes are regenerated.</p>
                {latestProjectRun && (
                  <p className="mt-2 text-sm font-semibold text-indigo-800">
                    Run #{latestProjectRun.id}: {latestProjectRun.progress.completed} of {latestProjectRun.progress.total} pages complete · {latestProjectRun.status.replaceAll("_", " ")}
                    {latestProjectRun.progress.synthesis !== "queued" ? ` · synthesis ${latestProjectRun.progress.synthesis}` : ""}
                  </p>
                )}
                {projectReviewNotice && <p className="mt-2 text-sm font-semibold text-emerald-700">{projectReviewNotice}</p>}
              </div>
              {canWrite && (
                <div className="flex shrink-0 flex-wrap gap-2">
                  <button type="button" disabled={busyDocumentId !== null || documentSet.included_document_count === 0 || latestProjectRun?.status === "queued" || latestProjectRun?.status === "running"} onClick={() => void startProjectReview()} className="h-10 rounded-lg bg-indigo-700 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40">
                    {busyDocumentId === -1 ? "Starting…" : "Review Project Set"}
                  </button>
                  {latestProjectRun?.status === "succeeded" && (
                    <button type="button" disabled={busyDocumentId !== null} onClick={() => void prepareProjectItems()} className="h-10 rounded-lg border border-indigo-300 bg-white px-4 text-sm font-semibold text-indigo-800 disabled:opacity-40">
                      {busyDocumentId === -2 ? "Preparing…" : "Prepare Items for Review"}
                    </button>
                  )}
                </div>
              )}
            </div>
            <p className="mt-3 text-xs text-slate-500">This explicit action may use the configured AI provider. It never auto-starts when documents are selected. Preparing saved results does not call the provider.</p>
          </section>
        )}
        {!canWrite && <p className="text-xs text-slate-500">Viewer access is read-only. An Admin or Estimator can change the estimating set.</p>}
      </div>
    </Card>
  );
}

function ClassificationDialog({ document, onCancel, onSave }: { document: ProductionDocument; onCancel: () => void; onSave: (category: DocumentCategoryCode, discipline: DocumentDisciplineCode) => Promise<void> }) {
  const [category, setCategory] = useState<DocumentCategoryCode>(document.category);
  const [discipline, setDiscipline] = useState<DocumentDisciplineCode>(document.discipline || "unknown");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const unchanged = category === document.category && discipline === (document.discipline || "unknown");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4" role="presentation">
      <section role="dialog" aria-modal="true" aria-labelledby="classification-title" className="w-full max-w-lg rounded-2xl border bg-white p-5 shadow-2xl sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-blue-700">Document metadata</p>
            <h3 id="classification-title" className="mt-1 text-lg font-semibold text-slate-900">
              Edit Classification
            </h3>
            <p className="mt-1 text-sm text-slate-500">{document.title}</p>
          </div>
          <button type="button" onClick={onCancel} aria-label="Close classification editor" className="rounded-lg p-2 text-slate-500 hover:bg-slate-100">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <SelectField label="Document Type" value={category} onChange={(value) => setCategory(value as DocumentCategoryCode)} options={documentCategoryOptions} />
          <SelectField label="Discipline" value={discipline} onChange={(value) => setDiscipline(value as DocumentDisciplineCode)} options={documentDisciplineOptions} />
        </div>
        <p className="mt-4 rounded-lg bg-slate-50 p-3 text-xs leading-5 text-slate-600">This updates metadata only. The stored file, checksum, revisions, and review history stay unchanged.</p>
        {error && (
          <p role="alert" className="mt-3 text-sm font-medium text-red-700">
            {error}
          </p>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onCancel} disabled={busy} className="h-10 rounded-lg border bg-white px-4 text-sm font-semibold text-slate-700 disabled:opacity-50">
            Cancel
          </button>
          <button
            type="button"
            disabled={busy || unchanged}
            onClick={() => {
              setBusy(true);
              setError(null);
              void onSave(category, discipline).catch((reason: unknown) => {
                setError(reason instanceof Error ? reason.message : "The classification could not be updated.");
                setBusy(false);
              });
            }}
            className="inline-flex h-10 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50"
          >
            <Pencil className="h-4 w-4" />
            {busy ? "Saving…" : "Save Classification"}
          </button>
        </div>
      </section>
    </div>
  );
}

function RevisionHistory({ document, project, slug, canWrite, canManageArchive, onChanged, onClose }: { document: ProductionDocument; project: ProductionProject; slug: string; canWrite: boolean; canManageArchive: boolean; onChanged: (message: string) => Promise<void>; onClose: () => void }) {
  const [revisions, setRevisions] = useState<ProductionDocumentRevision[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [showRevisionUpload, setShowRevisionUpload] = useState(false);

  const loadRevisions = useCallback(async () => {
    const response = await documentsApi.revisions(slug, project.id, document.id);
    setRevisions(response.results);
  }, [document.id, project.id, slug]);

  useEffect(() => {
    let active = true;
    documentsApi
      .revisions(slug, project.id, document.id)
      .then((response) => {
        if (active) setRevisions(response.results);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Revisions could not be loaded.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [document.id, project.id, slug]);

  async function run(action: () => Promise<void>) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The request could not be completed.");
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  async function download(revision: ProductionDocumentRevision) {
    await run(async () => {
      const blob = await documentsApi.download(slug, project.id, document.id, revision.id);
      const url = URL.createObjectURL(blob);
      const anchor = window.document.createElement("a");
      anchor.href = url;
      anchor.download = revision.source_filename;
      anchor.style.display = "none";
      window.document.body.append(anchor);
      try {
        anchor.click();
      } finally {
        anchor.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
      }
    });
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Revision history</p>
          <h3 className="mt-1 font-semibold text-slate-900">{document.title}</h3>
          <p className="mt-2 flex flex-wrap gap-2 text-xs font-semibold">
            <span className="rounded bg-blue-50 px-2 py-1 text-blue-700">Type: {categoryLabel(document.category)}</span>
            <span className="rounded bg-indigo-50 px-2 py-1 text-indigo-700">Discipline: {disciplineLabel(document.discipline || "unknown")}</span>
          </p>
        </div>
        <button type="button" onClick={onClose} aria-label="Close revision history" className="rounded p-1.5 text-slate-500 hover:bg-slate-100">
          <X className="h-4 w-4" />
        </button>
      </div>

      {error && <Notice tone="error" message={error} />}
      {canManageArchive && document.is_active && (
        <div className="flex flex-wrap gap-2">
          {canWrite && (
            <button type="button" onClick={() => setShowRevisionUpload((value) => !value)} className="inline-flex h-9 items-center gap-2 rounded-lg border bg-white px-3 text-sm font-semibold">
              <Upload className="h-4 w-4" /> Add Revision
            </button>
          )}
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void run(async () => {
                if (!window.confirm(`${documentArchiveConfirmation.title}\n\n${documentArchiveConfirmation.detail}`)) return;
                await documentsApi.archive(slug, project.id, document.id);
                await onChanged("Document archived. Its revisions remain preserved.");
              })
            }
            className="inline-flex h-9 items-center gap-2 rounded-lg border bg-white px-3 text-sm font-semibold disabled:opacity-50"
          >
            <Archive className="h-4 w-4" /> Archive
          </button>
        </div>
      )}
      {canManageArchive && !document.is_active && (
        <button
          type="button"
          disabled={busy}
          onClick={() =>
            void run(async () => {
              await documentsApi.reactivate(slug, project.id, document.id);
              await onChanged("Document restored to the active project workflow.");
            })
          }
          className="inline-flex h-9 items-center gap-2 rounded-lg border bg-white px-3 text-sm font-semibold disabled:opacity-50"
        >
          <ArchiveRestore className="h-4 w-4" /> Restore Document
        </button>
      )}

      {showRevisionUpload && canWrite && document.is_active && (
        <RevisionUploadForm
          busy={busy}
          revisions={revisions}
          onCancel={() => setShowRevisionUpload(false)}
          onSubmit={async (values) => {
            await run(async () => {
              await documentsApi.uploadRevision(slug, project.id, document.id, values);
              setShowRevisionUpload(false);
              await loadRevisions();
              await onChanged(values.makeCurrent ? "Revision uploaded and explicitly set as current." : "Revision uploaded. The existing current revision was preserved.");
            });
          }}
        />
      )}

      {loading ? (
        <p className="py-8 text-center text-sm text-slate-500">Loading revisions…</p>
      ) : (
        <ul className="space-y-3">
          {revisions.map((revision) => {
            const isCurrent = document.current_revision?.id === revision.id;
            return (
              <li key={revision.id} className="rounded-lg border p-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-semibold">{revision.revision_label || "Unlabelled revision"}</p>
                      <span className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase ${isCurrent ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>{isCurrent ? "Current revision" : "Historical revision"}</span>
                    </div>
                    <p className="mt-1 break-all text-xs text-slate-500">{revision.source_filename}</p>
                    <p className="mt-1 text-xs text-slate-500">
                      {formatSize(revision.project_file.file_asset.byte_size)} · Received {formatTimestamp(revision.received_at)}
                    </p>
                    {revision.supersedes && <p className="mt-1 text-xs text-slate-500">Supersedes revision #{revision.supersedes}</p>}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" disabled={busy} onClick={() => void download(revision)} className="inline-flex h-8 items-center gap-1.5 rounded border bg-white px-2.5 text-xs font-semibold disabled:opacity-50">
                      <Download className="h-3.5 w-3.5" /> Download
                    </button>
                    {canWrite && document.is_active && !isCurrent && (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() =>
                          void run(async () => {
                            await documentsApi.setCurrent(slug, project.id, document.id, revision.id);
                            await onChanged("Current revision changed explicitly. Historical revisions were preserved.");
                          })
                        }
                        className="inline-flex h-8 items-center gap-1.5 rounded bg-emerald-700 px-2.5 text-xs font-semibold text-white disabled:opacity-50"
                      >
                        <CheckCircle2 className="h-3.5 w-3.5" /> Make Current
                      </button>
                    )}
                  </div>
                </div>
                <RevisionProcessingState revision={revision} documentId={document.id} projectId={project.id} slug={slug} canWrite={canWrite && document.is_active} />
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

const sourceProcessingLabels: Record<ProcessingJob["status"], string> = {
  queued: "Queued",
  running: "Verifying source",
  succeeded: "Source verified",
  failed: "Verification failed",
};

const pdfProcessingLabels: Record<ProcessingJob["status"], string> = {
  queued: "PDF indexing queued",
  running: "Indexing PDF",
  succeeded: "PDF indexed",
  failed: "PDF indexing failed",
};

const presentationProcessingLabels: Record<ProcessingJob["status"], string> = {
  queued: "Slide preparation queued",
  running: "Preparing slides",
  succeeded: "Slides prepared",
  failed: "Slide preparation failed",
};

function RevisionProcessingState({ revision, documentId, projectId, slug, canWrite }: { revision: ProductionDocumentRevision; documentId: number; projectId: number; slug: string; canWrite: boolean }) {
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [pages, setPages] = useState<DocumentPageIndex[]>([]);
  const [showPages, setShowPages] = useState(false);
  const [loadingPages, setLoadingPages] = useState(false);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [missingPdfObservationCount, setMissingPdfObservationCount] = useState(0);
  const [pollGeneration, setPollGeneration] = useState(0);
  const pollCount = useRef(0);
  const missingPdfObservationCountRef = useRef(0);
  const latestSource = jobs.find((job) => job.job_type === "source_verification") ?? null;
  const latestPdf = jobs.find((job) => job.job_type === "pdf_indexing") ?? null;
  const latestPresentation = jobs.find((job) => job.job_type === "presentation_indexing") ?? null;
  const isPdf = revision.project_file.file_asset.detected_mime_type === "application/pdf";
  const isPresentation = revision.project_file.file_asset.detected_mime_type === "application/vnd.openxmlformats-officedocument.presentationml.presentation";

  const load = useCallback(
    async (signal?: AbortSignal) => {
      const result = await documentsApi.processingJobs(slug, projectId, documentId, revision.id, signal);
      setJobs(result);
      setError(null);
      return result;
    },
    [documentId, projectId, revision.id, slug],
  );

  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;
    let active = true;

    async function check() {
      try {
        const current = await load(controller.signal);
        const currentSource = current.find((job) => job.job_type === "source_verification") ?? null;
        const currentPdf = current.find((job) => job.job_type === "pdf_indexing") ?? null;
        const currentPresentation = current.find((job) => job.job_type === "presentation_indexing") ?? null;
        const waitingForChainedPdf = isPdf && currentSource?.status === "succeeded" && currentPdf === null;
        const waitingForChainedPresentation = isPresentation && currentSource?.status === "succeeded" && currentPresentation === null;
        const nextMissingPdfObservationCount = waitingForChainedPdf ? Math.min(missingPdfObservationCountRef.current + 1, PDF_CHAINING_GRACE_OBSERVATIONS) : 0;
        missingPdfObservationCountRef.current = nextMissingPdfObservationCount;
        setMissingPdfObservationCount(nextMissingPdfObservationCount);
        const pdfDisplay = derivePdfProcessingDisplay({
          isPdf,
          sourceStatus: currentSource?.status,
          pdfStatus: currentPdf?.status,
          pdfPageCount: currentPdf?.result_metadata.page_count,
          missingPdfObservationCount: nextMissingPdfObservationCount,
          canWrite,
        });
        const hasActiveJob = current.some((job) => job.status === "queued" || job.status === "running");
        if (active && (pdfDisplay.kind === "preparing" || waitingForChainedPresentation || (hasActiveJob && pollCount.current < 24))) {
          pollCount.current += 1;
          timer = window.setTimeout(() => void check(), 5_000);
        }
      } catch (reason) {
        if (active && !controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "Processing state is unavailable.");
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    void check();
    return () => {
      active = false;
      controller.abort();
      if (timer) window.clearTimeout(timer);
    };
  }, [canWrite, isPdf, isPresentation, load, pollGeneration]);

  async function act(action: () => Promise<ProcessingJob>) {
    if (acting) return;
    setActing(true);
    setError(null);
    try {
      await action();
      pollCount.current = 0;
      missingPdfObservationCountRef.current = 0;
      setMissingPdfObservationCount(0);
      await load();
      setPollGeneration((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The request could not be completed.");
    } finally {
      setActing(false);
    }
  }

  async function togglePages() {
    if (showPages) {
      setShowPages(false);
      return;
    }
    setLoadingPages(true);
    setError(null);
    try {
      setPages(await documentsApi.pages(slug, projectId, documentId, revision.id));
      setShowPages(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The page index is unavailable.");
    } finally {
      setLoadingPages(false);
    }
  }

  if (loading) return <p className="mt-3 text-xs text-slate-500">Loading verification state…</p>;

  const pdfDisplay = derivePdfProcessingDisplay({
    isPdf,
    sourceStatus: latestSource?.status,
    pdfStatus: latestPdf?.status,
    pdfPageCount: latestPdf?.result_metadata.page_count,
    missingPdfObservationCount,
    canWrite,
  });

  return (
    <div className="mt-3 space-y-3 rounded-lg border bg-white p-3 text-xs">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-semibold text-slate-800">{latestSource ? sourceProcessingLabels[latestSource.status] : "Source not yet verified"}</p>
          {latestSource?.status === "succeeded" && <p className="mt-1 text-emerald-700">Size and SHA-256 match the immutable source metadata.</p>}
          {latestSource?.status === "failed" && <p className="mt-1 text-red-700">{latestSource.error_message || "Verification failed safely."}</p>}
          {latestSource?.status === "queued" && <p className="mt-1 text-slate-500">Waiting for a processing worker.</p>}
        </div>
        {canWrite && !latestSource && (
          <button type="button" disabled={acting} onClick={() => void act(() => documentsApi.requestSourceVerification(slug, projectId, documentId, revision.id))} className="h-8 rounded border bg-white px-2.5 font-semibold disabled:opacity-50">
            {acting ? "Requesting…" : "Verify Source"}
          </button>
        )}
        {canWrite && latestSource?.status === "failed" && (
          <button type="button" disabled={acting} onClick={() => void act(() => documentsApi.retryProcessingJob(slug, projectId, latestSource.id))} className="h-8 rounded border bg-white px-2.5 font-semibold disabled:opacity-50">
            {acting ? "Requesting…" : "Retry Verification"}
          </button>
        )}
      </div>
      {isPdf && latestSource?.status === "succeeded" && (
        <div className="border-t pt-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="font-semibold text-slate-800">
                {pdfDisplay.kind === "preparing" ? "Preparing PDF indexing…" : pdfDisplay.kind === "not_indexed" ? "PDF not yet indexed" : latestPdf ? pdfProcessingLabels[latestPdf.status] : "PDF not yet indexed"}
                {pdfDisplay.kind === "succeeded" && pdfDisplay.pageCount ? ` — ${pdfDisplay.pageCount} pages` : ""}
              </p>
              {latestPdf?.status === "queued" && <p className="mt-1 text-slate-500">Waiting for a processing worker.</p>}
              {latestPdf?.status === "succeeded" && <p className="mt-1 text-emerald-700">Native page structure is indexed. No OCR or AI analysis has run.</p>}
              {latestPdf?.status === "failed" && <p className="mt-1 text-red-700">{latestPdf.error_message || "PDF indexing failed safely."}</p>}
            </div>
            <div className="flex flex-wrap gap-2">
              {pdfDisplay.showIndexAction && (
                <button type="button" disabled={acting} onClick={() => void act(() => documentsApi.requestPdfIndexing(slug, projectId, documentId, revision.id))} className="h-8 rounded border bg-white px-2.5 font-semibold disabled:opacity-50">
                  {acting ? "Requesting…" : "Index PDF"}
                </button>
              )}
              {canWrite && latestPdf?.status === "failed" && (
                <button type="button" disabled={acting} onClick={() => void act(() => documentsApi.retryProcessingJob(slug, projectId, latestPdf.id))} className="h-8 rounded border bg-white px-2.5 font-semibold disabled:opacity-50">
                  {acting ? "Requesting…" : "Retry PDF Indexing"}
                </button>
              )}
              {latestPdf?.status === "succeeded" && (
                <button type="button" disabled={loadingPages} onClick={() => void togglePages()} className="h-8 rounded border bg-white px-2.5 font-semibold disabled:opacity-50">
                  {loadingPages ? "Loading…" : showPages ? "Hide Page Index" : "Page / Sheet Index"}
                </button>
              )}
            </div>
          </div>
          {showPages && <PageIndexTable pages={pages} />}
        </div>
      )}
      {isPresentation && latestSource?.status === "succeeded" && (
        <div className="border-t pt-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="font-semibold text-slate-800">
                {latestPresentation ? presentationProcessingLabels[latestPresentation.status] : "Presentation not yet prepared"}
                {latestPresentation?.status === "succeeded" && latestPresentation.result_metadata.slide_count ? ` — ${latestPresentation.result_metadata.slide_count} slides` : ""}
              </p>
              {latestPresentation?.status === "queued" && <p className="mt-1 text-slate-500">Waiting for a processing worker.</p>}
              {latestPresentation?.status === "succeeded" && <p className="mt-1 text-emerald-700">Native slide text is indexed with slide-number provenance. No OCR or AI analysis has run.</p>}
              {latestPresentation?.status === "failed" && <p className="mt-1 text-red-700">{latestPresentation.error_message || "Slide preparation failed safely."}</p>}
            </div>
            <div className="flex flex-wrap gap-2">
              {canWrite && !latestPresentation && (
                <button type="button" disabled={acting} onClick={() => void act(() => documentsApi.requestPresentationIndexing(slug, projectId, documentId, revision.id))} className="h-8 rounded border bg-white px-2.5 font-semibold disabled:opacity-50">
                  {acting ? "Requesting…" : "Prepare Slides"}
                </button>
              )}
              {canWrite && latestPresentation?.status === "failed" && (
                <button type="button" disabled={acting} onClick={() => void act(() => documentsApi.retryProcessingJob(slug, projectId, latestPresentation.id))} className="h-8 rounded border bg-white px-2.5 font-semibold disabled:opacity-50">
                  {acting ? "Requesting…" : "Retry Slide Preparation"}
                </button>
              )}
              {latestPresentation?.status === "succeeded" && (
                <button type="button" disabled={loadingPages} onClick={() => void togglePages()} className="h-8 rounded border bg-white px-2.5 font-semibold disabled:opacity-50">
                  {loadingPages ? "Loading…" : showPages ? "Hide Slide Index" : "Slide Index"}
                </button>
              )}
            </div>
          </div>
          {showPages && <PageIndexTable pages={pages} labelHeading="Source label" />}
        </div>
      )}
      {error && (
        <p role="alert" className="mt-2 text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}

function PageIndexTable({ pages, labelHeading = "PDF label" }: { pages: DocumentPageIndex[]; labelHeading?: string }) {
  return (
    <div className="mt-3 overflow-x-auto rounded-lg border">
      <table className="min-w-full divide-y text-left text-xs">
        <thead className="bg-slate-50 text-slate-600">
          <tr>
            <th className="px-3 py-2 font-semibold">Page</th>
            <th className="px-3 py-2 font-semibold">{labelHeading}</th>
            <th className="px-3 py-2 font-semibold">Sheet</th>
            <th className="px-3 py-2 font-semibold">Title</th>
            <th className="px-3 py-2 font-semibold">Native text</th>
            <th className="px-3 py-2 font-semibold">Geometry</th>
          </tr>
        </thead>
        <tbody className="divide-y bg-white">
          {pages.map((page) => (
            <tr key={page.id}>
              <td className="whitespace-nowrap px-3 py-2 font-semibold">{page.page_number}</td>
              <td className="whitespace-nowrap px-3 py-2">{page.page_label || "—"}</td>
              <td className="whitespace-nowrap px-3 py-2">{page.drawing_sheet?.sheet_number || "—"}</td>
              <td className="min-w-40 px-3 py-2">{page.drawing_sheet?.sheet_title || "—"}</td>
              <td className="whitespace-nowrap px-3 py-2">{page.has_native_text ? `Yes (${page.native_text_char_count.toLocaleString()} chars)` : "No"}</td>
              <td className="whitespace-nowrap px-3 py-2 text-slate-500">
                {Math.round(page.width_points)} × {Math.round(page.height_points)} pt · {page.rotation_degrees}°
              </td>
            </tr>
          ))}
          {pages.length === 0 && (
            <tr>
              <td colSpan={6} className="px-3 py-6 text-center text-slate-500">
                No indexed pages were returned.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

type NewUploadValues = Parameters<typeof documentsApi.uploadDocument>[2];
type RevisionUploadValues = Parameters<typeof documentsApi.uploadRevision>[3];

function NewDocumentForm({ onSubmit, onCancel }: { onSubmit: (values: NewUploadValues) => Promise<void>; onCancel: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState<DocumentCategoryCode>("unknown");
  const [discipline, setDiscipline] = useState<DocumentDisciplineCode>("unknown");
  const [suggestion, setSuggestion] = useState<DocumentClassificationSuggestion | null>(null);
  const [description, setDescription] = useState("");
  const [revisionLabel, setRevisionLabel] = useState("");
  const [issuedDate, setIssuedDate] = useState("");
  const [revisionNotes, setRevisionNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <Card className="p-4 sm:p-5">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!file || !title.trim() || submitting) return;
          setSubmitting(true);
          setError(null);
          void onSubmit({
            file,
            title: title.trim(),
            category,
            discipline,
            description,
            revisionLabel,
            issuedDate,
            revisionNotes,
          })
            .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Upload failed."))
            .finally(() => setSubmitting(false));
        }}
        className="space-y-4"
      >
        <div>
          <h3 className="font-semibold">Upload a new logical document</h3>
          <p className="mt-1 text-sm text-slate-500">The source file will be stored privately and preserved as its first immutable revision.</p>
        </div>
        {error && <Notice tone="error" message={error} />}
        <label className="block text-sm font-medium">
          File
          <input
            required
            type="file"
            accept={acceptedFiles}
            onChange={(event) => {
              const selectedFile = event.target.files?.[0] ?? null;
              setFile(selectedFile);
              setSuggestion(selectedFile ? suggestDocumentClassification(selectedFile.name) : null);
              if (selectedFile && !title) setTitle(filenameTitle(selectedFile.name));
            }}
            className="mt-1 block w-full rounded-lg border bg-white px-3 py-2 text-sm"
          />
        </label>
        {suggestion && (
          <div className="flex flex-col gap-3 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-950 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="font-semibold">
                Suggested classification: {categoryLabel(suggestion.category)} · {disciplineLabel(suggestion.discipline)}
              </p>
              <p className="mt-1 text-xs text-blue-800">{suggestion.explanation}</p>
            </div>
            <button
              type="button"
              onClick={() => {
                setCategory(suggestion.category);
                setDiscipline(suggestion.discipline);
                setSuggestion(null);
              }}
              className="h-9 shrink-0 rounded-lg bg-blue-700 px-3 text-xs font-semibold text-white"
            >
              Apply suggestion
            </button>
          </div>
        )}
        <div className="grid gap-4 md:grid-cols-2">
          <TextField label="Document title" value={title} onChange={setTitle} required />
          <SelectField label="Document Type" value={category} onChange={(value) => setCategory(value as DocumentCategoryCode)} options={documentCategoryOptions} />
          <SelectField label="Discipline" value={discipline} onChange={(value) => setDiscipline(value as DocumentDisciplineCode)} options={documentDisciplineOptions} />
          <TextField label="Revision label (optional)" value={revisionLabel} onChange={setRevisionLabel} />
          <label className="block text-sm font-medium">
            Issued date (optional)
            <input type="date" value={issuedDate} onChange={(event) => setIssuedDate(event.target.value)} className="mt-1 h-10 w-full rounded-lg border px-3 text-sm" />
          </label>
        </div>
        <TextArea label="Document description (optional)" value={description} onChange={setDescription} />
        <TextArea label="Revision notes (optional)" value={revisionNotes} onChange={setRevisionNotes} />
        <div className="flex flex-wrap justify-end gap-2 border-t pt-4">
          <button type="button" onClick={onCancel} disabled={submitting} className="h-10 rounded-lg border bg-white px-4 text-sm font-semibold disabled:opacity-50">
            Cancel
          </button>
          <button type="submit" disabled={!file || !title.trim() || submitting} className="inline-flex h-10 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50">
            {submitting && <LoaderCircle className="h-4 w-4 animate-spin" />}
            {submitting ? "Uploading securely…" : "Upload Document"}
          </button>
        </div>
      </form>
    </Card>
  );
}

function RevisionUploadForm({ busy, revisions, onSubmit, onCancel }: { busy: boolean; revisions: ProductionDocumentRevision[]; onSubmit: (values: RevisionUploadValues) => Promise<void>; onCancel: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [revisionLabel, setRevisionLabel] = useState("");
  const [issuedDate, setIssuedDate] = useState("");
  const [revisionNotes, setRevisionNotes] = useState("");
  const [supersedes, setSupersedes] = useState<number | null>(null);
  const [makeCurrent, setMakeCurrent] = useState(false);

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (file && !busy)
          void onSubmit({
            file,
            revisionLabel,
            issuedDate,
            revisionNotes,
            supersedes,
            makeCurrent,
          });
      }}
      className="space-y-3 rounded-lg border bg-slate-50 p-3"
    >
      <p className="text-sm font-semibold">Upload another immutable revision</p>
      <label className="block text-xs font-semibold">
        File
        <input required type="file" accept={acceptedFiles} onChange={(event) => setFile(event.target.files?.[0] ?? null)} className="mt-1 block w-full rounded-lg border bg-white px-2 py-2 text-sm" />
      </label>
      <div className="grid gap-3 sm:grid-cols-2">
        <TextField label="Revision label" value={revisionLabel} onChange={setRevisionLabel} />
        <label className="block text-xs font-semibold">
          Issued date
          <input type="date" value={issuedDate} onChange={(event) => setIssuedDate(event.target.value)} className="mt-1 h-9 w-full rounded-lg border bg-white px-2 text-sm" />
        </label>
      </div>
      <label className="block text-xs font-semibold">
        Supersedes
        <select value={supersedes ?? ""} onChange={(event) => setSupersedes(event.target.value ? Number(event.target.value) : null)} className="mt-1 h-9 w-full rounded-lg border bg-white px-2 text-sm">
          <option value="">No explicit supersession</option>
          {revisions.map((revision) => (
            <option key={revision.id} value={revision.id}>
              {revision.revision_label || `Revision #${revision.id}`}
            </option>
          ))}
        </select>
      </label>
      <TextArea label="Revision notes" value={revisionNotes} onChange={setRevisionNotes} />
      <label className="flex items-start gap-2 rounded-lg bg-white p-3 text-xs leading-5">
        <input type="checkbox" checked={makeCurrent} onChange={(event) => setMakeCurrent(event.target.checked)} className="mt-0.5" />
        <span>
          <strong>Explicitly make this the current revision.</strong>
          <br />
          Leave unchecked to preserve the existing current revision.
        </span>
      </label>
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onCancel} disabled={busy} className="h-9 rounded-lg border bg-white px-3 text-xs font-semibold disabled:opacity-50">
          Cancel
        </button>
        <button type="submit" disabled={!file || busy} className="inline-flex h-9 items-center gap-2 rounded-lg bg-primary px-3 text-xs font-semibold text-white disabled:opacity-50">
          {busy && <LoaderCircle className="h-3.5 w-3.5 animate-spin" />}
          {busy ? "Uploading…" : "Upload Revision"}
        </button>
      </div>
    </form>
  );
}

function TextField({ label, value, onChange, required = false }: { label: string; value: string; onChange: (value: string) => void; required?: boolean }) {
  return (
    <label className="block text-sm font-medium">
      {label}
      <input required={required} value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 h-10 w-full rounded-lg border px-3 text-sm" />
    </label>
  );
}

function TextArea({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="block text-sm font-medium">
      {label}
      <textarea value={value} onChange={(event) => onChange(event.target.value)} rows={2} className="mt-1 w-full rounded-lg border px-3 py-2 text-sm" />
    </label>
  );
}

function SelectField({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: Array<[string, string]> }) {
  return (
    <label className="block text-sm font-medium">
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 h-10 w-full rounded-lg border bg-white px-3 text-sm">
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>
            {optionLabel}
          </option>
        ))}
      </select>
    </label>
  );
}

function Notice({ tone, message }: { tone: "success" | "error"; message: string }) {
  return (
    <div role={tone === "error" ? "alert" : "status"} className={`flex items-start gap-2 rounded-lg p-3 text-sm ${tone === "error" ? "bg-red-50 text-red-800" : "bg-emerald-50 text-emerald-800"}`}>
      {tone === "error" ? <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" /> : <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />}
      <span>{message}</span>
    </div>
  );
}

function ModuleState({ icon: Icon, title, detail, spin = false }: { icon: typeof FileText; title: string; detail?: string; spin?: boolean }) {
  return (
    <section className="flex min-h-64 flex-col items-center justify-center rounded-xl border border-dashed px-6 text-center">
      <Icon className={`h-7 w-7 text-slate-400 ${spin ? "animate-spin" : ""}`} />
      <h2 className="mt-4 font-semibold">{title}</h2>
      {detail && <p className="mt-1 max-w-lg text-sm leading-6 text-slate-500">{detail}</p>}
    </section>
  );
}
