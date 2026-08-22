"use client";
import { useMemo, useState } from "react";
import {
  CheckCircle2,
  Edit3,
  FileSearch,
  Info,
  ShieldCheck,
  X,
} from "lucide-react";
import type {
  AIExtractedField,
  AIReviewApprovalState,
  AIReviewData,
} from "@/types";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { ConfidenceIndicator } from "./confidence-indicator";
import { SourceReference } from "./source-reference";
const initialChecklist: AIReviewApprovalState = {
  projectInformation: false,
  requiredTrades: false,
  scopeObservations: false,
  riskItems: false,
  potentialExclusions: false,
};
export function AIReviewModule({ review }: { review: AIReviewData }) {
  const [fields, setFields] = useState(review.fields);
  const [included, setIncluded] = useState(
    () => new Set(review.trades.map((t) => t.id)),
  );
  const [reviewedRisks, setReviewedRisks] = useState(new Set<string>());
  const [checklist, setChecklist] = useState(initialChecklist);
  const [approved, setApproved] = useState(
    review.status === "Review Approved",
  );
  const [editing, setEditing] = useState(false);
  const allChecked = Object.values(checklist).every(Boolean);
  const revised = useMemo(
    () =>
      new Map(
        fields
          .filter((f) => (f as RevisedField).originalValue)
          .map((f) => [f.id, (f as RevisedField).originalValue!]),
      ),
    [fields],
  );
  if (review.status === "Awaiting Documents")
    return (
      <div className="flex min-h-64 flex-col items-center justify-center text-center">
        <FileSearch className="h-8 w-8 text-slate-400" />
        <h2 className="mt-4 text-xl font-semibold">Awaiting Documents</h2>
        <p className="mt-1 max-w-md text-sm text-slate-500">
          Add project documents before starting the demo AI review workflow.
        </p>
      </div>
    );
  const metrics = [
    { label: "Documents Analyzed", value: review.documentsAnalyzed },
    { label: "Drawing Sheets Reviewed", value: review.drawingSheetsReviewed },
    { label: "AI Findings", value: review.findingsCount },
    { label: "Items Requiring Attention", value: review.attentionCount },
    { label: "Overall AI Confidence", value: `${review.overallConfidence}%` },
  ];
  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-xl font-semibold">AI Document Review</h2>
            <span
              className={cn(
                "rounded-md px-2 py-1 text-xs font-semibold",
                approved
                  ? "bg-emerald-50 text-emerald-700"
                  : "bg-amber-50 text-amber-800",
              )}
            >
              {approved ? "AI Review Approved" : "Ready for Human Review"}
            </span>
          </div>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-500">
            AI-generated findings must be reviewed before they are used to
            create subcontractor bid packages.
          </p>
          <p className="mt-2 text-xs font-medium text-violet-700">
            Demo environment — findings and review history shown here are
            simulated.
          </p>
        </div>
        <button
          onClick={() => setEditing(true)}
          className="inline-flex h-9 items-center gap-2 self-start rounded-lg border bg-white px-3 text-sm font-semibold"
        >
          <Edit3 className="h-4 w-4" />
          Edit Findings
        </button>
      </div>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {metrics.map((item) => (
          <Card key={item.label} className="p-4">
            <p className="text-2xl font-semibold">{item.value}</p>
            <p className="mt-1 text-xs text-slate-500">{item.label}</p>
          </Card>
        ))}
      </section>
      <p className="flex items-start gap-2 rounded-lg bg-slate-100 p-3 text-xs leading-5 text-slate-600">
        <Info className="mt-0.5 h-4 w-4 shrink-0" />
        AI confidence is an estimated indicator used to prioritize human review.
        It does not guarantee accuracy.
      </p>
      <Card>
        <SectionHeader
          title="Project Intelligence"
          subtitle="Structured fields extracted for estimator review"
        />
        <div className="grid sm:grid-cols-2 xl:grid-cols-3">
          {fields.map((field) => (
            <ExtractedField
              key={field.id}
              field={field}
              original={revised.get(field.id)}
            />
          ))}
        </div>
        <div className="border-t p-4">
          <p className="text-xs font-medium text-slate-500">
            Detected disciplines
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {review.disciplines.map((d) => (
              <span
                key={d}
                className="rounded-md bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-700"
              >
                {d}
              </span>
            ))}
          </div>
        </div>
      </Card>
      <Card>
        <SectionHeader
          title="AI Identified Trades"
          subtitle="Human operator inclusion decisions are temporary"
        />
        <div className="grid sm:grid-cols-2">
          {review.trades.map((trade) => {
            const active = included.has(trade.id);
            return (
              <div
                key={trade.id}
                className="flex items-center justify-between gap-3 border-b p-4 sm:odd:border-r"
              >
                <div>
                  <p className="text-sm font-semibold">{trade.trade}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    {trade.confidence}% confidence · {trade.sourceCount} sources
                    · Recommended
                  </p>
                </div>
                <button
                  onClick={() =>
                    setIncluded((current) => {
                      const next = new Set(current);
                      if (active) {
                        next.delete(trade.id);
                      } else {
                        next.add(trade.id);
                      }
                      return next;
                    })
                  }
                  aria-pressed={active}
                  className={cn(
                    "rounded-lg border px-3 py-2 text-xs font-semibold",
                    active
                      ? "border-emerald-300 bg-emerald-50 text-emerald-700"
                      : "bg-white text-slate-600",
                  )}
                >
                  {active ? "Included" : "Excluded"}
                </button>
              </div>
            );
          })}
        </div>
        <p className="p-4 text-xs text-slate-500">
          Demo review changes are not persisted.
        </p>
      </Card>
      <Card>
        <SectionHeader
          title="Key Scope Observations"
          subtitle="AI-detected observations with demo source provenance"
        />
        <div className="divide-y">
          {review.observations.map((item) => (
            <article
              key={item.id}
              className="grid gap-3 p-4 lg:grid-cols-[150px_1fr_170px]"
            >
              <div>
                <span className="rounded-md bg-slate-100 px-2 py-1 text-xs font-semibold">
                  {item.category}
                </span>
              </div>
              <div>
                <p className="text-sm font-medium">{item.finding}</p>
                <SourceReference source={item.source} />
              </div>
              <ConfidenceIndicator value={item.confidence} />
            </article>
          ))}
        </div>
      </Card>
      <div className="grid gap-5 xl:grid-cols-[1.25fr_.75fr]">
        <Card>
          <SectionHeader
            title="Items Requiring Attention"
            subtitle="AI cannot resolve these items without human judgment"
          />
          <div className="divide-y">
            {review.risks.map((risk) => {
              const done = reviewedRisks.has(risk.id);
              return (
                <article key={risk.id} className="p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-sm font-semibold">{risk.title}</h3>
                        <span
                          className={cn(
                            "rounded px-2 py-0.5 text-[11px] font-semibold",
                            risk.severity === "High"
                              ? "bg-red-50 text-red-700"
                              : "bg-amber-50 text-amber-800",
                          )}
                        >
                          {risk.severity} severity
                        </span>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-slate-600">
                        {risk.reason}
                      </p>
                      <SourceReference source={risk.source} />
                    </div>
                    <button
                      onClick={() =>
                        setReviewedRisks((current) => {
                          const next = new Set(current);
                          if (done) {
                            next.delete(risk.id);
                          } else {
                            next.add(risk.id);
                          }
                          return next;
                        })
                      }
                      className={cn(
                        "shrink-0 rounded-lg border px-3 py-2 text-xs font-semibold",
                        done && "bg-emerald-50 text-emerald-700",
                      )}
                    >
                      {done ? "Reviewed" : "Mark Reviewed"}
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        </Card>
        <Card>
          <SectionHeader
            title="Possible Exclusions / Clarifications"
            subtitle="Possibilities only — not contractual exclusions"
          />
          <ul className="divide-y">
            {review.exclusions.map((item) => (
              <li key={item.id} className="p-4">
                <p className="text-sm font-semibold">{item.label}</p>
                <div className="mt-1 flex gap-2 text-[11px]">
                  <span className="rounded bg-slate-100 px-2 py-1">
                    {item.status}
                  </span>
                  <span className="rounded bg-amber-50 px-2 py-1 text-amber-800">
                    Needs Confirmation
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      </div>
      <Card className="border-slate-300">
        <div className="grid lg:grid-cols-[1fr_340px]">
          <div className="p-5">
            <div className="flex items-center gap-3">
              <ShieldCheck className="h-5 w-5 text-primary" />
              <div>
                <h2 className="font-semibold">AI Review Status</h2>
                <p className="text-xs text-slate-500">
                  {approved
                    ? "Approved with human oversight"
                    : "Ready for Human Review"}
                </p>
              </div>
            </div>
            {approved ? (
              <div className="mt-5 rounded-lg bg-emerald-50 p-4">
                <p className="flex items-center gap-2 font-semibold text-emerald-800">
                  <CheckCircle2 className="h-5 w-5" />
                  AI Review Approved
                </p>
                <p className="mt-2 text-sm text-emerald-800">
                  Approved by Alex Morgan · Estimator
                </p>
                <p className="mt-1 text-xs text-emerald-700">
                  Demo timestamp: August 23, 2026 at 12:00 PM
                </p>
                <p className="mt-3 text-xs leading-5 text-emerald-800">
                  In production, this approval will be stored in the project
                  audit trail before trade scopes can be generated.
                </p>
              </div>
            ) : (
              <div className="mt-5 space-y-2">
                {Object.entries({
                  projectInformation: "Project information reviewed",
                  requiredTrades: "Required trades reviewed",
                  scopeObservations: "Scope observations reviewed",
                  riskItems: "Risk items reviewed",
                  potentialExclusions: "Potential exclusions reviewed",
                }).map(([key, label]) => (
                  <label
                    key={key}
                    className="flex cursor-pointer items-center gap-3 rounded-lg border p-3 text-sm"
                  >
                    <input
                      type="checkbox"
                      checked={checklist[key as keyof AIReviewApprovalState]}
                      onChange={(e) =>
                        setChecklist((v) => ({ ...v, [key]: e.target.checked }))
                      }
                      className="h-4 w-4 accent-[#163451]"
                    />
                    {label}
                  </label>
                ))}
              </div>
            )}
          </div>
          <div className="border-t bg-slate-50 p-5 lg:border-l lg:border-t-0">
            <p className="text-sm font-semibold">Human approval required</p>
            <p className="mt-2 text-xs leading-5 text-slate-500">
              All review areas must be acknowledged before these findings can
              inform trade scopes.
            </p>
            <button
              disabled={!allChecked || approved}
              onClick={() => setApproved(true)}
              className="mt-5 w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              {approved ? "Review Approved" : "Approve AI Review"}
            </button>
          </div>
        </div>
      </Card>
      {editing && (
        <EditModal
          fields={fields}
          onSave={setFields}
          onClose={() => setEditing(false)}
        />
      )}
    </div>
  );
}
type RevisedField = AIExtractedField & { originalValue?: string };
function ExtractedField({
  field,
  original,
}: {
  field: AIExtractedField;
  original?: string;
}) {
  return (
    <div className="border-b p-4 sm:odd:border-r">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs text-slate-500">{field.label}</p>
          <p className="mt-1 text-sm font-semibold">{field.value}</p>
        </div>
        <ConfidenceIndicator value={field.confidence} />
      </div>
      {original && (
        <div className="mt-2">
          <span className="rounded bg-blue-50 px-2 py-1 text-[10px] font-semibold text-blue-700">
            Human Revised
          </span>
          <p className="mt-2 text-xs text-slate-500">
            AI extracted: {original}
          </p>
        </div>
      )}
      <SourceReference source={field.source} />
    </div>
  );
}
function SectionHeader({
  title,
  subtitle,
}: {
  title: string;
  subtitle: string;
}) {
  return (
    <div className="border-b px-5 py-4">
      <h2 className="font-semibold">{title}</h2>
      <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>
    </div>
  );
}
function EditModal({
  fields,
  onSave,
  onClose,
}: {
  fields: AIExtractedField[];
  onSave: (f: AIExtractedField[]) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState(fields);
  const save = () => {
    onSave(
      draft.map((field, index) =>
        field.value !== fields[index].value
          ? {
              ...field,
              originalValue:
                (fields[index] as RevisedField).originalValue ??
                fields[index].value,
            }
          : field,
      ),
    );
    onClose();
  };
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Edit findings"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4"
    >
      <div className="w-full max-w-xl rounded-xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b p-4">
          <h2 className="font-semibold">Edit Human-Reviewable Findings</h2>
          <button
            onClick={onClose}
            aria-label="Close edit findings"
            className="p-2"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="space-y-4 p-5">
          {draft.map(
            (field, index) =>
              field.editable && (
                <label key={field.id} className="block">
                  <span className="mb-1.5 block text-sm font-medium">
                    {field.label}
                  </span>
                  <input
                    value={field.value}
                    onChange={(e) =>
                      setDraft((current) =>
                        current.map((item, i) =>
                          i === index
                            ? { ...item, value: e.target.value }
                            : item,
                        ),
                      )
                    }
                    className="h-10 w-full rounded-lg border px-3 text-sm"
                  />
                  <p className="mt-1 text-xs text-slate-500">
                    Source reference remains unchanged.
                  </p>
                </label>
              ),
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
            onClick={save}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white"
          >
            Save Human Revisions
          </button>
        </div>
      </div>
    </div>
  );
}
