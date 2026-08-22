"use client";
import { useMemo, useState } from "react";
import {
  AlertTriangle,
  ClipboardCheck,
  PackageCheck,
  Plus,
  X,
} from "lucide-react";
import type {
  BidPackage,
  BidPackageReviewState,
  Project,
  ScopeItemCategory,
  TradeScopeDetail,
  TradeScopeItem,
  TradeScopeReview,
} from "@/types";
import { createBidPackage } from "@/data";
import { formatDate } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { SourceReference } from "@/components/ai-review/source-reference";
import { ConfidenceIndicator } from "@/components/ai-review/confidence-indicator";
import { ScopeStatusBadge } from "./scope-status-badge";
const blankReview: TradeScopeReview = {
  scopeItems: false,
  exclusions: false,
  clarifications: false,
  sources: false,
};
const blankPackageReview: BidPackageReviewState = {
  tradeScope: false,
  exclusions: false,
  bidDeadline: false,
  documentList: false,
  submissionInstructions: false,
};
const categories: ScopeItemCategory[] = [
  "Included Scope",
  "Exclusion",
  "Clarification",
  "Allowance",
  "Alternate",
  "General Requirement",
];
export function ScopeBuilder({
  project,
  initialScopes,
}: {
  project: Project;
  initialScopes: TradeScopeDetail[];
}) {
  const [scopes, setScopes] = useState(initialScopes);
  const [selectedId, setSelectedId] = useState(
    initialScopes[7]?.id ?? initialScopes[0]?.id ?? "",
  );
  const [editor, setEditor] = useState<{
    mode: "add" | "edit";
    item?: TradeScopeItem;
  } | null>(null);
  const [reviews, setReviews] = useState<Record<string, TradeScopeReview>>({});
  const [packages, setPackages] = useState<Record<string, BidPackage>>({});
  const [packagePreview, setPackagePreview] = useState(false);
  const [packageReview, setPackageReview] = useState<
    Record<string, BidPackageReviewState>
  >({});
  const scope = scopes.find((item) => item.id === selectedId);
  if (!scope)
    return (
      <div className="flex min-h-64 flex-col items-center justify-center text-center">
        <ClipboardCheck className="h-8 w-8 text-slate-400" />
        <h2 className="mt-4 text-xl font-semibold">Scopes Not Generated</h2>
        <p className="mt-1 max-w-md text-sm text-slate-500">
          Complete the AI review before preparing trade scopes for this project.
        </p>
      </div>
    );
  const review = reviews[scope.id] ?? blankReview;
  const reviewReady = Object.values(review).every(Boolean);
  const pkg = packages[scope.id];
  const pkgChecklist = packageReview[scope.id] ?? blankPackageReview;
  const pkgReady = Object.values(pkgChecklist).every(Boolean);
  const metrics = [
    { label: "Required Trades", value: scopes.length },
    { label: "Scopes Ready", value: scopes.length },
    {
      label: "Approved",
      value: scopes.filter((s) => s.status === "Approved").length,
    },
    {
      label: "Needs Review",
      value: scopes.filter((s) => s.status === "Needs Review").length,
    },
    {
      label: "Bid Packages Ready",
      value: scopes.filter((s) => s.packageStatus === "Approved for Outreach")
        .length,
    },
  ];
  const updateScope = (fn: (s: TradeScopeDetail) => TradeScopeDetail) =>
    setScopes((current) => current.map((s) => (s.id === scope.id ? fn(s) : s)));
  const saveItem = (description: string, category: ScopeItemCategory) => {
    if (editor?.mode === "edit" && editor.item) {
      updateScope((s) => ({
        ...s,
        status: "Human Revised",
        items: s.items.map((item) =>
          item.id === editor.item!.id
            ? {
                ...item,
                description,
                category,
                status: "Human Revised",
                humanModified: true,
                originalDescription:
                  item.originalDescription ?? item.description,
              }
            : item,
        ),
      }));
    } else {
      const item: TradeScopeItem = {
        id: `human-${scope.id}-${scope.items.length + 1}`,
        tradeId: scope.id,
        category,
        description,
        status: "Human Added",
        sources: [],
        humanModified: true,
      };
      updateScope((s) => ({
        ...s,
        status: "Human Revised",
        items: [...s.items, item],
      }));
    }
    setEditor(null);
  };
  const approveScope = () =>
    updateScope((s) => ({
      ...s,
      status: "Approved",
      approvedBy: "Alex Morgan · Estimator",
      approvedAt: "August 23, 2026 at 12:00 PM",
    }));
  const generate = () => {
    setPackages((current) => ({
      ...current,
      [scope.id]: createBidPackage(scope.id),
    }));
    setPackagePreview(true);
  };
  const approvePackage = () => {
    setPackages((current) => ({
      ...current,
      [scope.id]: { ...current[scope.id], status: "Approved for Outreach" },
    }));
    updateScope((s) => ({ ...s, packageStatus: "Approved for Outreach" }));
  };
  return (
    <div>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="text-xl font-semibold">Trade Scope Builder</h2>
          <p className="mt-1 text-sm text-slate-500">
            Review AI-assisted trade scopes before creating subcontractor bid
            packages.
          </p>
          <p className="mt-2 text-xs font-medium text-violet-700">
            Demo environment — trade scopes and package content shown here are
            simulated.
          </p>
        </div>
        <button
          onClick={() => setEditor({ mode: "add" })}
          className="inline-flex h-9 items-center gap-2 self-start rounded-lg bg-primary px-3 text-sm font-semibold text-white"
        >
          <Plus className="h-4 w-4" />
          Add Scope Item
        </button>
      </div>
      <section className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {metrics.map((item) => (
          <Card key={item.label} className="p-4">
            <p className="text-2xl font-semibold">{item.value}</p>
            <p className="mt-1 text-xs text-slate-500">{item.label}</p>
          </Card>
        ))}
      </section>
      <div className="mt-5 grid gap-5 xl:grid-cols-[300px_1fr]">
        <aside>
          <label className="block xl:hidden">
            <span className="mb-1.5 block text-sm font-medium">
              Select trade
            </span>
            <select
              value={selectedId}
              onChange={(e) => setSelectedId(e.target.value)}
              className="h-10 w-full rounded-lg border bg-white px-3 text-sm"
            >
              {scopes.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.trade} — {s.status}
                </option>
              ))}
            </select>
          </label>
          <Card className="hidden overflow-hidden xl:block">
            <div className="border-b px-4 py-3">
              <h3 className="text-sm font-semibold">Trade Coverage</h3>
              <p className="text-xs text-slate-500">Select a scope to review</p>
            </div>
            <nav aria-label="Trade scopes" className="divide-y">
              {scopes.map((s) => (
                <button
                  key={s.id}
                  onClick={() => setSelectedId(s.id)}
                  aria-current={s.id === scope.id ? "true" : undefined}
                  className={`w-full p-3 text-left ${s.id === scope.id ? "bg-blue-50" : "hover:bg-slate-50"}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold">{s.trade}</span>
                    <ScopeStatusBadge status={s.status} />
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    {s.items.length} items · {s.sourceCount} sources
                  </p>
                  <p className="mt-1 text-[11px] text-slate-500">
                    Package: {s.packageStatus}
                  </p>
                </button>
              ))}
            </nav>
          </Card>
        </aside>
        <main className="min-w-0 space-y-5">
          <Card>
            <div className="flex flex-col gap-4 border-b p-5 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-lg font-semibold">{scope.trade}</h3>
                  <ScopeStatusBadge status={scope.status} />
                  <ScopeStatusBadge
                    status={pkg?.status ?? scope.packageStatus}
                  />
                </div>
                <p className="mt-1 text-sm text-slate-500">
                  AI-assisted scope · {scope.confidence}% estimated confidence ·{" "}
                  {scope.sourceCount} source references
                </p>
              </div>
              {scope.status === "Approved" ? (
                <div className="text-right">
                  <p className="text-xs font-semibold text-emerald-700">
                    Approved
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    {scope.approvedBy}
                  </p>
                  <button
                    onClick={() =>
                      updateScope((s) => ({
                        ...s,
                        status: "Ready for Approval",
                      }))
                    }
                    className="mt-2 text-xs font-semibold text-blue-700 hover:underline"
                  >
                    Reopen Review
                  </button>
                </div>
              ) : null}
            </div>
            {scope.warnings.length > 0 && (
              <div className="border-b bg-amber-50/60 p-4">
                <p className="flex items-center gap-2 text-sm font-semibold text-amber-900">
                  <AlertTriangle className="h-4 w-4" />
                  Scope warnings requiring human review
                </p>
                <div className="mt-3 space-y-2">
                  {scope.warnings.map((w) => (
                    <label
                      key={w.id}
                      className="flex items-center gap-3 text-sm text-amber-900"
                    >
                      <input type="checkbox" className="accent-amber-700" />
                      {w.message}
                    </label>
                  ))}
                </div>
              </div>
            )}
            <ScopeSections
              items={scope.items}
              onEdit={(item) => setEditor({ mode: "edit", item })}
              onToggle={(item) =>
                updateScope((s) => ({
                  ...s,
                  items: s.items.map((i) =>
                    i.id === item.id
                      ? {
                          ...i,
                          status:
                            i.status === "Removed"
                              ? i.humanModified
                                ? "Human Added"
                                : "AI Generated"
                              : "Removed",
                        }
                      : i,
                  ),
                }))
              }
            />
          </Card>
          <Card>
            <div className="grid lg:grid-cols-[1fr_310px]">
              <div className="p-5">
                <h3 className="font-semibold">Estimator Review Checklist</h3>
                <p className="mt-1 text-xs text-slate-500">
                  Production approval will be recorded in the project audit
                  trail.
                </p>
                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                  {Object.entries({
                    scopeItems: "Scope items reviewed",
                    exclusions: "Potential exclusions reviewed",
                    clarifications: "Clarifications reviewed",
                    sources: "Sources checked",
                  }).map(([key, label]) => (
                    <label
                      key={key}
                      className="flex items-center gap-3 rounded-lg border p-3 text-sm"
                    >
                      <input
                        type="checkbox"
                        checked={review[key as keyof TradeScopeReview]}
                        onChange={(e) =>
                          setReviews((v) => ({
                            ...v,
                            [scope.id]: { ...review, [key]: e.target.checked },
                          }))
                        }
                      />
                      {label}
                    </label>
                  ))}
                </div>
              </div>
              <div className="border-t bg-slate-50 p-5 lg:border-l lg:border-t-0">
                {scope.status !== "Approved" ? (
                  <button
                    disabled={!reviewReady}
                    onClick={approveScope}
                    className="w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-40"
                  >
                    Approve Trade Scope
                  </button>
                ) : (
                  <>
                    <p className="text-sm font-semibold text-emerald-700">
                      Scope approved for package preparation
                    </p>
                    <button
                      onClick={generate}
                      className="mt-4 w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white"
                    >
                      {pkg ? "Preview Bid Package" : "Generate Bid Package"}
                    </button>
                  </>
                )}
              </div>
            </div>
          </Card>
        </main>
      </div>
      {editor && (
        <ItemEditor
          item={editor.item}
          onClose={() => setEditor(null)}
          onSave={saveItem}
        />
      )}{" "}
      {packagePreview && pkg && (
        <PackagePreview
          project={project}
          scope={scope}
          pkg={pkg}
          review={pkgChecklist}
          onReview={(next) =>
            setPackageReview((v) => ({ ...v, [scope.id]: next }))
          }
          onDocuments={(documents) =>
            setPackages((v) => ({ ...v, [scope.id]: { ...pkg, documents } }))
          }
          onApprove={approvePackage}
          ready={pkgReady}
          onClose={() => setPackagePreview(false)}
        />
      )}
    </div>
  );
}
function ScopeSections({
  items,
  onEdit,
  onToggle,
}: {
  items: TradeScopeItem[];
  onEdit: (i: TradeScopeItem) => void;
  onToggle: (i: TradeScopeItem) => void;
}) {
  const groups = useMemo(
    () =>
      categories
        .map((category) => ({
          category,
          items: items.filter((i) => i.category === category),
        }))
        .filter((group) => group.items.length),
    [items],
  );
  return (
    <div>
      {groups.map((group) => (
        <section key={group.category} className="border-b last:border-0">
          <h4 className="bg-slate-50 px-5 py-3 text-xs font-semibold uppercase tracking-wider text-slate-600">
            {group.category}
          </h4>
          <div className="divide-y">
            {group.items.map((item) => (
              <article
                key={item.id}
                className={`p-4 ${item.status === "Removed" ? "opacity-50" : ""}`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <p
                      className={`text-sm leading-6 ${item.status === "Removed" ? "line-through" : ""}`}
                    >
                      {item.description}
                    </p>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <span className="rounded bg-slate-100 px-2 py-1 text-[10px] font-semibold">
                        {item.status}
                      </span>
                      {item.status === "Human Added" && (
                        <span className="text-xs text-slate-500">
                          Human Added — no AI source
                        </span>
                      )}
                      {item.originalDescription && (
                        <details>
                          <summary className="cursor-pointer text-xs font-medium text-blue-700">
                            Original AI wording
                          </summary>
                          <p className="mt-1 text-xs text-slate-500">
                            {item.originalDescription}
                          </p>
                        </details>
                      )}
                      {item.confidence && (
                        <ConfidenceIndicator value={item.confidence} />
                      )}
                    </div>
                    {item.sources.map((source, index) => (
                      <SourceReference
                        key={`${source.documentId}-${index}`}
                        source={source}
                      />
                    ))}
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <button
                      onClick={() => onEdit(item)}
                      disabled={item.status === "Removed"}
                      className="text-xs font-semibold text-blue-700 disabled:opacity-40"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => onToggle(item)}
                      className="text-xs font-semibold text-slate-600"
                    >
                      {item.status === "Removed" ? "Restore" : "Remove"}
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
function ItemEditor({
  item,
  onClose,
  onSave,
}: {
  item?: TradeScopeItem;
  onClose: () => void;
  onSave: (d: string, c: ScopeItemCategory) => void;
}) {
  const [description, setDescription] = useState(item?.description ?? "");
  const [category, setCategory] = useState<ScopeItemCategory>(
    item?.category ?? "Included Scope",
  );
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={item ? "Edit scope item" : "Add scope item"}
    >
      <div className="w-full max-w-xl rounded-xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b p-4">
          <h2 className="font-semibold">
            {item ? "Edit Scope Item" : "Add Scope Item"}
          </h2>
          <button
            onClick={onClose}
            aria-label="Close scope item editor"
            className="p-2"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="space-y-4 p-5">
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium">Category</span>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value as ScopeItemCategory)}
              className="h-10 w-full rounded-lg border px-3 text-sm"
            >
              {categories.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium">
              Scope description
            </span>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={5}
              className="w-full rounded-lg border p-3 text-sm"
            />
          </label>
          {item && (
            <p className="text-xs text-slate-500">
              Source references will remain unchanged.
            </p>
          )}
        </div>
        <div className="flex justify-end gap-2 border-t p-4">
          <button
            onClick={onClose}
            className="rounded-lg border px-4 py-2 text-sm font-semibold"
          >
            Cancel
          </button>
          <button
            disabled={!description.trim()}
            onClick={() => onSave(description, category)}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
          >
            Save Scope Item
          </button>
        </div>
      </div>
    </div>
  );
}

function PackagePreview({
  project,
  scope,
  pkg,
  review,
  onReview,
  onDocuments,
  onApprove,
  ready,
  onClose,
}: {
  project: Project;
  scope: TradeScopeDetail;
  pkg: BidPackage;
  review: BidPackageReviewState;
  onReview: (v: BidPackageReviewState) => void;
  onDocuments: (v: BidPackage["documents"]) => void;
  onApprove: () => void;
  ready: boolean;
  onClose: () => void;
}) {
  const included = scope.items.filter(
    (item) => item.status !== "Removed" && item.category === "Included Scope",
  );
  const clarifications = scope.items.filter(
    (item) =>
      item.status !== "Removed" &&
      ["Exclusion", "Clarification", "Allowance", "Alternate"].includes(
        item.category,
      ),
  );
  const sources = [
    ...new Set(
      included.flatMap((item) =>
        item.sources.map(
          (source) =>
            `${source.documentName}${source.sheetNumber ? ` — ${source.sheetNumber}` : ""}`,
        ),
      ),
    ),
  ];
  return (
    <div
      className="fixed inset-0 z-50 bg-slate-950/50 p-3 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-label="Bid package preview"
    >
      <div className="mx-auto flex h-full max-w-6xl flex-col overflow-hidden rounded-xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b px-5 py-4">
          <div>
            <h2 className="font-semibold">Bid Package Preview</h2>
            <p className="text-xs text-slate-500">
              Temporary demo package · no PDF is generated
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close bid package preview"
            className="p-2"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="grid min-h-0 flex-1 overflow-y-auto lg:grid-cols-[1fr_330px]">
          <article className="p-5 sm:p-8">
            <div className="border-b border-slate-900 pb-5">
              <p className="text-sm font-bold tracking-[.14em]">BB BUILDERS</p>
              <h3 className="mt-2 text-xl font-semibold">
                REQUEST FOR SUBCONTRACTOR BID
              </h3>
              <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2">
                {[
                  ["Project", project.name],
                  ["Project Number", project.projectNumber],
                  ["Location", `${project.city}, ${project.province}`],
                  ["Trade", scope.trade],
                  ["Bid Due", formatDate(project.bidDeadline)],
                  ["Questions Due", formatDate(project.questionsDeadline)],
                ].map(([k, v]) => (
                  <div key={k}>
                    <dt className="text-xs text-slate-500">{k}</dt>
                    <dd className="font-medium">{v}</dd>
                  </div>
                ))}
              </dl>
            </div>
            <PackageSection title="Project Summary">
              <p>
                Retail tenant improvement project requiring coordinated trade
                pricing based on the listed tender documents and approved trade
                scope.
              </p>
            </PackageSection>
            <PackageSection title="Trade Scope of Work">
              <ol className="list-decimal space-y-2 pl-5">
                {included.map((item) => (
                  <li key={item.id}>{item.description}</li>
                ))}
              </ol>
            </PackageSection>
            {clarifications.length > 0 && (
              <PackageSection title="Potential Exclusions / Clarifications">
                <ul className="list-disc space-y-2 pl-5">
                  {clarifications.map((item) => (
                    <li key={item.id}>{item.description}</li>
                  ))}
                </ul>
              </PackageSection>
            )}
            <PackageSection title="Drawing / Specification References">
              <ul className="space-y-1">
                {sources.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </PackageSection>
            <PackageSection title="Bid Requirements">
              <ul className="list-disc space-y-1 pl-5">
                {pkg.requirements.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </PackageSection>
            <PackageSection title="Submission Instructions">
              <ul className="list-disc space-y-1 pl-5">
                {pkg.submissionInstructions.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
              <p className="mt-3 text-xs text-slate-500">
                Demo submission destination will be configured in production.
              </p>
            </PackageSection>
          </article>
          <aside className="border-t bg-slate-50 p-5 lg:border-l lg:border-t-0">
            <h3 className="font-semibold">Package Documents</h3>
            <p className="mt-1 text-xs text-slate-500">
              Select documents that would be shared.
            </p>
            <div className="mt-3 space-y-2">
              {pkg.documents.map((document, index) => (
                <label
                  key={document.documentId}
                  className="flex items-start gap-3 rounded-lg border bg-white p-3 text-sm"
                >
                  <input
                    type="checkbox"
                    checked={document.included}
                    onChange={(e) =>
                      onDocuments(
                        pkg.documents.map((item, i) =>
                          i === index
                            ? { ...item, included: e.target.checked }
                            : item,
                        ),
                      )
                    }
                  />
                  {document.documentName}
                </label>
              ))}
            </div>
            <h3 className="mt-6 font-semibold">Package Review</h3>
            <div className="mt-3 space-y-2">
              {Object.entries({
                tradeScope: "Trade scope reviewed",
                exclusions: "Exclusions reviewed",
                bidDeadline: "Bid deadline confirmed",
                documentList: "Document list confirmed",
                submissionInstructions: "Submission instructions confirmed",
              }).map(([key, label]) => (
                <label
                  key={key}
                  className="flex items-center gap-3 rounded-lg border bg-white p-3 text-sm"
                >
                  <input
                    type="checkbox"
                    checked={review[key as keyof BidPackageReviewState]}
                    onChange={(e) =>
                      onReview({ ...review, [key]: e.target.checked })
                    }
                  />
                  {label}
                </label>
              ))}
            </div>
            <button
              disabled={!ready || pkg.status === "Approved for Outreach"}
              onClick={onApprove}
              className="mt-5 w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-40"
            >
              {pkg.status === "Approved for Outreach"
                ? "Ready for Contractor Outreach"
                : "Approve Bid Package"}
            </button>
            {pkg.status === "Approved for Outreach" && (
              <p className="mt-3 flex items-center gap-2 text-sm font-semibold text-emerald-700">
                <PackageCheck className="h-4 w-4" />
                Approved for Outreach
              </p>
            )}
          </aside>
        </div>
      </div>
    </div>
  );
}
function PackageSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border-b py-5 text-sm leading-6 last:border-0">
      <h4 className="mb-3 text-xs font-bold uppercase tracking-wider text-slate-600">
        {title}
      </h4>
      {children}
    </section>
  );
}
