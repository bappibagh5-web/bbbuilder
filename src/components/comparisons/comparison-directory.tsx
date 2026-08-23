"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import type { ComparisonQueueItem } from "@/types";
import { Card } from "@/components/ui/card";
export function ComparisonDirectory({
  items,
  summary,
}: {
  items: ComparisonQueueItem[];
  summary: {
    ready: number;
    inReview: number;
    approved: number;
    clarifications: number;
    nearProposal: number;
  };
}) {
  const [f, setF] = useState({ q: "", trade: "", status: "" });
  const shown = useMemo(
    () =>
      items.filter(
        (i) =>
          (!f.q || i.projectName.toLowerCase().includes(f.q.toLowerCase())) &&
          (!f.trade || i.trade === f.trade) &&
          (!f.status || i.status === f.status),
      ),
    [items, f],
  );
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold">Bid Comparisons</h1>
        <p className="mt-1 text-sm text-slate-500">
          Review subcontractor pricing, scope coverage, exclusions, and
          estimator recommendations.
        </p>
        <p className="mt-2 text-xs font-medium text-violet-700">
          Demo environment — pricing, comparisons, and recommendation results
          shown here are simulated.
        </p>
      </header>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {[
          ["Trades Ready for Comparison", summary.ready],
          ["Comparisons In Review", summary.inReview],
          ["Selections Approved", summary.approved],
          ["Clarifications Open", summary.clarifications],
          ["Projects Nearing Proposal", summary.nearProposal],
        ].map(([l, v]) => (
          <Card key={l as string} className="p-4">
            <p className="text-2xl font-semibold">{v}</p>
            <p className="text-xs text-slate-500">{l}</p>
          </Card>
        ))}
      </section>
      <Card>
        <div className="grid gap-3 border-b p-4 sm:grid-cols-3">
          <input
            aria-label="Search project"
            placeholder="Search project"
            value={f.q}
            onChange={(e) => setF((v) => ({ ...v, q: e.target.value }))}
            className="h-10 rounded-lg border px-3"
          />
          <select
            aria-label="Filter by trade"
            value={f.trade}
            onChange={(e) => setF((v) => ({ ...v, trade: e.target.value }))}
            className="h-10 rounded-lg border bg-white px-3"
          >
            <option value="">All trades</option>
            {[...new Set(items.map((i) => i.trade))].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
          <select
            aria-label="Filter by comparison status"
            value={f.status}
            onChange={(e) => setF((v) => ({ ...v, status: e.target.value }))}
            className="h-10 rounded-lg border bg-white px-3"
          >
            <option value="">All statuses</option>
            {[
              "Not Ready",
              "Needs More Bids",
              "Ready for Review",
              "Clarifications Required",
              "Selection Approved",
              "Closed",
            ].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1000px] text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                {[
                  "Project",
                  "Trade",
                  "Bids",
                  "Price Range",
                  "Scope Coverage",
                  "Open Clarifications",
                  "Recommendation",
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
              {shown.map((i) => (
                <tr key={i.id}>
                  <td className="px-4 py-3 font-semibold">{i.projectName}</td>
                  <td className="px-4 py-3">{i.trade}</td>
                  <td className="px-4 py-3">{i.bids}</td>
                  <td className="px-4 py-3">{i.priceRange}</td>
                  <td className="px-4 py-3">{i.coverageRange}</td>
                  <td className="px-4 py-3">{i.clarifications}</td>
                  <td className="px-4 py-3">{i.recommendation}</td>
                  <td className="px-4 py-3">{i.status}</td>
                  <td className="px-4 py-3">
                    <Link
                      href={`/projects/${i.projectId}/comparisons`}
                      className="font-semibold text-blue-700"
                    >
                      Open Comparison
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="border-t p-4 text-xs text-slate-500">
          Showing {shown.length} comparison records.
        </p>
      </Card>
    </div>
  );
}
