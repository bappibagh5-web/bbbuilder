"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  BadgeCheck,
  ChevronDown,
  ExternalLink,
  FileStack,
  History,
  LoaderCircle,
  Pencil,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import type { OrganizationMembership } from "@/lib/auth";
import { analysisApi, type IntelligenceSnapshot } from "@/lib/analysis";
import type { ProductionProject } from "@/lib/projects";
import {
  itemsToLines,
  itemTypeLabel,
  linesToItems,
  replaceScopePackage,
  responsibilityLabel,
  scopeItemCount,
  scopePackageCounts,
  scopePackageGenerations,
} from "@/lib/scope-package-state";
import {
  scopePackagesApi,
  type ScopeCoveragePreview,
  type ScopeCoveragePreviewSource,
  type ScopeItemSource,
  type ScopePackage,
  type ScopePackageEdit,
} from "@/lib/scope-packages";
import { documentsApi } from "@/lib/documents";
import { sourcePdfViewerUrl } from "@/lib/document-source-navigation";
import { cn } from "@/lib/utils";
import { canEditProjects } from "@/components/organizations/organization-provider";
import { Card } from "@/components/ui/card";

export function ProductionScopesModule({
  project,
  membership,
}: {
  project: ProductionProject;
  membership: OrganizationMembership;
}) {
  const slug = membership.organization.slug;
  const canWrite = project.is_active && canEditProjects(membership);
  const [packages, setPackages] = useState<ScopePackage[]>([]);
  const [snapshots, setSnapshots] = useState<IntelligenceSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [preview, setPreview] = useState<ScopeCoveragePreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [confirmGeneration, setConfirmGeneration] = useState(false);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      const [scopeData, snapshotData] = await Promise.all([
        scopePackagesApi.list(slug, project.id, signal, showHistory),
        analysisApi.snapshots(slug, project.id, signal),
      ]);
      setPackages(scopeData);
      setSnapshots(snapshotData);
    },
    [project.id, showHistory, slug],
  );

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      scopePackagesApi.list(slug, project.id, controller.signal, showHistory),
      analysisApi.snapshots(slug, project.id, controller.signal),
    ])
      .then(([scopeData, snapshotData]) => {
        setPackages(scopeData);
        setSnapshots(snapshotData);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(
            reason instanceof Error
              ? reason.message
              : "Scope packages could not be loaded.",
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [project.id, showHistory, slug]);

  const approvedSnapshots = snapshots
    .filter((snapshot) => snapshot.approval)
    .sort((a, b) => b.version - a.version);
  const latestApproved = approvedSnapshots[0] ?? null;
  const { active: activePackages, historical: historicalPackages } =
    scopePackageGenerations(packages);
  const counts = scopePackageCounts(activePackages);
  const detailedItemCount = scopeItemCount(activePackages);

  async function viewSource(source: ScopeItemSource) {
    const preview = window.open("about:blank", "_blank");
    if (preview) preview.opener = null;
    setError(null);
    try {
      const blob = await documentsApi.download(
        slug,
        project.id,
        source.document_id,
        source.document_revision,
      );
      const url = URL.createObjectURL(blob);
      if (preview)
        preview.location.href = sourcePdfViewerUrl(url, source.page_number);
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (reason) {
      preview?.close();
      setError(
        reason instanceof Error
          ? reason.message
          : "The source document could not be opened.",
      );
    }
  }

  async function viewPreviewSource(source: ScopeCoveragePreviewSource) {
    const previewWindow = window.open("about:blank", "_blank");
    if (previewWindow) previewWindow.opener = null;
    setError(null);
    try {
      const blob = await documentsApi.download(
        slug,
        project.id,
        source.document_id,
        source.document_revision_id,
      );
      const url = URL.createObjectURL(blob);
      if (previewWindow) {
        previewWindow.location.href = sourcePdfViewerUrl(url, source.page_number);
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (reason) {
      previewWindow?.close();
      setError(reason instanceof Error ? reason.message : "The preview source could not be opened.");
    }
  }

  async function loadPreview() {
    setPreviewLoading(true);
    setError(null);
    try {
      setPreview(await scopePackagesApi.preview(slug, project.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Scope coverage preview could not be loaded.");
    } finally {
      setPreviewLoading(false);
    }
  }

  async function generate() {
    if (!preview || !canWrite || busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await scopePackagesApi.generate(slug, project.id, preview);
      await load();
      setConfirmGeneration(false);
      setNotice(
        result.created_count
          ? `New draft scopes created from Project Information Version ${result.source_snapshot_version}: ${result.package_count} trade scopes and ${result.scope_item_count} detailed work items.`
          : "Draft scopes already exist for this approved version. Nothing was overwritten.",
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Draft scopes could not be generated.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function save(packageId: number, values: ScopePackageEdit) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await scopePackagesApi.update(slug, project.id, packageId, values);
      await load();
      setEditing(null);
      setNotice("Scope changes saved as a new version.");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Scope changes could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function ready(packageId: number) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await scopePackagesApi.markReady(
        slug,
        project.id,
        packageId,
      );
      setPackages((current) => replaceScopePackage(current, updated));
      setNotice("Scope marked ready by the estimator.");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "The scope could not be marked ready.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (loading)
    return (
      <State
        title="Loading scope packages…"
        detail="Retrieving approved project information and scope history."
        spin
      />
    );

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <span className="inline-flex items-center gap-1 rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-blue-700">
            <FileStack className="h-3 w-3" />
            Scope Builder
          </span>
          <h2 className="mt-3 text-xl font-semibold text-slate-950">
            Trade & Scope Packages
          </h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-500">
            Build editable bid scopes from approved project information. Human
            changes are preserved as explicit versions.
          </p>
        </div>
      </div>
      {error && <Notice tone="error" message={error} />}
      {notice && <Notice tone="success" message={notice} />}
      <ScopeCoveragePreviewPanel
        preview={preview}
        loading={previewLoading}
        currentPackageCount={activePackages.length}
        onLoad={() => void loadPreview()}
        onViewSource={(source) => void viewPreviewSource(source)}
        canWrite={canWrite}
        onCreate={() => setConfirmGeneration(true)}
      />
      {preview && confirmGeneration && (
        <GenerationConfirmation
          preview={preview}
          busy={busy}
          onCancel={() => setConfirmGeneration(false)}
          onConfirm={() => void generate()}
        />
      )}
      <section aria-label="Scope status" className="grid gap-3 sm:grid-cols-4">
        <Metric
          label="Current trade packages"
          value={counts.total}
          tone="blue"
        />
        <Metric
          label="Detailed scope items"
          value={detailedItemCount}
          tone="blue"
        />
        <Metric label="Draft" value={counts.draft} tone="amber" />
        <Metric label="Ready" value={counts.ready} tone="green" />
      </section>
      {!latestApproved ? (
        <State
          title="Approved project information required"
          detail="Approve a Project Information version in Document Review before generating scope packages."
        />
      ) : activePackages.length === 0 ? (
        <State
          title="No scope packages yet"
          detail={
            canWrite
              ? `Generate drafts from approved Project Information Version ${latestApproved.version}.`
              : `An estimator can generate drafts from approved Project Information Version ${latestApproved.version}.`
          }
        />
      ) : (
        <div className="grid gap-4">
          {activePackages.map((item) =>
            editing === item.id ? (
              <ScopeEditor
                key={item.id}
                item={item}
                busy={busy}
                onCancel={() => setEditing(null)}
                onSave={(values) => void save(item.id, values)}
              />
            ) : (
              <ScopeCard
                key={item.id}
                item={item}
                canWrite={canWrite}
                busy={busy}
                onEdit={() => setEditing(item.id)}
                onReady={() => void ready(item.id)}
                onViewSource={(source) => void viewSource(source)}
              />
            ),
          )}
        </div>
      )}
      <section className="rounded-xl border bg-white p-4">
        <button
          type="button"
          onClick={() => setShowHistory((value) => !value)}
          className="inline-flex items-center gap-2 text-sm font-semibold text-blue-700"
        >
          <History className="h-4 w-4" />
          {showHistory ? "Hide generation history" : "View generation history"}
        </button>
        {showHistory && (
          <div className="mt-4 space-y-2 border-t pt-4">
            {historicalPackages.length ? (
              historicalPackages.map((item) => (
                <div
                  key={item.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-50 px-3 py-2 text-sm"
                >
                  <span className="font-medium text-slate-700">
                    {item.trade_category} · Project Information V
                    {item.source_snapshot_version}
                  </span>
                  <span className="rounded-full bg-slate-200 px-2 py-1 text-[10px] font-bold uppercase text-slate-600">
                    Superseded · {item.current_version.scope_items.length} items
                  </span>
                </div>
              ))
            ) : (
              <p className="text-sm text-slate-500">
                No earlier scope generations.
              </p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

function GenerationConfirmation({
  preview,
  busy,
  onCancel,
  onConfirm,
}: {
  preview: ScopeCoveragePreview;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <section role="dialog" aria-labelledby="scope-generation-title" className="rounded-xl border-2 border-blue-200 bg-white p-5 shadow-lg">
      <p className="text-xs font-bold uppercase tracking-wider text-blue-700">Confirm new draft generation</p>
      <h3 id="scope-generation-title" className="mt-2 text-lg font-semibold text-slate-950">
        Create a new draft scope generation from Project Information V{preview.source_snapshot_version}?
      </h3>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <Metric label="Trade scopes" value={preview.proposed_package_count} tone="blue" />
        <Metric label="Detailed work items" value={preview.proposed_scope_item_count} tone="blue" />
        <Metric label="Project-wide requirements kept separate" value={preview.project_wide_requirement_count} tone="amber" />
      </div>
      <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-slate-600">
        <li>Existing scope history and human edits will be preserved.</li>
        <li>Every new trade scope will start as Draft.</li>
        <li>Contractor discovery will not use these scopes until an estimator marks them Ready.</li>
      </ul>
      <div className="mt-5 flex flex-wrap gap-2">
        <button type="button" onClick={onConfirm} disabled={busy} className="inline-flex h-10 items-center gap-2 rounded-lg bg-[#173f5f] px-4 text-sm font-semibold text-white disabled:opacity-50">
          {busy && <LoaderCircle className="h-4 w-4 animate-spin" />}
          {busy ? "Creating drafts…" : "Create Draft Scopes"}
        </button>
        <button type="button" onClick={onCancel} disabled={busy} className="h-10 rounded-lg border px-4 text-sm font-semibold text-slate-700 disabled:opacity-50">
          Cancel
        </button>
      </div>
    </section>
  );
}

function ScopeCoveragePreviewPanel({
  preview,
  loading,
  currentPackageCount,
  onLoad,
  onViewSource,
  canWrite,
  onCreate,
}: {
  preview: ScopeCoveragePreview | null;
  loading: boolean;
  currentPackageCount: number;
  onLoad: () => void;
  onViewSource: (source: ScopeCoveragePreviewSource) => void;
  canWrite: boolean;
  onCreate: () => void;
}) {
  return (
    <section className="rounded-xl border border-violet-200 bg-gradient-to-br from-violet-50 via-white to-blue-50 p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-bold uppercase tracking-wider text-violet-700">Read-only planning preview</p>
          <h2 className="mt-2 text-xl font-semibold text-slate-950">Preview New Scope Coverage</h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600">Compare proposed trade packages from the latest approved Project Information with the current scope generation. Previewing does not create or supersede scope records.</p>
        </div>
        <button type="button" onClick={onLoad} disabled={loading} className="inline-flex h-10 items-center gap-2 rounded-lg bg-violet-700 px-4 text-sm font-semibold text-white disabled:opacity-50">
          {loading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          {loading ? "Building preview…" : "Preview New Scope Coverage"}
        </button>
      </div>
      {!preview ? <p className="mt-4 text-sm text-slate-500">Current scope generation: {currentPackageCount} trade packages. Run the preview to compare without changing it.</p> : <div className="mt-5 space-y-4">
        <div className="rounded-xl border border-blue-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-wider text-blue-700">New scope coverage from Project Information V{preview.source_snapshot_version}</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
            <Metric label="Trade scopes identified" value={preview.proposed_package_count} tone="blue" />
            <Metric label="Detailed work items" value={preview.proposed_scope_item_count} tone="blue" />
            <Metric label="Project-wide requirements" value={preview.project_wide_requirement_count} tone="blue" />
            <Metric label="Project Information represented" value={`${preview.source_coverage_percent}%`} tone="green" />
            <Metric label="Responsibility not stated" value={`${preview.responsibility_not_stated_count} of ${preview.total_requirement_count}`} tone="amber" />
            <Metric label="Expected scopes not found" value={preview.expected_scope_coverage.filter((scope) => scope.status === "not_found").length} tone="amber" />
          </div>
          <p className="mt-4 text-sm text-slate-600">The documents identify the work below. Missing responsibility means the source documents did not name who performs it—not that the work itself is uncertain.</p>
          {canWrite && (
            <button type="button" onClick={onCreate} className="mt-4 inline-flex h-10 items-center gap-2 rounded-lg bg-[#173f5f] px-4 text-sm font-semibold text-white shadow-sm hover:bg-[#102f49]">
              <Sparkles className="h-4 w-4" />
              Create Draft Scopes
            </button>
          )}
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Responsibility stated" value={preview.responsibility_explicit_count} tone="green" />
          <Metric label="Responsibility not stated" value={preview.responsibility_not_stated_count} tone="amber" />
          <Metric label="Owner, landlord, or by others" value={preview.external_responsibility_count} tone="blue" />
          <Metric label="Coordination required" value={preview.coordination_entry_count} tone="amber" />
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-xl border border-emerald-200 bg-emerald-50/70 p-4">
            <h3 className="text-sm font-semibold text-emerald-900">New coverage beyond the current generation</h3>
            <p className="mt-1 text-xs text-emerald-800">{preview.new_package_names.length ? preview.new_package_names.join(" · ") : "No additional trade destinations detected."}</p>
          </div>
          <div className="rounded-xl border border-amber-200 bg-amber-50/70 p-4">
            <h3 className="text-sm font-semibold text-amber-900">Current packages without Version {preview.source_snapshot_version} support</h3>
            <p className="mt-1 text-xs text-amber-800">{preview.historical_packages_no_longer_supported.length ? preview.historical_packages_no_longer_supported.join(" · ") : "Every current package retains supporting project information."}</p>
          </div>
        </div>
        <div>
          <h3 className="text-base font-semibold text-slate-950">Trade scopes</h3>
          <p className="mt-1 text-sm text-slate-600">Open a trade to review its proposed work and supporting source documents.</p>
          <div className="mt-3 space-y-2">
            {preview.packages.map((item) => <PreviewPackageDetails key={item.trade_key} item={item} onViewSource={onViewSource} />)}
          </div>
        </div>
        <div>
          <h3 className="text-base font-semibold text-slate-950">Project-wide requirements</h3>
          <p className="mt-1 text-sm text-slate-600">Requirements that apply across the project, such as permits, site rules, landlord coordination, inspections, and general construction obligations.</p>
          <div className="mt-3"><PreviewPackageDetails item={preview.project_wide_requirements} onViewSource={onViewSource} /></div>
        </div>
        <section className="rounded-xl border bg-white p-5">
          <h3 className="text-base font-semibold text-slate-950">Scope coverage check</h3>
          <p className="mt-1 text-sm text-slate-600">“Not found” means the reviewed documents did not provide enough evidence. It does not guarantee that the trade is unnecessary.</p>
          <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{preview.expected_scope_coverage.map((scope) => <div key={scope.trade_key} className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2"><span className="text-sm font-medium text-slate-800">{scope.name}</span><span className={cn("rounded-full px-2 py-1 text-[10px] font-bold uppercase", scope.status === "found" ? "bg-emerald-100 text-emerald-700" : scope.status === "limited" ? "bg-amber-100 text-amber-700" : "bg-rose-100 text-rose-700")}>{scope.status === "found" ? "Found" : scope.status === "limited" ? "Limited evidence" : "Not found"}</span></div>)}</div>
        </section>
        <details className="rounded-xl border bg-white p-4"><summary className="cursor-pointer text-sm font-semibold text-slate-700">Advanced details</summary><div className="mt-3 space-y-4 border-t pt-3"><div className="flex flex-wrap gap-2 text-xs font-semibold text-slate-600"><span className="rounded-full bg-slate-100 px-3 py-1.5">{preview.mapped_entry_count} / {preview.total_approved_entries} Project Information items represented</span><span className="rounded-full bg-slate-100 px-3 py-1.5">{preview.non_scope_informational_count} informational</span><span className="rounded-full bg-slate-100 px-3 py-1.5">{preview.unmapped_entry_count} unclassified</span><span className="rounded-full bg-slate-100 px-3 py-1.5">{preview.bundled_findings_split} bundled findings separated</span><span className="rounded-full bg-slate-100 px-3 py-1.5">{preview.non_actionable_clauses_removed} non-actionable clauses removed</span><span className="rounded-full bg-slate-100 px-3 py-1.5">{preview.trade_assignments_refined} clause-level trade assignments refined</span><span className="rounded-full bg-slate-100 px-3 py-1.5">{preview.passive_fire_items_removed_from_sprinklers} passive-fire items kept outside sprinkler scope</span><span className="rounded-full bg-slate-100 px-3 py-1.5">{preview.duplicate_obligations_consolidated} equivalent obligations consolidated</span><span className="rounded-full bg-slate-100 px-3 py-1.5">Rule version {preview.taxonomy_version}</span></div><div className="grid gap-4 md:grid-cols-2"><div><h4 className="text-xs font-bold uppercase text-amber-700">Unclassified</h4>{preview.unmapped_items.length ? <ul className="mt-2 space-y-1 text-sm text-slate-600">{preview.unmapped_items.map((item, index) => <li key={index}>{String(item.subject ?? "Unclassified Project Information")}</li>)}</ul> : <p className="mt-2 text-sm text-slate-500">None</p>}</div><div><h4 className="text-xs font-bold uppercase text-slate-500">Informational only</h4><p className="mt-2 text-sm text-slate-600">{preview.non_scope_informational_items.length} non-actionable document facts were retained outside the proposed scopes.</p></div></div></div></details>
      </div>}
    </section>
  );
}

function PreviewPackageDetails({ item, onViewSource }: { item: ScopeCoveragePreview["packages"][number]; onViewSource: (source: ScopeCoveragePreviewSource) => void }) {
  return <details className="rounded-xl border bg-white shadow-sm"><summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3 px-4 py-3"><div><span className="font-semibold text-slate-900">{item.name}</span><p className="mt-1 text-xs text-slate-500">{item.scope_item_count} work items · {item.responsibility_explicit_count} responsibility stated · {item.responsibility_not_stated_count} not stated · {item.source_document_count} documents / {item.source_page_count} pages</p></div><ChevronDown className="h-4 w-4 text-slate-400" /></summary><div className="divide-y border-t">{item.items.map((scopeItem) => <article key={scopeItem.item_key} className="p-4"><div className="flex flex-wrap items-center gap-2"><span className="rounded bg-slate-100 px-2 py-1 text-[10px] font-bold uppercase text-slate-600">{previewResponsibility(scopeItem.responsibility)}</span>{scopeItem.coordination_required && <span className="rounded bg-amber-100 px-2 py-1 text-[10px] font-bold uppercase text-amber-700">Coordination required</span>}<h4 className="font-semibold text-slate-900">{scopeItem.title}</h4></div><p className="mt-2 text-sm leading-6 text-slate-600">{scopeItem.description}</p><PreviewSources sources={scopeItem.provenance} onViewSource={onViewSource} /></article>)}</div></details>;
}

function PreviewSources({ sources, onViewSource }: { sources: ScopeCoveragePreviewSource[]; onViewSource: (source: ScopeCoveragePreviewSource) => void }) {
  const sourceButton = (source: ScopeCoveragePreviewSource) => <button key={source.snapshot_provenance_id} type="button" onClick={() => onViewSource(source)} className="rounded-lg border px-2.5 py-1.5 text-xs font-semibold text-blue-700">Source: {source.document_title} · {source.revision_label || `Version ${source.document_revision_id}`} · Page {source.page_number}{source.sheet_number ? ` · ${source.sheet_number}` : ""}</button>;
  return <div className="mt-3"><p className="text-xs font-semibold text-slate-500">Supporting sources: {sources.length}</p><div className="mt-2 flex flex-wrap gap-2">{sources.slice(0, 3).map(sourceButton)}</div>{sources.length > 3 && <details className="mt-2"><summary className="cursor-pointer text-xs font-semibold text-blue-700">Show all {sources.length} sources</summary><div className="mt-2 flex flex-wrap gap-2">{sources.slice(3).map(sourceButton)}</div></details>}</div>;
}

function previewResponsibility(value: string) {
  return responsibilityLabel(value);
}

function ScopeCard({
  item,
  canWrite,
  busy,
  onEdit,
  onReady,
  onViewSource,
}: {
  item: ScopePackage;
  canWrite: boolean;
  busy: boolean;
  onEdit: () => void;
  onReady: () => void;
  onViewSource: (source: ScopeItemSource) => void;
}) {
  const version = item.current_version;
  const workIncluded = version.scope_items
    .filter((scopeItem) => scopeItem.responsibility !== "unclear")
    .map((scopeItem) => scopeItem.description);
  const needsConfirmation = version.scope_items
    .filter((scopeItem) => scopeItem.responsibility === "unclear")
    .map((scopeItem) => scopeItem.description);
  return (
    <Card className="overflow-hidden border-slate-200 shadow-sm">
      <div className="flex flex-col gap-3 border-b bg-white px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-bold uppercase tracking-[.1em] text-blue-700">
              {item.trade_category}
            </span>
            <Status status={version.status} />
            <span className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-semibold text-slate-600">
              Version {version.version}
            </span>
            <span className="rounded-full bg-indigo-50 px-2 py-1 text-[10px] font-semibold text-indigo-700">
              {version.scope_items.length} detailed item
              {version.scope_items.length === 1 ? "" : "s"}
            </span>
          </div>
          <h3 className="mt-2 text-lg font-semibold text-slate-950">
            {version.title}
          </h3>
          <p className="mt-1 text-sm leading-6 text-slate-500">
            {version.description || "No scope description added."}
          </p>
        </div>
        {canWrite && (
          <div className="flex shrink-0 gap-2">
            <button
              type="button"
              onClick={onEdit}
              disabled={busy}
              className="inline-flex h-9 items-center gap-2 rounded-lg border bg-white px-3 text-sm font-semibold text-slate-700 hover:border-blue-200 hover:text-blue-700 disabled:opacity-50"
            >
              <Pencil className="h-4 w-4" />
              Edit
            </button>
            {version.status === "draft" && (
              <button
                type="button"
                onClick={onReady}
                disabled={busy}
                className="inline-flex h-9 items-center gap-2 rounded-lg bg-emerald-600 px-3 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                <BadgeCheck className="h-4 w-4" />
                Mark Ready
              </button>
            )}
          </div>
        )}
      </div>
      <details className="border-b bg-indigo-50/30 px-5 py-4">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-semibold text-indigo-950">
          <span>Detailed scope items ({version.scope_items.length})</span>
          <ChevronDown className="h-4 w-4" />
        </summary>
        <div className="mt-4 divide-y rounded-lg border bg-white">
          {version.scope_items.map((scopeItem) => (
            <article key={scopeItem.id} className="p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded bg-indigo-50 px-2 py-1 text-[10px] font-bold uppercase text-indigo-700">
                  {itemTypeLabel(scopeItem.item_type)}
                </span>
                <span className="rounded bg-slate-100 px-2 py-1 text-[10px] font-bold text-slate-600">
                  {responsibilityLabel(scopeItem.responsibility)}
                </span>
                {scopeItem.coordination_required && (
                  <span className="rounded bg-amber-100 px-2 py-1 text-[10px] font-bold text-amber-800">
                    Coordination required
                  </span>
                )}
                <h4 className="font-semibold text-slate-900">
                  {scopeItem.title}
                </h4>
              </div>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                {scopeItem.description}
              </p>
              <ScopeItemSources sources={scopeItem.sources} onViewSource={onViewSource} />
            </article>
          ))}
        </div>
      </details>
      <div className="grid gap-4 bg-slate-50/50 p-5 md:grid-cols-2 xl:grid-cols-4">
        <ItemList title="Work Included" items={workIncluded} tone="green" />
        <ItemList title="Needs Confirmation" items={needsConfirmation} tone="amber" />
        <ItemList title="Exclusions" items={version.exclusions} tone="red" />
        <ItemList
          title="Notes"
          items={version.clarifications}
          tone="blue"
        />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t bg-white px-5 py-3 text-xs text-slate-500">
        <span className="inline-flex items-center gap-1.5">
          <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
          Approved Project Information V{item.source_snapshot_version} ·{" "}
          {version.sources.length} source item
          {version.sources.length === 1 ? "" : "s"}
        </span>
        <details>
          <summary className="flex cursor-pointer list-none items-center gap-1 font-semibold text-blue-700">
            Version history ({item.versions.length})
            <ChevronDown className="h-3.5 w-3.5" />
          </summary>
          <div className="mt-2 space-y-1 text-right">
            {item.versions.map((history) => (
              <p key={history.id}>
                V{history.version} ·{" "}
                {history.status === "ready" ? "Ready" : "Draft"} ·{" "}
                {history.created_by} · {history.scope_items.length} items
              </p>
            ))}
          </div>
        </details>
      </div>
    </Card>
  );
}

function ScopeItemSources({
  sources,
  onViewSource,
}: {
  sources: ScopeItemSource[];
  onViewSource: (source: ScopeItemSource) => void;
}) {
  const sourceButton = (source: ScopeItemSource) => (
    <button
      key={source.id}
      type="button"
      onClick={() => onViewSource(source)}
      className="inline-flex items-center gap-1.5 rounded-lg border bg-white px-2.5 py-1.5 text-xs font-semibold text-blue-700 hover:border-blue-300"
    >
      <ExternalLink className="h-3.5 w-3.5" />
      {source.document_title} · {source.revision_label || `Version ${source.document_revision}`} · Page {source.page_number}
      {source.sheet_number ? ` · ${source.sheet_number}` : ""}
    </button>
  );
  return (
    <div className="mt-3">
      <p className="text-xs font-semibold text-slate-500">Supporting sources: {sources.length}</p>
      <div className="mt-2 flex flex-wrap gap-2">{sources.slice(0, 3).map(sourceButton)}</div>
      {sources.length > 3 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs font-semibold text-blue-700">Show all {sources.length} sources</summary>
          <div className="mt-2 flex flex-wrap gap-2">{sources.slice(3).map(sourceButton)}</div>
        </details>
      )}
    </div>
  );
}

function ScopeEditor({
  item,
  busy,
  onCancel,
  onSave,
}: {
  item: ScopePackage;
  busy: boolean;
  onCancel: () => void;
  onSave: (values: ScopePackageEdit) => void;
}) {
  const current = item.current_version;
  const [title, setTitle] = useState(current.title);
  const [description, setDescription] = useState(current.description);
  const [inclusions, setInclusions] = useState(
    itemsToLines(current.inclusions),
  );
  const [exclusions, setExclusions] = useState(
    itemsToLines(current.exclusions),
  );
  const [clarifications, setClarifications] = useState(
    itemsToLines(current.clarifications),
  );
  return (
    <Card className="border-blue-200 p-5 shadow-sm">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-wide text-blue-700">
            Editing {item.trade_category}
          </p>
          <h3 className="mt-1 font-semibold text-slate-900">
            Create Version {current.version + 1}
          </h3>
        </div>
        <button
          type="button"
          onClick={onCancel}
          aria-label="Close scope editor"
          className="rounded-lg p-2 text-slate-400 hover:bg-slate-100"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="mt-4 grid gap-4">
        <Field label="Title" value={title} onChange={setTitle} />
        <Area
          label="Description"
          value={description}
          onChange={setDescription}
          rows={3}
        />
        <div className="grid gap-4 lg:grid-cols-3">
          <Area
            label="Inclusions — one per line"
            value={inclusions}
            onChange={setInclusions}
          />
          <Area
            label="Exclusions — one per line"
            value={exclusions}
            onChange={setExclusions}
          />
          <Area
            label="Clarifications / notes — one per line"
            value={clarifications}
            onChange={setClarifications}
          />
        </div>
      </div>
      <div className="mt-5 flex justify-end gap-2 border-t pt-4">
        <button
          type="button"
          onClick={onCancel}
          disabled={busy}
          className="h-9 rounded-lg border bg-white px-3 text-sm font-semibold"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() =>
            onSave({
              title,
              description,
              inclusions: linesToItems(inclusions),
              exclusions: linesToItems(exclusions),
              clarifications: linesToItems(clarifications),
            })
          }
          disabled={busy || !title.trim()}
          className="inline-flex h-9 items-center gap-2 rounded-lg bg-[#173f5f] px-4 text-sm font-semibold text-white disabled:opacity-50"
        >
          {busy && <LoaderCircle className="h-4 w-4 animate-spin" />}Save New
          Version
        </button>
      </div>
    </Card>
  );
}

function ItemList({
  title,
  items,
  tone,
}: {
  title: string;
  items: string[];
  tone: "green" | "red" | "amber" | "blue";
}) {
  const dot = {
    green: "bg-emerald-500",
    red: "bg-red-500",
    amber: "bg-amber-500",
    blue: "bg-blue-500",
  }[tone];
  return (
    <section>
      <h4 className="text-xs font-bold uppercase tracking-wide text-slate-600">
        {title}
      </h4>
      {items.length ? (
        <ul className="mt-2 space-y-2">
          {items.map((item, index) => (
            <li
              key={`${item}-${index}`}
              className="flex gap-2 text-sm leading-5 text-slate-700"
            >
              <span
                className={`mt-2 h-1.5 w-1.5 shrink-0 rounded-full ${dot}`}
              />
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm italic text-slate-400">None recorded</p>
      )}
    </section>
  );
}
function Status({ status }: { status: "draft" | "ready" }) {
  return (
    <span
      className={`rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide ${status === "ready" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-200 bg-amber-50 text-amber-700"}`}
    >
      {status === "ready" ? "Ready" : "Draft"}
    </span>
  );
}
function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | string;
  tone: "blue" | "amber" | "green";
}) {
  const style = {
    blue: "border-t-blue-500",
    amber: "border-t-amber-500",
    green: "border-t-emerald-500",
  }[tone];
  return (
    <Card className={`border-t-4 bg-white p-4 ${style}`}>
      <p className="text-2xl font-semibold text-slate-950">{value}</p>
      <p className="text-xs font-semibold text-slate-500">{label}</p>
    </Card>
  );
}
function Notice({
  tone,
  message,
}: {
  tone: "error" | "success";
  message: string;
}) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={`flex items-start gap-2 rounded-xl border p-3 text-sm ${tone === "error" ? "border-red-200 bg-red-50 text-red-800" : "border-emerald-200 bg-emerald-50 text-emerald-800"}`}
    >
      {tone === "error" ? (
        <AlertCircle className="mt-0.5 h-4 w-4" />
      ) : (
        <BadgeCheck className="mt-0.5 h-4 w-4" />
      )}
      {message}
    </div>
  );
}
function State({
  title,
  detail,
  spin = false,
}: {
  title: string;
  detail: string;
  spin?: boolean;
}) {
  return (
    <section className="flex min-h-64 flex-col items-center justify-center rounded-xl border border-dashed bg-white px-6 text-center">
      <FileStack
        className={`h-8 w-8 text-slate-400 ${spin ? "animate-pulse" : ""}`}
      />
      <h3 className="mt-4 font-semibold text-slate-900">{title}</h3>
      <p className="mt-1 max-w-lg text-sm leading-6 text-slate-500">{detail}</p>
    </section>
  );
}
function Field({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="text-sm font-semibold text-slate-700">
      {label}
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 h-10 w-full rounded-lg border px-3 font-normal outline-none focus:border-blue-500"
      />
    </label>
  );
}
function Area({
  label,
  value,
  onChange,
  rows = 6,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  rows?: number;
}) {
  return (
    <label className="text-sm font-semibold text-slate-700">
      {label}
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        rows={rows}
        className="mt-1 w-full rounded-lg border px-3 py-2 font-normal outline-none focus:border-blue-500"
      />
    </label>
  );
}
