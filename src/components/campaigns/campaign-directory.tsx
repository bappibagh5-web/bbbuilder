"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { Search } from "lucide-react";
import type { OutreachCampaign } from "@/types";
import { Card } from "@/components/ui/card";
import { formatDate } from "@/lib/utils";
export function CampaignDirectory({
  campaigns,
  summary,
}: {
  campaigns: OutreachCampaign[];
  summary: {
    active: number;
    sent: number;
    responses: number;
    bids: number;
    followUp: number;
  };
}) {
  const [filters, setFilters] = useState({ search: "", trade: "", status: "" });
  const filtered = useMemo(
    () =>
      campaigns.filter(
        (item) =>
          (!filters.search ||
            item.projectName
              .toLowerCase()
              .includes(filters.search.toLowerCase())) &&
          (!filters.trade || item.trade === filters.trade) &&
          (!filters.status || item.status === filters.status),
      ),
    [campaigns, filters],
  );
  const trades = [...new Set(campaigns.map((c) => c.trade))];
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold">Outreach Campaigns</h1>
        <p className="mt-1 text-sm text-slate-500">
          Manage subcontractor bid invitations, response activity, and
          follow-ups.
        </p>
        <p className="mt-2 text-xs font-medium text-violet-700">
          Demo environment — communication activity shown here is simulated. No
          emails are sent.
        </p>
      </header>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {[
          ["Active Campaigns", summary.active],
          ["Invitations Sent", summary.sent],
          ["Responses", summary.responses],
          ["Bids Submitted", summary.bids],
          ["Needs Follow-Up", summary.followUp],
        ].map(([label, value]) => (
          <Card key={label as string} className="p-4">
            <p className="text-2xl font-semibold">{value}</p>
            <p className="text-xs text-slate-500">{label}</p>
          </Card>
        ))}
      </section>
      <Card>
        <div className="grid gap-3 border-b p-4 md:grid-cols-3">
          <label className="relative">
            <span className="sr-only">Search project</span>
            <Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
            <input
              placeholder="Search project"
              value={filters.search}
              onChange={(e) =>
                setFilters((v) => ({ ...v, search: e.target.value }))
              }
              className="h-10 w-full rounded-lg border pl-9 pr-3"
            />
          </label>
          <label>
            <span className="sr-only">Filter by trade</span>
            <select
              value={filters.trade}
              onChange={(e) =>
                setFilters((v) => ({ ...v, trade: e.target.value }))
              }
              className="h-10 w-full rounded-lg border bg-white px-3"
            >
              <option value="">All trades</option>
              {trades.map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </label>
          <label>
            <span className="sr-only">Filter by campaign status</span>
            <select
              value={filters.status}
              onChange={(e) =>
                setFilters((v) => ({ ...v, status: e.target.value }))
              }
              className="h-10 w-full rounded-lg border bg-white px-3"
            >
              <option value="">All statuses</option>
              {[
                "Draft",
                "Ready for Approval",
                "Active",
                "Needs Follow-Up",
                "Needs Coverage",
                "Complete",
                "Closed",
              ].map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[950px] text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                {[
                  "Project",
                  "Trade",
                  "Recipients",
                  "Sent",
                  "Opened",
                  "Responses",
                  "Bids",
                  "Deadline",
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
              {filtered.map((c) => (
                <tr key={c.id}>
                  <td className="px-4 py-3 font-semibold">{c.projectName}</td>
                  <td className="px-4 py-3">{c.trade}</td>
                  <td className="px-4 py-3">{c.recipientIds.length}</td>
                  <td className="px-4 py-3">{c.sent}</td>
                  <td className="px-4 py-3">{c.opened}</td>
                  <td className="px-4 py-3">{c.responses}</td>
                  <td className="px-4 py-3 font-semibold">{c.bids}</td>
                  <td className="px-4 py-3">{formatDate(c.deadline)}</td>
                  <td className="px-4 py-3">{c.status}</td>
                  <td className="px-4 py-3">
                    <Link
                      className="font-semibold text-blue-700 hover:underline"
                      href={`/projects/${c.projectId}/outreach`}
                    >
                      View Campaign
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="border-t p-4 text-xs text-slate-500">
          Showing {filtered.length} simulated campaigns.
        </p>
      </Card>
    </div>
  );
}
