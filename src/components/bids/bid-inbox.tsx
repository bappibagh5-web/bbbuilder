"use client";
import { useMemo, useState } from "react";
import { FileSearch, X } from "lucide-react";
import type {
  BidReviewChecklist,
  BidSubmission,
  Project,
  Subcontractor,
} from "@/types";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { formatCurrency } from "@/lib/utils";
const empty: BidReviewChecklist = {
  total: false,
  scopeCoverage: false,
  exclusions: false,
  schedule: false,
  clarifications: false,
};
export function BidInbox({
  project,
  initialBids,
  companies,
  summary,
}: {
  project: Project;
  initialBids: BidSubmission[];
  companies: Subcontractor[];
  summary: {
    received: number;
    trades: number;
    needsReview: number;
    clarifications: number;
    ready: number;
  };
}) {
  const [bids, setBids] = useState(initialBids);
  const [selected, setSelected] = useState<BidSubmission | null>(null);
  const [filters, setFilters] = useState({
    trade: "",
    review: "",
    completeness: "",
  });
  const companyMap = new Map(companies.map((c) => [c.id, c]));
  const filtered = useMemo(
    () =>
      bids.filter(
        (b) =>
          (!filters.trade || b.trade === filters.trade) &&
          (!filters.review || b.reviewStatus === filters.review) &&
          (!filters.completeness || b.completeness === filters.completeness),
      ),
    [bids, filters],
  );
  if (project.id !== "retail-store-coquitlam")
    return (
      <Card className="p-10 text-center">
        <FileSearch className="mx-auto h-8 w-8 text-slate-400" />
        <h2 className="mt-4 text-xl font-semibold">No Bids Received</h2>
        <p className="mt-2 text-sm text-slate-500">
          Bid collection has not started for {project.name}.
        </p>
      </Card>
    );
  return (
    <div className="space-y-5">
      <header>
        <h2 className="text-xl font-semibold">Bid Inbox</h2>
        <p className="mt-1 text-sm text-slate-500">
          Collect and review subcontractor pricing received for this project.
        </p>
        <p className="mt-2 text-xs font-medium text-violet-700">
          Demo environment — all submissions, attachments, pricing, and review
          activity are fictional.
        </p>
      </header>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {[
          ["Bids Received", summary.received],
          ["Trades Covered", summary.trades],
          ["Needs Review", summary.needsReview],
          ["Clarifications Required", summary.clarifications],
          ["Ready for Comparison", summary.ready],
        ].map(([l, v]) => (
          <Card key={l as string} className="p-4">
            <p className="text-2xl font-semibold">{v}</p>
            <p className="text-xs text-slate-500">{l}</p>
          </Card>
        ))}
      </section>
      <Card>
        <div className="grid gap-3 border-b p-4 sm:grid-cols-3">
          <label>
            <span className="sr-only">Filter bids by trade</span>
            <select
              value={filters.trade}
              onChange={(e) =>
                setFilters((v) => ({ ...v, trade: e.target.value }))
              }
              className="h-10 w-full rounded-lg border bg-white px-3"
            >
              <option value="">All trades</option>
              <option>Electrical</option>
            </select>
          </label>
          <label>
            <span className="sr-only">Filter by review status</span>
            <select
              value={filters.review}
              onChange={(e) =>
                setFilters((v) => ({ ...v, review: e.target.value }))
              }
              className="h-10 w-full rounded-lg border bg-white px-3"
            >
              <option value="">All review statuses</option>
              <option>Reviewed</option>
              <option>Needs Review</option>
            </select>
          </label>
          <label>
            <span className="sr-only">Filter by submission completeness</span>
            <select
              value={filters.completeness}
              onChange={(e) =>
                setFilters((v) => ({ ...v, completeness: e.target.value }))
              }
              className="h-10 w-full rounded-lg border bg-white px-3"
            >
              <option value="">All completeness</option>
              <option>Complete</option>
              <option>Incomplete</option>
            </select>
          </label>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[980px] text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                {[
                  "Contractor",
                  "Trade",
                  "Submitted",
                  "Total",
                  "Completeness",
                  "Demo Review",
                  "Clarifications",
                  "Status",
                  "Actions",
                ].map((h) => (
                  <th key={h} className="px-4 py-3">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y">
              {filtered.map((b) => (
                <tr key={b.id}>
                  <td className="px-4 py-3 font-semibold">
                    {companyMap.get(b.subcontractorId)?.companyName}
                  </td>
                  <td className="px-4 py-3">{b.trade}</td>
                  <td className="px-4 py-3">{b.submittedAt}</td>
                  <td className="px-4 py-3 font-semibold">
                    {formatCurrency(b.total)}
                  </td>
                  <td className="px-4 py-3">{b.completeness}</td>
                  <td className="px-4 py-3">{b.reviewStatus}</td>
                  <td className="px-4 py-3">{b.clarifications.length}</td>
                  <td className="px-4 py-3">{b.status}</td>
                  <td className="px-4 py-3">
                    <Button onClick={() => setSelected(b)}>
                      Review Submission
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="border-t p-4 text-xs text-slate-500">
          Apex Retail Electrical has not submitted a bid and is tracked in
          Outreach, not as a BidSubmission record.
        </p>
      </Card>
      {selected && (
        <BidPanel
          bid={selected}
          company={companyMap.get(selected.subcontractorId)!}
          onClose={() => setSelected(null)}
          onUpdate={(fn) => {
            setBids((items) =>
              items.map((b) => (b.id === selected.id ? fn(b) : b)),
            );
            setSelected((current) => (current ? fn(current) : current));
          }}
        />
      )}
    </div>
  );
}
function BidPanel({
  bid,
  company,
  onClose,
  onUpdate,
}: {
  bid: BidSubmission;
  company: Subcontractor;
  onClose: () => void;
  onUpdate: (fn: (b: BidSubmission) => BidSubmission) => void;
}) {
  const [review, setReview] = useState<BidReviewChecklist>(
    bid.status === "Ready for Comparison"
      ? {
          total: true,
          scopeCoverage: true,
          exclusions: true,
          schedule: true,
          clarifications: true,
        }
      : empty,
  );
  const ready =
    Object.values(review).every(Boolean) && bid.completeness === "Complete";
  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-slate-950/45"
      role="dialog"
      aria-modal="true"
      aria-label="Bid submission detail"
    >
      <div className="h-full w-full max-w-3xl overflow-y-auto bg-white">
        <header className="sticky top-0 z-10 flex items-center justify-between border-b bg-white p-5">
          <div>
            <p className="text-xs font-semibold text-violet-700">
              Fictional demo submission
            </p>
            <h2 className="font-semibold">
              {company.companyName} · {bid.trade}
            </h2>
          </div>
          <button onClick={onClose} aria-label="Close bid submission">
            <X className="h-5 w-5" />
          </button>
        </header>
        <div className="space-y-5 p-5">
          <dl className="grid gap-3 sm:grid-cols-3">
            {[
              ["Received Date", bid.submittedAt],
              ["Submitted By", bid.submittedBy],
              ["Original Filename", bid.attachment.filename],
              ["Total Bid", formatCurrency(bid.total)],
              ["Review Status", bid.reviewStatus],
              ["Source Campaign", bid.campaignId],
            ].map(([l, v]) => (
              <div key={l}>
                <dt className="text-xs text-slate-500">{l}</dt>
                <dd className="break-words text-sm font-semibold">{v}</dd>
              </div>
            ))}
          </dl>
          <section className="rounded-lg border">
            <header className="border-b bg-slate-50 p-4">
              <h3 className="font-semibold">Demo Quote Extraction</h3>
              <p className="mt-1 text-xs text-violet-700">
                Demo environment — pricing fields below are simulated. No
                document was parsed and no AI service was called.
              </p>
            </header>
            <dl className="grid sm:grid-cols-2">
              {[
                ["Base Bid", formatCurrency(bid.extraction.baseBid)],
                ["Taxes", bid.extraction.taxes],
                ["Labour", bid.extraction.labour],
                ["Materials", bid.extraction.materials],
                ["Permit", bid.extraction.permit],
                ["Fixtures", bid.extraction.fixtures],
                ["Schedule", bid.extraction.schedule],
                ["Bid Validity", bid.extraction.validity],
                ["Scope Coverage", `${bid.extraction.scopeCoverage}%`],
                [
                  "Estimated Review Confidence",
                  `${bid.extraction.confidence}%`,
                ],
              ].map(([l, v]) => (
                <div key={l} className="border-b p-3 sm:border-r">
                  <dt className="text-xs text-slate-500">{l}</dt>
                  <dd className="text-sm font-semibold">{v}</dd>
                </div>
              ))}
            </dl>
            <div className="grid gap-4 p-4 sm:grid-cols-2">
              <div>
                <h4 className="text-sm font-semibold">Exclusions</h4>
                <ul className="mt-1 list-disc pl-5 text-sm">
                  {bid.extraction.exclusions.map((v) => (
                    <li key={v}>{v}</li>
                  ))}
                </ul>
              </div>
              <div>
                <h4 className="text-sm font-semibold">
                  Potential Missing Items
                </h4>
                {bid.extraction.missingItems.length ? (
                  <ul className="mt-1 list-disc pl-5 text-sm text-amber-800">
                    {bid.extraction.missingItems.map((v) => (
                      <li key={v}>{v}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-1 text-sm text-emerald-700">
                    None identified
                  </p>
                )}
              </div>
            </div>
          </section>
          <section>
            <h3 className="font-semibold">Bid Clarifications</h3>
            <div className="mt-3 space-y-3">
              {bid.clarifications.map((c) => (
                <article key={c.id} className="rounded-lg border p-4">
                  <div className="flex justify-between gap-3">
                    <p className="text-sm font-semibold">{c.category}</p>
                    <span className="text-xs">
                      {c.priority} · {c.status}
                    </span>
                  </div>
                  <p className="mt-2 text-sm">{c.question}</p>
                  {c.status === "Open" && (
                    <Button
                      onClick={() =>
                        onUpdate((b) => ({
                          ...b,
                          clarifications: b.clarifications.map((item) =>
                            item.id === c.id
                              ? { ...item, status: "Prepared" }
                              : item,
                          ),
                        }))
                      }
                      className="mt-3"
                    >
                      Prepare Clarification
                    </Button>
                  )}
                  {c.status === "Prepared" && (
                    <p className="mt-2 text-xs text-violet-700">
                      Demo clarification prepared — no message sent.
                    </p>
                  )}
                </article>
              ))}
            </div>
          </section>
          <section className="rounded-lg border p-4">
            <h3 className="font-semibold">Human Review Checklist</h3>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {Object.entries({
                total: "Total verified",
                scopeCoverage: "Scope coverage reviewed",
                exclusions: "Exclusions reviewed",
                schedule: "Schedule reviewed",
                clarifications: "Clarifications reviewed",
              }).map(([key, label]) => (
                <label
                  key={key}
                  className="flex gap-3 rounded border p-3 text-sm"
                >
                  <input
                    type="checkbox"
                    checked={review[key as keyof BidReviewChecklist]}
                    onChange={(e) =>
                      setReview((v) => ({ ...v, [key]: e.target.checked }))
                    }
                  />
                  {label}
                </label>
              ))}
            </div>
            <Button
              disabled={!ready || bid.status === "Ready for Comparison"}
              onClick={() =>
                onUpdate((b) => ({
                  ...b,
                  status: "Ready for Comparison",
                  reviewStatus: "Reviewed",
                }))
              }
              className="mt-4 bg-primary text-white"
            >
              {bid.status === "Ready for Comparison"
                ? "Ready for Comparison"
                : "Mark Ready for Comparison"}
            </Button>
            {bid.completeness === "Incomplete" && (
              <p className="mt-2 text-xs text-amber-700">
                Incomplete bids cannot be marked ready until missing items and
                open clarifications are resolved.
              </p>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
