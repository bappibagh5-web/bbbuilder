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
  linesToItems,
  replaceScopePackage,
  scopeItemCount,
  scopePackageCounts,
  scopePackageGenerations,
} from "@/lib/scope-package-state";
import {
  scopePackagesApi,
  type ScopeItemSource,
  type ScopePackage,
  type ScopePackageEdit,
} from "@/lib/scope-packages";
import { documentsApi } from "@/lib/documents";
import { sourcePdfViewerUrl } from "@/lib/document-source-navigation";
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

  async function generate() {
    if (!latestApproved || !canWrite || busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await scopePackagesApi.generate(
        slug,
        project.id,
        latestApproved.id,
      );
      await load();
      setNotice(
        result.created_count
          ? `${result.created_count} draft scope package${result.created_count === 1 ? "" : "s"} created from approved Project Information Version ${latestApproved.version}.`
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
        {latestApproved && canWrite && (
          <button
            type="button"
            onClick={() => void generate()}
            disabled={busy}
            className="inline-flex h-10 items-center justify-center gap-2 self-start rounded-lg bg-[#173f5f] px-4 text-sm font-semibold text-white shadow-sm hover:bg-[#102f49] disabled:opacity-50"
          >
            <Sparkles className="h-4 w-4" />
            {busy
              ? "Working…"
              : packages.some(
                    (item) => item.source_snapshot === latestApproved.id,
                  )
                ? "Check Approved Version"
                : "Generate Draft Scopes"}
          </button>
        )}
      </div>
      {error && <Notice tone="error" message={error} />}
      {notice && <Notice tone="success" message={notice} />}
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
                  {scopeItem.item_type.replaceAll("_", " ")}
                </span>
                <span className="rounded bg-slate-100 px-2 py-1 text-[10px] font-bold text-slate-600">
                  {scopeItem.responsibility.replaceAll("_", " ")}
                </span>
                <h4 className="font-semibold text-slate-900">
                  {scopeItem.title}
                </h4>
              </div>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                {scopeItem.description}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {scopeItem.sources.map((source) => (
                  <button
                    key={source.id}
                    type="button"
                    onClick={() => onViewSource(source)}
                    className="inline-flex items-center gap-1.5 rounded-lg border bg-white px-2.5 py-1.5 text-xs font-semibold text-blue-700 hover:border-blue-300"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                    {source.document_title} ·{" "}
                    {source.revision_label ||
                      `Version ${source.document_revision}`}{" "}
                    · Page {source.page_number}
                    {source.sheet_number ? ` · ${source.sheet_number}` : ""}
                  </button>
                ))}
              </div>
            </article>
          ))}
        </div>
      </details>
      <div className="grid gap-4 bg-slate-50/50 p-5 lg:grid-cols-3">
        <ItemList title="Inclusions" items={version.inclusions} tone="green" />
        <ItemList title="Exclusions" items={version.exclusions} tone="red" />
        <ItemList
          title="Clarifications & Notes"
          items={version.clarifications}
          tone="amber"
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
  tone: "green" | "red" | "amber";
}) {
  const dot = {
    green: "bg-emerald-500",
    red: "bg-red-500",
    amber: "bg-amber-500",
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
  value: number;
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
