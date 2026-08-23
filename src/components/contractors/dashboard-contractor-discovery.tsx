import Link from "next/link";
import { ArrowRight, CheckCircle2, Users, AlertTriangle } from "lucide-react";
import type { Project, TradeProcurementStatus } from "@/types";
import { Card } from "@/components/ui/card";
import { contractorDiscoverySummary } from "@/data/contractor-discovery";

export function DashboardContractorDiscovery({
  project,
  procurement,
}: {
  project: Project;
  procurement: TradeProcurementStatus[];
}) {
  const ready = procurement
    .filter((item) => item.status === "Ready")
    .filter((item) => ["Electrical", "Plumbing", "HVAC"].includes(item.trade));
  const attention = procurement.filter(
    (item) => item.status === "Needs More Candidates",
  );

  const metrics = [
    ["Candidates Identified", contractorDiscoverySummary.candidatesIdentified],
    ["Shortlisted", contractorDiscoverySummary.shortlisted],
    ["Approved for Outreach", contractorDiscoverySummary.approvedForOutreach],
    [
      "Trades Ready",
      `${contractorDiscoverySummary.tradesReady} / ${contractorDiscoverySummary.tradesRequired}`,
    ],
    [
      "Trades Needing More Candidates",
      contractorDiscoverySummary.tradesNeedingMoreCandidates,
    ],
  ] as const;

  return (
    <Card className="mt-6 overflow-hidden">
      <header className="flex flex-col gap-4 border-b px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="font-semibold text-slate-900">Contractor Discovery</h2>
          <p className="mt-0.5 text-xs text-slate-500">
            Monitor subcontractor sourcing and trade coverage across active
            bids.
          </p>
        </div>
        <Link
          href={`/projects/${project.id}/contractors`}
          className="inline-flex min-h-10 items-center justify-center gap-2 self-start rounded-lg bg-primary px-4 text-sm font-semibold text-white transition hover:bg-primary/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 sm:self-auto"
        >
          Find Subcontractors
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </Link>
      </header>

      <div className="p-5">
        <div className="flex items-start gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-slate-100 text-slate-600">
            <Users className="h-5 w-5" aria-hidden="true" />
          </span>
          <div>
            <p className="font-semibold text-slate-900">{project.name}</p>
            <p className="mt-0.5 text-sm text-slate-500">
              {project.city}, {project.province} · {project.projectNumber}
            </p>
          </div>
        </div>

        <dl className="mt-5 grid gap-px overflow-hidden rounded-xl border bg-slate-200 sm:grid-cols-2 xl:grid-cols-5">
          {metrics.map(([label, value]) => (
            <div key={label} className="bg-white p-4">
              <dd className="text-xl font-semibold tabular-nums text-slate-900">
                {value}
              </dd>
              <dt className="mt-1 text-xs leading-5 text-slate-500">{label}</dt>
            </div>
          ))}
        </dl>

        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          <section
            aria-labelledby="ready-trades-title"
            className="rounded-xl border p-4"
          >
            <div className="flex items-center gap-2">
              <CheckCircle2
                className="h-4 w-4 text-emerald-700"
                aria-hidden="true"
              />
              <h3
                id="ready-trades-title"
                className="text-sm font-semibold text-slate-900"
              >
                Ready Trades
              </h3>
              <span className="ml-auto text-xs font-semibold text-emerald-700">
                {contractorDiscoverySummary.tradesReady} of{" "}
                {contractorDiscoverySummary.tradesRequired}
              </span>
            </div>
            <ul className="mt-3 divide-y">
              {ready.map((item) => (
                <li
                  key={item.trade}
                  className="flex items-center justify-between gap-4 py-2 text-sm first:pt-0 last:pb-0"
                >
                  <span className="font-medium text-slate-800">
                    {item.trade}
                  </span>
                  <span className="text-right text-xs text-slate-500">
                    {item.approvedRecipients} approved recipients ·{" "}
                    <strong className="text-emerald-700">Ready</strong>
                  </span>
                </li>
              ))}
            </ul>
          </section>

          <section
            aria-labelledby="coverage-attention-title"
            className="rounded-xl border border-amber-200 bg-amber-50/50 p-4"
          >
            <div className="flex items-center gap-2">
              <AlertTriangle
                className="h-4 w-4 text-amber-700"
                aria-hidden="true"
              />
              <h3
                id="coverage-attention-title"
                className="text-sm font-semibold text-slate-900"
              >
                Coverage Requiring Attention
              </h3>
              <span className="ml-auto text-xs font-semibold text-amber-800">
                {attention.length} trades
              </span>
            </div>
            <ul className="mt-3 divide-y divide-amber-200">
              {attention.map((item) => (
                <li
                  key={item.trade}
                  className="flex items-center justify-between gap-4 py-2 text-sm first:pt-0 last:pb-0"
                >
                  <span className="font-medium text-slate-800">
                    {item.trade}
                  </span>
                  <span className="text-right text-xs text-slate-600">
                    {item.approvedRecipients} approved recipients ·{" "}
                    <strong className="text-amber-800">
                      Needs More Candidates
                    </strong>
                  </span>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </Card>
  );
}
