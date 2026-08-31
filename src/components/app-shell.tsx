"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  Activity,
  BarChart3,
  Bell,
  Building2,
  ClipboardList,
  FileChartColumn,
  FolderKanban,
  Gavel,
  LayoutDashboard,
  LogOut,
  Menu,
  MonitorPlay,
  PanelLeftClose,
  Presentation,
  Search,
  Send,
  Settings,
  Users,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { roleLabel } from "@/lib/auth";
import { useAuth } from "@/components/auth/auth-provider";
import { useOrganization } from "@/components/organizations/organization-provider";
import { DemoNotice } from "./demo-notice";
import { Button } from "./ui/button";

const groups = [
  {
    label: null,
    items: [{ label: "Dashboard", href: "/dashboard", icon: LayoutDashboard }],
  },
  {
    label: "Preconstruction",
    items: [
      {
        label: "Bid Opportunities",
        href: "/bid-opportunities",
        icon: ClipboardList,
      },
      { label: "Projects", href: "/projects", icon: FolderKanban },
      { label: "Subcontractors", href: "/subcontractors", icon: Users },
    ],
  },
  {
    label: "Procurement",
    items: [
      { label: "Outreach Campaigns", href: "/campaigns", icon: Send },
      { label: "Bid Comparisons", href: "/comparisons", icon: BarChart3 },
      { label: "Client Proposals", href: "/proposals", icon: FileChartColumn },
    ],
  },
  {
    label: "Projects",
    items: [{ label: "Awarded Projects", href: "/awarded", icon: Gavel }],
  },
  {
    label: "System",
    items: [
      { label: "Activity", href: "/activity", icon: Activity },
      { label: "Settings", href: "/settings", icon: Settings },
    ],
  },
];

const guideSteps = [
  ["1", "Bid Opportunities", "/bid-opportunities"],
  ["2", "Open Project", "/projects/retail-store-coquitlam"],
  ["3", "Review Documents", "/projects/retail-store-coquitlam/documents"],
  ["4", "Review AI Findings", "/projects/retail-store-coquitlam/ai-review"],
  ["5", "Review Trade Scopes", "/projects/retail-store-coquitlam/scopes"],
  [
    "6",
    "View Subcontractor Discovery",
    "/projects/retail-store-coquitlam/contractors",
  ],
  ["7", "View Outreach", "/projects/retail-store-coquitlam/outreach"],
  ["8", "Open Bid Inbox", "/projects/retail-store-coquitlam/bids"],
  [
    "9",
    "Compare Electrical Bids",
    "/projects/retail-store-coquitlam/comparisons",
  ],
  ["10", "Review Client Proposal", "/projects/retail-store-coquitlam/proposal"],
  ["11", "View Award Handoff", "/awarded"],
] as const;

