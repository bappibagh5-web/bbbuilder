"use client";

import Link from "next/link";
import { FormEvent, useMemo, useState } from "react";
import {
  AlertTriangle,
  FileText,
  Plus,
  Search,
  X,
} from "lucide-react";
import type {
  BidOpportunity,
  OpportunityDecisionReason,
  OpportunityReviewChecklist,
} from "@/types";
import { formatDate } from "@/lib/utils";
import { DemoNotice } from "@/components/demo-notice";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

const declineReasons: OpportunityDecisionReason[] = [
  "Not enough bidding time",
  "Outside service area",
  "Project type not a fit",
  "Insufficient capacity",
  "Insufficient information",
  "Commercial risk",
  "Client / relationship decision",
  "Other",
];
const checklistLabels: Array<[keyof OpportunityReviewChecklist, string]> = [
  ["details", "Opportunity details reviewed"],
  ["deadline", "Bid deadline reviewed"],
  ["documents", "Documents reviewed"],
  ["risks", "Initial risks reviewed"],
  ["capacity", "Capacity considered"],
];
const initialChecklist: OpportunityReviewChecklist = {
  details: false,
  deadline: false,
  documents: false,
  risks: false,
  capacity: false,
};

function StatusBadge({ status }: { status: BidOpportunity["status"] }) {
  const styles =
    status === "Converted to Project" || status === "Pursue"
      ? "bg-emerald-50 text-emerald-800"
      : status === "Declined"
        ? "bg-red-50 text-red-700"
        : status === "Reviewing"
          ? "bg-blue-50 text-blue-700"
          : "bg-slate-100 text-slate-700";
  return (
    <span
      className={`inline-flex whitespace-nowrap rounded-md px-2 py-1 text-xs font-semibold ${styles}`}
    >
      {status}
    </span>
  );
}

function HowItWorks() {
  const steps = [
    [
      "Opportunity Received",
      "A client or construction partner sends a bid invitation, project details, and documents.",
    ],
    [
      "Initial Review",
      "BB Builders reviews location, deadline, project type, documents, size, and trade requirements.",
    ],
    [
      "AI-Assisted Intake",
      "A future production system can summarize documents, identify likely trades, and flag missing information.",
    ],
    [
      "Go / No-Go Decision",
      "A BB Builders estimator decides whether the opportunity is worth pursuing.",
    ],
    [
      "Convert to Project",
      "Approved opportunities enter the full Documents-to-Client Proposal workflow.",
    ],
  ];
  return (
    <Card className="p-5 xl:sticky xl:top-24">
      <h2 className="font-semibold text-slate-900">
        How Bid Opportunities Work
      </h2>
      <ol className="mt-4 space-y-4">
        {steps.map(([title, text], index) => (
          <li key={title} className="flex gap-3">
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-slate-100 text-xs font-bold text-slate-600">
              {index + 1}
            </span>
            <div>
              <h3 className="text-sm font-semibold">{title}</h3>
              <p className="mt-0.5 text-xs leading-5 text-slate-500">{text}</p>
            </div>
          </li>
        ))}
      </ol>
      <p className="mt-5 rounded-lg bg-blue-50 p-3 text-xs font-semibold leading-5 text-blue-900">
        Human decision required — AI assists with intake, but BB Builders
        decides whether to pursue the opportunity.
      </p>
    </Card>
  );
}

