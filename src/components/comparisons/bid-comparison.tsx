"use client";
import { useState } from "react";
import Link from "next/link";
import { BarChart3 } from "lucide-react";
import type {
  BidSubmission,
  EstimatorSelection,
  LeveledBid,
  Project,
  Subcontractor,
} from "@/types";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { formatCurrency } from "@/lib/utils";
export function BidComparison({
  project,
  tradeNames,
  initialLevels,
  bids,
  companies,
}: {
  project: Project;
  tradeNames: string[];
  initialLevels: LeveledBid[];
  bids: BidSubmission[];
  companies: Subcontractor[];
}) {
  const [trade, setTrade] = useState("Electrical");
  const [levels, setLevels] = useState(initialLevels);
  const [selection, setSelection] = useState<EstimatorSelection | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [reason, setReason] = useState("Better scope coverage");
  const [notes, setNotes] = useState("");
  const cmap = new Map(companies.map((c) => [c.id, c]));
  const bmap = new Map(bids.map((b) => [b.id, b]));
  const normalized = (l: LeveledBid) =>
    l.normalization.baseBid +
    l.normalization.adjustments.reduce((n, a) => n + a.amount, 0);
  const choose = (id: string) => {
    if (id === levels[0].subcontractorId)
      setSelection({
        trade: "Electrical",
        subcontractorId: id,
        selectedBy: "Alex Morgan · Estimator",
        selectedAt: "Aug 23, 2026, 5:10 PM",
        basis: "Recommended Candidate",
      });
    else setPending(id);
  };
  if (project.id !== "retail-store-coquitlam")
    return (
      <Card className="p-10 text-center">
        <BarChart3 className="mx-auto h-8 w-8 text-slate-400" />
        <h2 className="mt-4 text-xl font-semibold">Comparison Not Ready</h2>
        <p className="mt-2 text-sm text-slate-500">
          Qualified bids are required before leveling can begin.
        </p>
      </Card>
    );
  return (
    <div className="space-y-5">
      <header>
        <h2 className="text-xl font-semibold">Bid Comparison</h2>
        <p className="mt-1 text-sm text-slate-500">
          Level subcontractor bids and select the best-value proposal for each
          trade.
        </p>
        <p className="mt-1 text-sm font-medium">
          {project.name} · {project.projectNumber} · {project.city},{" "}
          {project.province} · September 14, 2026
        </p>
        <p className="mt-2 text-xs font-medium text-violet-700">
          Demo environment — all pricing, adjustments, risk indicators, and
          recommendations are simulated.
        </p>
      </header>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {[
          ["Trades Ready", 7],
          ["Trades Selected", 3],
          ["Clarifications Open", 4],
          ["Needs More Coverage", 2],
          ["Estimated Trade Total", "$238,450"],
        ].map(([l, v]) => (
          <Card key={l as string} className="p-4">
            <p className="text-2xl font-semibold">{v}</p>
            <p className="text-xs text-slate-500">{l}</p>
          </Card>
        ))}
      </section>
      <div className="grid gap-5 xl:grid-cols-[280px_1fr]">
        <aside>
          <select
            aria-label="Select comparison trade"
            value={trade}
            onChange={(e) => setTrade(e.target.value)}
            className="h-10 w-full rounded-lg border bg-white px-3 xl:hidden"
          >
            {tradeNames.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
          <Card className="hidden xl:block">
            {tradeNames.map((t) => (
              <button
                key={t}
                onClick={() => setTrade(t)}
                className={`w-full border-b p-3 text-left ${trade === t ? "bg-blue-50" : ""}`}
              >
                <span className="text-sm font-semibold">{t}</span>
                <p className="text-xs text-slate-500">
                  {t === "Electrical"
                    ? "3 qualified bids · Ready for Review"
                    : t === "Plumbing"
                      ? "3 bids · Selection Approved"
                      : t === "Flooring" || t === "Fire Protection"
                        ? "2 bids · Needs More Coverage"
                        : "3 bids · Ready"}
                </p>
              </button>
            ))}
          </Card>
        </aside>
        <main className="min-w-0 space-y-5">
          {trade !== "Electrical" ? (
            <Card className="p-8 text-center">
              <h3 className="font-semibold">{trade} Comparison Summary</h3>
              <p className="mt-2 text-sm text-slate-500">
                Electrical contains the complete leveling and estimator-decision
                workflow.
              </p>
            </Card>
          ) : (
            <>
              <Card>
                <header className="border-b p-4">
                  <h3 className="font-semibold">
                    Apples-to-Apples Electrical Comparison
                  </h3>
                  <p className="text-xs text-slate-500">
                    The lowest submitted bid is not necessarily the lowest
                    comparable bid.
                  </p>
                </header>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[900px] text-left text-sm">
                    <thead className="bg-slate-50">
                      <tr>
                        <th className="p-3">Comparison Factor</th>
                        {levels.map((l) => (
                          <th key={l.id} className="p-3">
                            {cmap.get(l.subcontractorId)?.companyName}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {[
                        [
                          "Submitted Bid",
                          (l: LeveledBid) =>
                            formatCurrency(l.normalization.baseBid),
                        ],
                        [
                          "Normalized Bid",
                          (l: LeveledBid) => formatCurrency(normalized(l)),
                        ],
                        [
                          "Scope Coverage",
                          (l: LeveledBid) =>
                            `${bmap.get(l.bidSubmissionId)?.extraction.scopeCoverage}%`,
                        ],
                        [
                          "Permit",
                          (l: LeveledBid) =>
                            bmap.get(l.bidSubmissionId)?.extraction.permit,
                        ],
                        [
                          "Fixtures",
                          (l: LeveledBid) =>
                            bmap.get(l.bidSubmissionId)?.extraction.fixtures,
                        ],
                        [
                          "Emergency Lighting",
                          (l: LeveledBid) => l.emergencyLighting,
                        ],
                        ["Fire Alarm", (l: LeveledBid) => l.fireAlarm],
                        ["Security", (l: LeveledBid) => l.security],
                        [
                          "Schedule",
                          (l: LeveledBid) =>
                            bmap.get(l.bidSubmissionId)?.extraction.schedule,
                        ],
                        [
                          "Bid Validity",
                          (l: LeveledBid) =>
                            bmap.get(l.bidSubmissionId)?.extraction.validity,
                        ],
                        [
                          "Qualification",
                          (l: LeveledBid) =>
                            cmap.get(l.subcontractorId)?.qualificationStatus,
                        ],
                        [
                          "Relationship",
                          (l: LeveledBid) =>
                            cmap.get(l.subcontractorId)?.relationship,
                        ],
                        ["Risk", (l: LeveledBid) => l.riskLevel],
                        [
                          "Review Position",
                          (l: LeveledBid) => l.reviewPosition,
                        ],
                      ].map(([label, get]) => (
                        <tr key={label as string}>
                          <th className="p-3 font-semibold">
                            {label as string}
                          </th>
                          {levels.map((l) => (
                            <td key={l.id} className="p-3">
                              {(get as (x: LeveledBid) => React.ReactNode)(l)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
              <section className="grid gap-4 lg:grid-cols-3">
                {levels.map((l) => (
                  <Card key={l.id} className="p-4">
                    <h3 className="font-semibold">
                      {cmap.get(l.subcontractorId)?.companyName}
                    </h3>
                    <p className="mt-1 text-sm">
                      {formatCurrency(l.normalization.baseBid)} →{" "}
                      <strong>{formatCurrency(normalized(l))}</strong>
                    </p>
                    <p className="mt-1 text-xs text-violet-700">
                      Normalization adjustments are estimator comparison
                      assumptions.
                    </p>
                    <div className="mt-3 space-y-2">
                      {l.normalization.adjustments.map((a) => (
                        <label key={a.id} className="block text-xs">
                          <span>{a.description}</span>
                          <input
                            aria-label={`${a.description} amount`}
                            type="number"
                            value={a.amount}
                            onChange={(e) =>
                              setLevels((items) =>
                                items.map((x) =>
                                  x.id === l.id
                                    ? {
                                        ...x,
                                        normalization: {
                                          ...x.normalization,
                                          adjustments:
                                            x.normalization.adjustments.map(
                                              (y) =>
                                                y.id === a.id
                                                  ? {
                                                      ...y,
                                                      amount: Number(
                                                        e.target.value,
                                                      ),
                                                      source: "Estimator",
                                                    }
                                                  : y,
                                            ),
                                        },
                                      }
                                    : x,
                                ),
                              )
                            }
                            className="mt-1 h-9 w-full rounded border px-2"
                          />
                        </label>
                      ))}
                    </div>
                    <h4 className="mt-4 text-sm font-semibold">
                      Risk: {l.riskLevel}
                    </h4>
                    <ul className="mt-1 list-disc pl-5 text-xs">
                      {l.riskReasons.map((r) => (
                        <li key={r}>{r}</li>
                      ))}
                    </ul>
                    <Button
                      onClick={() => choose(l.subcontractorId)}
                      disabled={l.riskLevel === "High"}
                      className="mt-4 w-full"
                    >
                      Select for Trade
                    </Button>
                  </Card>
                ))}
              </section>
              <Card className="p-5">
                <h3 className="font-semibold">
                  AI-Assisted Estimator Recommendation
                </h3>
                <p className="mt-1 text-xs text-violet-700">
                  Recommendation shown here is simulated from structured
                  comparison data. No AI service was called.
                </p>
                <p className="mt-4 text-sm font-semibold">
                  Recommended for Estimator Review: Demo Pacific Electrical Ltd.
                </p>
                <ul className="mt-2 list-disc pl-5 text-sm">
                  <li>
                    Lowest normalized comparable cost among sufficiently
                    complete bids
                  </li>
                  <li>91% scope coverage with permit and fixtures included</li>
                  <li>Preferred relationship and complete schedule</li>
                </ul>
                <p className="mt-3 text-sm">
                  <strong>Trade-off:</strong> Demo Fraser Valley Electrical has
                  96% coverage and a faster schedule at approximately $250
                  higher normalized price.
                </p>
                <p className="mt-2 text-sm">
                  <strong>Concern:</strong> Pacific excludes fire alarm; a
                  $2,500 estimator allowance is included.
                </p>
              </Card>
              {selection && (
                <Card className="p-5">
                  <h3 className="font-semibold">Estimator Selection</h3>
                  <p className="mt-2 text-lg font-semibold">
                    {cmap.get(selection.subcontractorId)?.companyName}
                  </p>
                  <p className="text-sm">
                    Selected by {selection.selectedBy} · {selection.selectedAt}
                  </p>
                  <p className="mt-2 text-sm font-semibold">
                    {selection.basis}
                  </p>
                  {selection.overrideReason && (
                    <p className="text-sm">
                      Reason: {selection.overrideReason} · {selection.notes}
                    </p>
                  )}
                  <Link
                    href={`/projects/${project.id}/proposal`}
                    className="mt-4 inline-flex rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white"
                  >
                    Continue to Proposal
                  </Link>
                </Card>
              )}
            </>
          )}
        </main>
      </div>
      {pending && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4"
          role="dialog"
          aria-modal="true"
          aria-label="Estimator override"
        >
          <Card className="w-full max-w-lg p-5">
            <h2 className="font-semibold">Estimator Override</h2>
            <p className="mt-2 text-sm">
              Select {cmap.get(pending)?.companyName} instead of the recommended
              Demo Pacific Electrical Ltd.
            </p>
            <label className="mt-4 block text-sm">
              Override reason
              <select
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="mt-1 h-10 w-full rounded border px-3"
              >
                {[
                  "Better scope coverage",
                  "Better schedule",
                  "Existing relationship",
                  "Lower risk",
                  "Client preference",
                  "Capacity confirmed",
                  "Commercial terms",
                  "Other",
                ].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
            <label className="mt-3 block text-sm">
              Notes
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="mt-1 w-full rounded border p-3"
              />
            </label>
            <div className="mt-4 flex justify-end gap-2">
              <Button onClick={() => setPending(null)}>Cancel</Button>
              <Button
                onClick={() => {
                  setSelection({
                    trade: "Electrical",
                    subcontractorId: pending,
                    selectedBy: "Alex Morgan · Estimator",
                    selectedAt: "Aug 23, 2026, 5:12 PM",
                    basis: "Estimator Override",
                    overrideReason: reason,
                    notes,
                  });
                  setPending(null);
                }}
                className="bg-primary text-white"
              >
                Confirm Override
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
