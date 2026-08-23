"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import type { Proposal } from "@/types";
import { Card } from "@/components/ui/card";
import {
  calculateProposalPricing,
  formatCurrency,
  formatDate,
} from "@/lib/utils";
export function ProposalDirectory({
  items,
  summary,
}: {
  items: Proposal[];
  summary: {
    draft: number;
    approval: number;
    issued: number;
    revisions: number;
    awarded: number;
  };
}) {
  const [f, setF] = useState({ q: "", status: "", decision: "" });
  const shown = useMemo(
    () =>
      items.filter(
        (i) =>
          (!f.q ||
            `${i.projectName} ${i.client}`
              .toLowerCase()
              .includes(f.q.toLowerCase())) &&
          (!f.status || i.status === f.status) &&
          (!f.decision || i.clientDecision === f.decision),
      ),
    [items, f],
  );
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold">Proposals</h1>
        <p className="mt-1 text-sm text-slate-500">
          Prepare, review, and track client-facing construction proposals.
        </p>
        <p className="mt-2 text-xs font-medium text-violet-700">
          Demo environment — pricing, proposal versions, and client activity
          shown here are simulated.
        </p>
      </header>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {[
          ["Draft Proposals", summary.draft],
          ["Awaiting Internal Approval", summary.approval],
          ["Issued to Client", summary.issued],
          ["Revisions Requested", summary.revisions],
          ["Awarded", summary.awarded],
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
            aria-label="Search project or client"
            placeholder="Search project or client"
            value={f.q}
            onChange={(e) => setF((v) => ({ ...v, q: e.target.value }))}
            className="h-10 rounded-lg border px-3"
          />
          <select
            aria-label="Filter proposal status"
            value={f.status}
            onChange={(e) => setF((v) => ({ ...v, status: e.target.value }))}
            className="h-10 rounded-lg border bg-white px-3"
          >
            <option value="">All statuses</option>
            {[
              "Draft",
              "Internal Review",
              "Approved",
              "Issued",
              "Revision Requested",
              "Accepted",
              "Declined",
              "Superseded",
            ].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
          <select
            aria-label="Filter client decision"
            value={f.decision}
            onChange={(e) => setF((v) => ({ ...v, decision: e.target.value }))}
            className="h-10 rounded-lg border bg-white px-3"
          >
            <option value="">All client decisions</option>
            {["Pending", "Revision Requested", "Accepted", "Declined"].map(
              (v) => (
                <option key={v}>{v}</option>
              ),
            )}
          </select>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[950px] text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                {[
                  "Project",
                  "Client",
                  "Version",
                  "Proposal Total",
                  "Prepared By",
                  "Updated",
                  "Status",
                  "Client Decision",
                  "Actions",
                ].map((h) => (
                  <th key={h} className="px-4 py-3">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y">
              {shown.map((p) => {
                const calc = calculateProposalPricing(
                  p.tradeLines.map((l) => l.clientPrice),
                  p.settings,
                );
                return (
                  <tr key={p.id}>
                    <td className="px-4 py-3 font-semibold">{p.projectName}</td>
                    <td className="px-4 py-3">{p.client}</td>
                    <td className="px-4 py-3">Version {p.version}</td>
                    <td className="px-4 py-3 font-semibold">
                      {formatCurrency(calc.total)}
                    </td>
                    <td className="px-4 py-3">{p.preparedBy}</td>
                    <td className="px-4 py-3">{formatDate(p.updatedAt)}</td>
                    <td className="px-4 py-3">{p.status}</td>
                    <td className="px-4 py-3">{p.clientDecision}</td>
                    <td className="px-4 py-3">
                      <Link
                        href={`/projects/${p.projectId}/proposal`}
                        className="font-semibold text-blue-700"
                      >
                        Open Proposal
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