export function BidOpportunitiesModule({
  initialItems,
}: {
  initialItems: BidOpportunity[];
}) {
  const [items, setItems] = useState(initialItems);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("All statuses");
  const [type, setType] = useState("All project types");
  const [selected, setSelected] = useState<BidOpportunity | null>(null);
  const [adding, setAdding] = useState(false);
  const [checklist, setChecklist] = useState(initialChecklist);
  const [reviewedRisks, setReviewedRisks] = useState(new Set<string>());
  const [decisionMode, setDecisionMode] = useState<"pursue" | "decline" | null>(
    null,
  );
  const [declineReason, setDeclineReason] = useState<OpportunityDecisionReason>(
    "Not enough bidding time",
  );
  const [declineNotes, setDeclineNotes] = useState("");
  const [converted, setConverted] = useState(false);
  const visible = useMemo(
    () =>
      items.filter(
        (item) =>
          `${item.name} ${item.client} ${item.city}`
            .toLowerCase()
            .includes(search.toLowerCase()) &&
          (status === "All statuses" || item.status === status) &&
          (type === "All project types" || item.projectType === type),
      ),
    [items, search, status, type],
  );
  const types = [...new Set(items.map((item) => item.projectType))];
  const openDetail = (item: BidOpportunity) => {
    setSelected(item);
    setChecklist(initialChecklist);
    setReviewedRisks(new Set());
    setDecisionMode(null);
    setConverted(false);
  };
  const updateSelected = (changes: Partial<BidOpportunity>) => {
    if (!selected) return;
    const next = { ...selected, ...changes };
    setSelected(next);
    setItems((current) =>
      current.map((item) => (item.id === next.id ? next : item)),
    );
  };
  const metrics = [
    ["Open Opportunities", 8],
    ["New / Unreviewed", items.filter((i) => i.status === "New").length],
    ["Under Review", items.filter((i) => i.status === "Reviewing").length],
    ["Pursuing", items.filter((i) => i.status === "Pursue").length],
    ["Due This Week", 3],
  ];
  return (
    <div className="mx-auto max-w-[1500px]">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[.12em] text-slate-500">
            BB Builders / Preconstruction
          </div>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900 sm:text-[28px]">
            Bid Opportunities
          </h1>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-500">
            Review incoming construction opportunities and decide which projects
            BB Builders should pursue.
          </p>
        </div>
        <Button
          onClick={() => setAdding(true)}
          className="bg-primary text-white"
        >
          <Plus className="h-4 w-4" />
          Add Demo Opportunity
        </Button>
      </div>
      <DemoNotice
        className="mt-5"
        detail="Opportunities, documents, AI summaries, and decisions shown here are simulated."
      />
      <section
        aria-label="Opportunity metrics"
        className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-5"
      >
        {metrics.map(([label, value]) => (
          <Card key={label} className="p-4">
            <p className="text-2xl font-semibold tabular-nums">{value}</p>
            <p className="mt-1 text-xs text-slate-500">{label}</p>
          </Card>
        ))}
      </section>
      <div className="mt-5 flex flex-wrap items-center gap-2 text-xs font-semibold text-slate-600">
        {["New", "Reviewing", "Pursue", "Converted to Project"].map(
          (label, index) => (
            <div key={label} className="flex items-center gap-2">
              <span className="rounded-md border bg-white px-3 py-2">
                {label}
              </span>
              {index < 3 && <span aria-hidden="true">→</span>}
            </div>
          ),
        )}
        <span className="ml-2 rounded-md bg-red-50 px-3 py-2 text-red-700">
          Declined
        </span>
      </div>
      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0">
          <Card className="overflow-hidden">
            <div className="grid gap-3 border-b p-4 md:grid-cols-3">
              <label className="relative">
                <span className="sr-only">Search opportunity</span>
                <Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search opportunities..."
                  className="h-10 w-full rounded-lg border pl-9 pr-3 text-sm"
                />
              </label>
              <label>
                <span className="sr-only">Project type</span>
                <select
                  value={type}
                  onChange={(e) => setType(e.target.value)}
                  className="h-10 w-full rounded-lg border bg-white px-3 text-sm"
                >
                  <option>All project types</option>
                  {types.map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
              </label>
              <label>
                <span className="sr-only">Status</span>
                <select
                  value={status}
                  onChange={(e) => setStatus(e.target.value)}
                  className="h-10 w-full rounded-lg border bg-white px-3 text-sm"
                >
                  <option>All statuses</option>
                  {[
                    "New",
                    "Reviewing",
                    "Pursue",
                    "Declined",
                    "Converted to Project",
                  ].map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
              </label>
            </div>
            {visible.length ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[1120px] text-left text-sm">
                  <caption className="sr-only">
                    Incoming bid opportunities
                  </caption>
                  <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      {[
                        "Opportunity",
                        "Client",
                        "Location",
                        "Project Type",
                        "Bid Deadline",
                        "Documents",
                        "Estimated Size",
                        "Status",
                        "Decision",
                        "Actions",
                      ].map((header) => (
                        <th key={header} className="px-4 py-3 font-semibold">
                          {header}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {visible.map((item) => (
                      <tr key={item.id} className="hover:bg-slate-50">
                        <td className="min-w-64 px-4 py-4">
                          <button
                            onClick={() => openDetail(item)}
                            className="text-left font-semibold text-blue-700 hover:underline focus-visible:outline-2 focus-visible:outline-blue-700"
                          >
                            {item.name}
                          </button>
                          {item.convertedProjectNumber && (
                            <p className="mt-1 text-xs text-slate-500">
                              Project {item.convertedProjectNumber}
                            </p>
                          )}
                        </td>
                        <td className="px-4 py-4">{item.client}</td>
                        <td className="whitespace-nowrap px-4 py-4">
                          {item.city}, {item.province}
                        </td>
                        <td className="px-4 py-4">{item.projectType}</td>
                        <td className="whitespace-nowrap px-4 py-4">
                          {formatDate(item.bidDeadline)}
                        </td>
                        <td className="px-4 py-4 text-right tabular-nums">
                          {item.documentCount}
                        </td>
                        <td className="whitespace-nowrap px-4 py-4 text-right tabular-nums">
                          {item.estimatedSquareFootage.toLocaleString("en-CA")}{" "}
                          SF
                        </td>
                        <td className="px-4 py-4">
                          <StatusBadge status={item.status} />
                        </td>
                        <td className="whitespace-nowrap px-4 py-4">
                          {item.decision}
                        </td>
                        <td className="px-4 py-4">
                          {item.convertedProjectId ? (
                            <Link
                              href={`/projects/${item.convertedProjectId}`}
                              className="font-semibold text-blue-700 hover:underline"
                            >
                              Open Project
                            </Link>
                          ) : (
                            <button
                              onClick={() => openDetail(item)}
                              className="font-semibold text-blue-700 hover:underline"
                            >
                              Review
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-10 text-center">
                <h2 className="font-semibold">
                  No opportunities match these filters.
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  Adjust the search or filters to view more opportunities.
                </p>
              </div>
            )}
          </Card>
        </div>
        <aside>
          <HowItWorks />
        </aside>
      </div>
      {selected && (
        <OpportunityDetail
          item={selected}
          checklist={checklist}
          setChecklist={setChecklist}
          reviewedRisks={reviewedRisks}
          setReviewedRisks={setReviewedRisks}
          decisionMode={decisionMode}
          setDecisionMode={setDecisionMode}
          declineReason={declineReason}
          setDeclineReason={setDeclineReason}
          declineNotes={declineNotes}
          setDeclineNotes={setDeclineNotes}
          converted={converted}
          onClose={() => setSelected(null)}
          onPursue={() =>
            updateSelected({ status: "Pursue", decision: "Approved to Pursue" })
          }
          onDecline={() =>
            updateSelected({ status: "Declined", decision: "No-Go" })
          }
          onConvert={() => setConverted(true)}
        />
      )}
      {adding && (
        <DemoOpportunityForm
          onClose={() => setAdding(false)}
          onAdd={(item) => {
            setItems((current) => [item, ...current]);
            setAdding(false);
          }}
        />
      )}
    </div>
  );
}

function OpportunityDetail(props: {
  item: BidOpportunity;
  checklist: OpportunityReviewChecklist;
  setChecklist: (value: OpportunityReviewChecklist) => void;
  reviewedRisks: Set<string>;
  setReviewedRisks: (value: Set<string>) => void;
  decisionMode: "pursue" | "decline" | null;
  setDecisionMode: (value: "pursue" | "decline" | null) => void;
  declineReason: OpportunityDecisionReason;
  setDeclineReason: (value: OpportunityDecisionReason) => void;
  declineNotes: string;
  setDeclineNotes: (value: string) => void;
  converted: boolean;
  onClose: () => void;
  onPursue: () => void;
  onDecline: () => void;
  onConvert: () => void;
}) {
  const { item } = props;
  const checklistComplete = Object.values(props.checklist).every(Boolean);
  const factors = [
    ["Client Relationship", "Existing Client"],
    ["Geographic Fit", "Within Service Area"],
    ["Project Type Fit", "Strong Retail Fit"],
    ["Bid Timeline", "Tight"],
    ["Document Completeness", "Some Gaps"],
    ["Subcontractor Coverage", "Strong"],
    ["Estimated Complexity", item.complexity],
    ["Capacity", "Needs Confirmation"],
  ];
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="opportunity-detail-title"
      className="fixed inset-0 z-50 flex justify-end bg-slate-950/50"
    >
      <div className="h-full w-full max-w-5xl overflow-y-auto bg-slate-50">
        <header className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b bg-white p-5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Bid Opportunity
            </p>
            <h2
              id="opportunity-detail-title"
              className="mt-1 text-xl font-semibold"
            >
              {item.name}
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              {item.client} · {item.city}, {item.province}
            </p>
          </div>
          <button
            autoFocus
            onClick={props.onClose}
            aria-label="Close opportunity detail"
            className="rounded-lg p-2 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-blue-700"
          >
            <X className="h-5 w-5" />
          </button>
        </header>
        <div className="space-y-5 p-4 sm:p-6">
          {item.convertedProjectId && (
            <Card className="border-emerald-200 bg-emerald-50 p-5">
              <h3 className="font-semibold text-emerald-900">
                Converted to Project · {item.convertedProjectNumber}
              </h3>
              <p className="mt-2 text-sm text-emerald-800">
                Invitation received → Opportunity reviewed → Approved to pursue
                → Converted to project {item.convertedProjectNumber}
              </p>
              <Link
                href={`/projects/${item.convertedProjectId}`}
                className="mt-4 inline-flex rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white"
              >
                Open Project
              </Link>
            </Card>
          )}
          <Card className="p-5">
            <h3 className="font-semibold">Opportunity Information</h3>
            <dl className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {[
                ["Client", item.client],
                ["Location", `${item.city}, ${item.province}`],
                ["Project Type", item.projectType],
                ["Bid Deadline", formatDate(item.bidDeadline)],
                ["Questions Deadline", formatDate(item.questionsDeadline)],
                [
                  "Estimated Size",
                  `${item.estimatedSquareFootage.toLocaleString("en-CA")} SF`,
                ],
                ["Invitation Source", item.invitationSource],
                ["Received", formatDate(item.receivedAt)],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-xs text-slate-500">{label}</dt>
                  <dd className="mt-1 text-sm font-semibold">{value}</dd>
                </div>
              ))}
            </dl>
          </Card>
          <div className="grid gap-5 lg:grid-cols-2">
            <Card className="p-5">
              <h3 className="font-semibold">Documents Received</h3>
              <ul className="mt-3 divide-y">
                {item.documents.map((doc) => (
                  <li
                    key={doc.id}
                    className="flex items-center gap-3 py-2 text-sm"
                  >
                    <FileText className="h-4 w-4 text-slate-500" />
                    {doc.name}
                    <span className="ml-auto text-xs text-slate-400">
                      {doc.category}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-xs text-slate-500">
                Fictional metadata only. No files are stored or rendered.
              </p>
            </Card>
            <Card className="p-5">
              <h3 className="font-semibold">AI-Assisted Opportunity Summary</h3>
              <p className="mt-1 text-xs text-violet-700">
                Demo summary — no documents were parsed and no AI service was
                called.
              </p>
              <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
                <div>
                  <dt className="text-xs text-slate-500">Approximate Area</dt>
                  <dd className="font-semibold">
                    {item.estimatedSquareFootage.toLocaleString("en-CA")} SF
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Likely Trades</dt>
                  <dd className="font-semibold">{item.likelyTrades.length}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Complexity</dt>
                  <dd className="font-semibold">{item.complexity}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Documents Detected</dt>
                  <dd className="font-semibold">
                    Architectural, MEP, Specifications
                  </dd>
                </div>
              </dl>
              <p className="mt-4 text-sm leading-6 text-slate-600">
                {item.summary}
              </p>
            </Card>
          </div>
          <Card className="p-5">
            <h3 className="font-semibold">Likely Trades</h3>
            <div className="mt-3 flex flex-wrap gap-2">
              {item.likelyTrades.map((finding) => (
                <span
                  key={finding.trade}
                  className="rounded-lg border bg-white px-3 py-2 text-sm"
                >
                  <strong>{finding.trade}</strong>
                  <span className="ml-2 text-xs text-slate-500">
                    {finding.confidence} confidence
                  </span>
                </span>
              ))}
            </div>
          </Card>
          <Card className="p-5">
            <h3 className="font-semibold">Items to Review Before Pursuing</h3>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {item.risks.map((risk) => {
                const done = props.reviewedRisks.has(risk.id);
                return (
                  <div key={risk.id} className="rounded-lg border p-3">
                    <div className="flex gap-2">
                      <AlertTriangle className="mt-0.5 h-4 w-4 text-amber-700" />
                      <div>
                        <h4 className="text-sm font-semibold">{risk.title}</h4>
                        <p className="mt-1 text-xs leading-5 text-slate-500">
                          {risk.detail}
                        </p>
                      </div>
                    </div>
                    <Button
                      onClick={() => {
                        const next = new Set(props.reviewedRisks);
                        if (done) next.delete(risk.id);
                        else next.add(risk.id);
                        props.setReviewedRisks(next);
                      }}
                      className="mt-3 h-8 text-xs"
                    >
                      {done ? "Reviewed" : "Mark Reviewed"}
                    </Button>
                  </div>
                );
              })}
            </div>
          </Card>
          <div className="grid gap-5 lg:grid-cols-2">
            <Card className="p-5">
              <h3 className="font-semibold">Go / No-Go Review</h3>
              <dl className="mt-3 divide-y">
                {factors.map(([label, value]) => (
                  <div
                    key={label}
                    className="flex justify-between gap-4 py-2 text-sm"
                  >
                    <dt className="text-slate-500">{label}</dt>
                    <dd className="font-semibold">{value}</dd>
                  </div>
                ))}
              </dl>
            </Card>
            <Card className="p-5">
              <h3 className="font-semibold">
                Opportunity Fit · {item.fit.label}
              </h3>
              <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-600">
                {item.fit.reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
              <p className="mt-3 text-sm">
                <strong>Concern:</strong> {item.fit.concern}
              </p>
              <p className="mt-3 text-xs text-slate-500">
                Opportunity fit is a review aid only. Final Go / No-Go decision
                belongs to the estimator.
              </p>
            </Card>
          </div>
          {!item.convertedProjectId && (
            <Card className="p-5">
              <h3 className="font-semibold">Human Decision</h3>
              {item.status === "Declined" ? (
                <div className="mt-3 rounded-lg bg-red-50 p-4 text-sm text-red-800">
                  <strong>Opportunity Declined</strong>
                  <p className="mt-1">
                    This opportunity remains in history and was not converted to
                    a project.
                  </p>
                </div>
              ) : item.status === "Pursue" ? (
                <div className="mt-3">
                  <div className="rounded-lg bg-emerald-50 p-4 text-sm text-emerald-800">
                    <strong>Approved to Pursue</strong>
                    <p className="mt-1">
                      Approved by Alex Morgan · Estimator · Sep 10, 2026, 2:15
                      PM
                    </p>
                  </div>
                  {props.converted ? (
                    <div className="mt-4 rounded-lg border p-4">
                      <h4 className="font-semibold">
                        Opportunity Converted to Project
                      </h4>
                      <p className="mt-2 text-sm text-slate-600">
                        Preparing project record ↓ Carrying details forward ↓
                        Preparing document workspace ↓ Setting bidding workflow
                        ↓ Demo project ready
                      </p>
                      <p className="mt-2 text-xs text-slate-500">
                        The existing Coquitlam project is used as the prototype
                        destination; no new record persists.
                      </p>
                      <Link
                        href="/projects/retail-store-coquitlam"
                        className="mt-3 inline-flex rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white"
                      >
                        Open Existing Coquitlam Demo Project
                      </Link>
                    </div>
                  ) : (
                    <Button
                      onClick={props.onConvert}
                      className="mt-4 bg-primary text-white"
                    >
                      Create Demo Project
                    </Button>
                  )}
                </div>
              ) : (
                <>
                  <div className="mt-4 flex flex-wrap gap-3">
                    <Button
                      onClick={() => props.setDecisionMode("pursue")}
                      className="bg-primary text-white"
                    >
                      Pursue Opportunity
                    </Button>
                    <Button
                      onClick={() => props.setDecisionMode("decline")}
                      className="border-red-200 text-red-700"
                    >
                      Decline Opportunity
                    </Button>
                  </div>
                  {props.decisionMode === "pursue" && (
                    <div className="mt-4 rounded-lg border p-4">
                      <h4 className="font-semibold">
                        Pursuit Review Checklist
                      </h4>
                      <div className="mt-3 grid gap-2 sm:grid-cols-2">
                        {checklistLabels.map(([key, label]) => (
                          <label
                            key={key}
                            className="flex items-center gap-2 text-sm"
                          >
                            <input
                              type="checkbox"
                              checked={props.checklist[key]}
                              onChange={(e) =>
                                props.setChecklist({
                                  ...props.checklist,
                                  [key]: e.target.checked,
                                })
                              }
                            />
                            {label}
                          </label>
                        ))}
                      </div>
                      <Button
                        disabled={!checklistComplete}
                        onClick={props.onPursue}
                        className="mt-4 bg-primary text-white"
                      >
                        Approve to Pursue
                      </Button>
                    </div>
                  )}
                  {props.decisionMode === "decline" && (
                    <div className="mt-4 rounded-lg border p-4">
                      <label className="text-sm font-medium">
                        Decline reason
                        <select
                          value={props.declineReason}
                          onChange={(e) =>
                            props.setDeclineReason(
                              e.target.value as OpportunityDecisionReason,
                            )
                          }
                          className="mt-1 block h-10 w-full rounded-lg border bg-white px-3"
                        >
                          {declineReasons.map((reason) => (
                            <option key={reason}>{reason}</option>
                          ))}
                        </select>
                      </label>
                      <label className="mt-3 block text-sm font-medium">
                        Optional notes
                        <textarea
                          value={props.declineNotes}
                          onChange={(e) =>
                            props.setDeclineNotes(e.target.value)
                          }
                          className="mt-1 block min-h-20 w-full rounded-lg border p-3"
                        />
                      </label>
                      <Button
                        onClick={props.onDecline}
                        className="mt-3 border-red-700 bg-red-700 text-white"
                      >
                        Confirm Decline
                      </Button>
                    </div>
                  )}
                </>
              )}
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function DemoOpportunityForm({
  onClose,
  onAdd,
}: {
  onClose: () => void;
  onAdd: (item: BidOpportunity) => void;
}) {
  const [form, setForm] = useState({
    name: "",
    client: "",
    projectType: "Retail Tenant Improvement",
    address: "",
    city: "",
    province: "BC",
    deadline: "",
    size: "",
    source: "Client Email",
    notes: "",
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const template = {
      ...form,
      id: `demo-${Date.now()}`,
      name: form.name,
      client: form.client,
      address: form.address,
      city: form.city,
      province: form.province,
      projectType: form.projectType,
      estimatedSquareFootage: Number(form.size),
      bidDeadline: form.deadline,
      questionsDeadline: form.deadline,
      receivedAt: "2026-09-10",
      invitationSource: form.source,
      contactName: "Demo Contact",
      contactEmail: "contact@example.com",
      documentCount: 0,
      documents: [],
      likelyTrades: [],
      summary: form.notes || "New demo opportunity awaiting initial review.",
      risks: [],
      status: "New" as const,
      decision: "Pending" as const,
      complexity: "Moderate" as const,
      fit: {
        label: "Needs Review" as const,
        reasons: ["Initial review required"],
        concern: "Details have not yet been reviewed",
      },
    };
    onAdd(template);
  };
  const fields: Array<[keyof typeof form, string, string]> = [
    ["name", "Opportunity Name", "text"],
    ["client", "Client", "text"],
    ["projectType", "Project Type", "text"],
    ["address", "Street Address", "text"],
    ["city", "City", "text"],
    ["province", "Province", "text"],
    ["deadline", "Bid Deadline", "date"],
    ["size", "Estimated Square Footage", "number"],
  ];
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-opportunity-title"
      className="fixed inset-0 z-50 grid place-items-center bg-slate-950/50 p-4"
    >
      <form
        onSubmit={submit}
        className="max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-5 shadow-2xl"
      >
        <div className="flex justify-between">
          <div>
            <h2 id="add-opportunity-title" className="text-lg font-semibold">
              Add Demo Opportunity
            </h2>
            <p className="mt-1 text-xs text-slate-500">
              Demo changes reset when the application reloads.
            </p>
          </div>
          <button
            type="button"
            autoFocus
            onClick={onClose}
            aria-label="Close add opportunity form"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          {fields.map(([key, label, type]) => (
            <label key={key} className="text-sm font-medium">
              {label}
              <input
                required
                value={form[key]}
                type={type}
                onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                className="mt-1 h-10 w-full rounded-lg border px-3"
              />
            </label>
          ))}
          <label className="text-sm font-medium">
            Invitation Source
            <select
              value={form.source}
              onChange={(e) => setForm({ ...form, source: e.target.value })}
              className="mt-1 h-10 w-full rounded-lg border bg-white px-3"
            >
              {[
                "Client Email",
                "Construction Manager",
                "Existing Client",
                "Referral",
                "Bid Portal",
                "Other",
              ].map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <label className="text-sm font-medium sm:col-span-2">
            Notes
            <textarea
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              className="mt-1 min-h-24 w-full rounded-lg border p-3"
            />
          </label>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" className="bg-primary text-white">
            Add Demo Opportunity
          </Button>
        </div>
      </form>
    </div>
  );
}
