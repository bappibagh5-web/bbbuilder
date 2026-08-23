import Link from "next/link";
import type { AwardedProject } from "@/types";
import { Card } from "@/components/ui/card";
import { formatCurrency } from "@/lib/utils";
export function AwardedDirectory({
  items,
  summary,
}: {
  items: AwardedProject[];
  summary: {
    active: number;
    tradeAwards: number;
    compliance: number;
    schedules: number;
  };
}) {
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold">Awarded Projects</h1>
        <p className="mt-1 text-sm text-slate-500">
          Transition successful bids into active construction projects.
        </p>
        <p className="mt-2 text-xs font-medium text-violet-700">
          Demo environment — award, compliance, and project setup statuses shown
          here are simulated.
        </p>
      </header>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          ["Active Awarded Projects", summary.active],
          ["Awaiting Trade Awards", summary.tradeAwards],
          ["Compliance Documents Pending", summary.compliance],
          ["Schedules Pending", summary.schedules],
        ].map(([l, v]) => (
          <Card key={l as string} className="p-4">
            <p className="text-2xl font-semibold">{v}</p>
            <p className="text-xs text-slate-500">{l}</p>
          </Card>
        ))}
      </section>
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[950px] text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                {[
                  "Project",
                  "Client",
                  "Contract Value",
                  "Awarded Date",
                  "Trade Awards",
                  "Compliance",
                  "Schedule",
                  "Project Status",
                  "Actions",
                ].map((h) => (
                  <th key={h} className="px-4 py-3">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y">
              {items.map((i) => (
                <tr key={i.id}>
                  <td className="px-4 py-3 font-semibold">{i.projectName}</td>
                  <td className="px-4 py-3">{i.client}</td>
                  <td className="px-4 py-3 font-semibold">
                    {formatCurrency(i.contractValue)}
                  </td>
                  <td className="px-4 py-3">{i.awardedAt}</td>
                  <td className="px-4 py-3">{i.tradeAwards}</td>
                  <td className="px-4 py-3">{i.compliance}</td>
                  <td className="px-4 py-3">{i.schedule}</td>
                  <td className="px-4 py-3">{i.status}</td>
                  <td className="px-4 py-3">
                    <Link
                      href={`/projects/${i.projectId}`}
                      className="font-semibold text-blue-700"
                    >
                      Open Project
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
