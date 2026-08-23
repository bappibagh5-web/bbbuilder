import type { Metadata } from "next";
import Link from "next/link";
import { ActivityFeed } from "@/components/activity-feed";
import { AttentionPanel } from "@/components/attention-panel";
import { MetricCard } from "@/components/metric-card";
import { PageHeader } from "@/components/page-header";
import { ProjectTable } from "@/components/project-table";
import { DashboardContractorDiscovery } from "@/components/contractors/dashboard-contractor-discovery";
import {
  attentionItems,
  dashboardMetrics,
  projects,
  recentActivity,
  procurementStatuses,
} from "@/data";
export const metadata: Metadata = { title: "Dashboard" };
export default function DashboardPage() {
  const primaryProject = projects.find(
    (project) => project.id === "retail-store-coquitlam",
  )!;
  return (
    <div className="mx-auto max-w-[1500px]">
      <PageHeader
        title="Dashboard"
        description="Monitor active bids, reviews, and preconstruction activity across your portfolio."
      />
      <section
        aria-label="Bid metrics"
        className="mt-7 grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
      >
        {dashboardMetrics.map((metric, index) => (
          <MetricCard key={metric.label} {...metric} index={index} />
        ))}
      </section>
      <section
        className="mt-6 flex flex-col gap-3 rounded-xl border border-blue-200 bg-blue-50/60 px-5 py-4 sm:flex-row sm:items-center sm:justify-between"
        aria-label="New bid opportunities"
      >
        <div>
          <h2 className="font-semibold text-slate-900">
            New Bid Opportunities
          </h2>
          <p className="mt-0.5 text-sm text-slate-600">
            3 awaiting initial review and a human Go / No-Go decision.
          </p>
        </div>
        <Link
          href="/bid-opportunities"
          className="inline-flex min-h-10 items-center justify-center rounded-lg bg-primary px-4 text-sm font-semibold text-white"
        >
          Review Opportunities
        </Link>
      </section>
      <section className="mt-6">
        <ProjectTable projects={projects} />
      </section>
      <DashboardContractorDiscovery
        project={primaryProject}
        procurement={procurementStatuses}
      />
      <section className="mt-6 grid gap-6 xl:grid-cols-2">
        <AttentionPanel items={attentionItems} />
        <ActivityFeed events={recentActivity} />
      </section>
    </div>
  );
}