function Sidebar({
  open,
  onClose,
  presentation,
}: {
  open: boolean;
  onClose: () => void;
  presentation: boolean;
}) {
  const path = usePathname();
  return (
    <>
      <button
        aria-label="Close navigation overlay"
        onClick={onClose}
        className={cn(
          "fixed inset-0 z-30 bg-slate-950/45 transition-opacity lg:hidden",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
      />
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-[268px] flex-col bg-sidebar text-white transition-transform lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex h-[72px] items-center justify-between border-b border-white/10 px-5">
          <Link
            href="/dashboard"
            onClick={onClose}
            className="flex items-center gap-3 rounded-md focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white"
          >
            <span className="grid h-9 w-9 place-items-center rounded-lg bg-white text-sidebar">
              <Building2 className="h-5 w-5" />
            </span>
            <span>
              <strong className="block text-sm tracking-[.12em]">
                BB BUILDERS
              </strong>
              <span className="text-[10px] uppercase tracking-[.16em] text-sidebar-muted">
                Preconstruction
              </span>
            </span>
          </Link>
          <button
            onClick={onClose}
            aria-label="Close navigation"
            className="rounded-md p-2 text-sidebar-muted hover:bg-white/10 lg:hidden"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <nav
          aria-label="Primary navigation"
          className="flex-1 overflow-y-auto px-3 py-4"
        >
          {groups.map((group, index) => (
            <div
              key={group.label ?? "main"}
              className={cn(index > 0 && "mt-6")}
            >
              {group.label && (
                <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[.16em] text-sidebar-muted/70">
                  {group.label}
                </p>
              )}
              <div className="space-y-1">
                {group.items.map((item) => {
                  const active =
                    path === item.href ||
                    (item.href !== "/dashboard" &&
                      path.startsWith(`${item.href}/`));
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={onClose}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "flex min-h-11 items-center gap-3 rounded-lg px-3 py-2.5 text-[13px] font-medium text-sidebar-muted transition-colors hover:bg-white/[.07] hover:text-white focus-visible:outline-2 focus-visible:outline-white",
                        active && "bg-white/[.1] text-white",
                      )}
                    >
                      <Icon className="h-[17px] w-[17px]" />
                      {item.label}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
        <div className="border-t border-white/10 p-4">
          <div className="rounded-lg bg-white/[.06] p-3">
            <p className="text-xs font-medium">
              {presentation ? "Presentation Mode" : "Demo Environment"}
            </p>
            <p className="mt-1 text-[11px] leading-4 text-sidebar-muted">
              Project records are persistent. Later workflow data remains simulated.
            </p>
          </div>
        </div>
      </aside>
    </>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const { memberships, activeMembership, selectOrganization } = useOrganization();
  const [navOpen, setNavOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [noticeOpen, setNoticeOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const [presentation, setPresentation] = useState(false);
  const displayName = [user?.firstName, user?.lastName].filter(Boolean).join(" ") || user?.email || "Member";
  const initials = displayName
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
  return (
    <div className="min-h-screen">
      <Sidebar
        open={navOpen}
        onClose={() => setNavOpen(false)}
        presentation={presentation}
      />
      <div className="lg:pl-[268px]">
        <header className="sticky top-0 z-20 flex h-[72px] items-center justify-between border-b bg-white/95 px-4 backdrop-blur-sm sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setNavOpen(true)}
              aria-label="Open navigation"
              className="rounded-lg border p-2 text-slate-600 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 lg:hidden"
            >
              <Menu className="h-5 w-5" />
            </button>
            <div className="hidden items-center gap-2 text-sm text-slate-500 sm:flex">
              <PanelLeftClose className="h-4 w-4" />
              <span>
                {presentation ? "Client Presentation" : "Bid Management"}
              </span>
            </div>
          </div>
          <div className="relative flex items-center gap-2">
            {!presentation && searchOpen && (
              <label className="absolute right-[244px] top-0 hidden sm:block">
                <span className="sr-only">Search demo</span>
                <input
                  autoFocus
                  placeholder="Search projects..."
                  className="h-9 w-64 rounded-lg border bg-slate-50 px-3 text-sm outline-none focus:border-blue-600"
                />
              </label>
            )}
            {!presentation && (
              <Button
                onClick={() => setSearchOpen((value) => !value)}
                aria-label={searchOpen ? "Close search" : "Open search"}
                aria-expanded={searchOpen}
                className="w-9 px-0"
              >
                <Search className="h-4 w-4" />
              </Button>
            )}
            {!presentation && (
              <div className="relative">
                <Button
                  onClick={() => setNoticeOpen((value) => !value)}
                  aria-label="View notifications"
                  aria-expanded={noticeOpen}
                  className="relative w-9 px-0"
                >
                  <Bell className="h-4 w-4" />
                  <span className="absolute right-2 top-2 h-1.5 w-1.5 rounded-full bg-red-500" />
                </Button>
                {noticeOpen && (
                  <div className="absolute right-0 top-12 w-72 rounded-xl border bg-white p-4 shadow-lg">
                    <p className="text-sm font-semibold">
                      Items requiring attention
                    </p>
                    <p className="mt-1 text-xs leading-5 text-slate-500">
                      Five reviews are ready for an estimator on the dashboard.
                    </p>
                  </div>
                )}
              </div>
            )}
            <Button
              onClick={() => setGuideOpen(true)}
              aria-label="Open demo guide"
            >
              <MonitorPlay className="h-4 w-4" />
              <span className="hidden md:inline">Demo Guide</span>
            </Button>
            <Button
              onClick={() => setPresentation((value) => !value)}
              aria-pressed={presentation}
              className={cn(
                presentation &&
                  "border-blue-700 bg-blue-700 text-white hover:bg-blue-800",
              )}
            >
              <Presentation className="h-4 w-4" />
              <span className="hidden xl:inline">Presentation Mode</span>
            </Button>
            <div className="ml-1 hidden items-center gap-2 border-l pl-3 sm:flex">
              <span className="grid h-9 w-9 place-items-center rounded-full bg-[#dce8f0] text-xs font-bold text-[#163451]">
                {initials}
              </span>
              <div className="hidden lg:block">
                <p className="text-xs font-semibold text-slate-800">
                  {displayName}
                </p>
                <p className="text-[11px] text-slate-500">
                  {roleLabel(activeMembership?.role)}
                </p>
              </div>
              <button
                type="button"
                onClick={() => void logout()}
                title="Sign out"
                aria-label="Sign out"
                className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              >
                <LogOut className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </header>
        {presentation && (
          <div className="border-b bg-blue-50 px-4 py-2 text-center text-xs font-medium text-blue-900">
            Presentation Mode · Project records are persistent; later workflows remain demo data.
          </div>
        )}
        {memberships.length > 1 && (
          <div className="border-b bg-white px-4 py-2 sm:px-6 lg:px-8">
            <label className="flex flex-wrap items-center gap-2 text-xs font-medium text-slate-600">
              Organization
              <select
                value={activeMembership?.organization.slug ?? ""}
                onChange={(event) => selectOrganization(event.target.value)}
                className="h-8 rounded-md border bg-white px-2 text-xs text-slate-800"
              >
                <option value="" disabled>Select an organization</option>
                {memberships.map((membership) => (
                  <option key={membership.id} value={membership.organization.slug}>
                    {membership.organization.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}
        <main className="min-w-0 overflow-x-clip px-4 py-7 sm:px-6 lg:px-8 lg:py-8">
          {children}
        </main>
      </div>
      {guideOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="demo-guide-title"
          className="fixed inset-0 z-50 grid place-items-center bg-slate-950/50 p-4"
          onMouseDown={(event) =>
            event.target === event.currentTarget && setGuideOpen(false)
          }
        >
          <div className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-2xl bg-white p-5 shadow-2xl sm:p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2
                  id="demo-guide-title"
                  className="text-lg font-semibold text-slate-900"
                >
                  Demo Guide
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  Recommended walkthrough for the Retail Store Tenant
                  Improvement project.
                </p>
              </div>
              <button
                autoFocus
                onClick={() => setGuideOpen(false)}
                aria-label="Close demo guide"
                className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-blue-700"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <DemoNotice className="mt-4" />
            <ol className="mt-4 grid gap-2 sm:grid-cols-2">
              {guideSteps.map(([number, label, href]) => (
                <li key={number}>
                  <Link
                    href={href}
                    onClick={() => setGuideOpen(false)}
                    className="flex min-h-12 items-center gap-3 rounded-xl border px-3 py-2 text-sm font-medium text-slate-800 transition hover:border-blue-300 hover:bg-blue-50 focus-visible:outline-2 focus-visible:outline-blue-700"
                  >
                    <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-slate-100 text-xs font-bold text-slate-600">
                      {number}
                    </span>
                    {label}
                  </Link>
                </li>
              ))}
            </ol>
          </div>
        </div>
      )}
    </div>
  );
}
