"use client";
import { useState } from "react";
import Link from "next/link";
import { FileCheck2, Plus, Trash2 } from "lucide-react";
import type {
  ClientDecision,
  Proposal,
  ProposalAllowance,
  ProposalPricingSettings,
  Project,
} from "@/types";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { calculateProposalPricing, formatCurrency } from "@/lib/utils";
const reviewLabels = [
  "Trade costs reviewed",
  "Estimator allowances reviewed",
  "Markup reviewed",
  "Included scope reviewed",
  "Exclusions reviewed",
  "Clarifications reviewed",
  "Schedule reviewed",
  "Commercial terms reviewed",
  "Client-facing preview reviewed",
];
const issueSteps = [
  "Preparing approved proposal",
  "Locking version",
  "Recording issue event",
  "Demo proposal issued",
];
export function ProposalBuilder({
  project,
  initial,
}: {
  project: Project;
  initial: Proposal;
}) {
  const [proposal] = useState(initial);
  const [settings, setSettings] = useState(initial.settings);
  const [allowances, setAllowances] = useState(initial.allowances);
  const [alternates, setAlternates] = useState(initial.alternates);
  const [exclusions, setExclusions] = useState(initial.exclusions);
  const [clarifications, setClarifications] = useState(initial.clarifications);
  const [summary, setSummary] = useState(initial.projectSummary);
  const [display, setDisplay] = useState(
    "Trade Breakdown Without Internal Cost",
  );
  const [checks, setChecks] = useState(new Set<string>());
  const [approved, setApproved] = useState(false);
  const [issued, setIssued] = useState(false);
  const [issuing, setIssuing] = useState(false);
  const [issueStep, setIssueStep] = useState(-1);
  const [decision, setDecision] = useState<ClientDecision>("Pending");
  const [revision, setRevision] = useState(false);
  const [awarded, setAwarded] = useState(false);
  const includedAlternates = alternates
    .filter((a) => a.status === "Included in Base Proposal")
    .map((a) => a.amount);
  const calc = calculateProposalPricing(
    proposal.tradeLines.map((l) => l.clientPrice),
    settings,
    includedAlternates,
  );
  const updateSetting = (key: keyof ProposalPricingSettings, value: number) =>
    setSettings((v) => ({
      ...v,
      [key]: Math.max(
        0,
        Math.min(
          key.includes("Percent") ? 100 : Number.MAX_SAFE_INTEGER,
          Number.isFinite(value) ? value : 0,
        ),
      ),
    }));
  const approveReady = checks.size === reviewLabels.length;
  const simulateIssue = async () => {
    setIssuing(true);
    for (let i = 0; i < issueSteps.length; i++) {
      setIssueStep(i);
      await new Promise((r) =>
        setTimeout(
          r,
          window.matchMedia("(prefers-reduced-motion: reduce)").matches
            ? 70
            : 500,
        ),
      );
    }
    setIssuing(false);
    setIssued(true);
  };
  if (project.id !== "retail-store-coquitlam")
    return (
      <Card className="p-10 text-center">
        <FileCheck2 className="mx-auto h-8 w-8 text-slate-400" />
        <h2 className="mt-4 text-xl font-semibold">
          Proposal Preparation Not Started
        </h2>
        <p className="mt-2 text-sm text-slate-500">
          Trade selections must be reviewed before building a client proposal.
        </p>
      </Card>
    );
  return (
    <div className="min-w-0 max-w-full space-y-5 overflow-x-clip">
      <header>
        <h2 className="text-xl font-semibold">Client Proposal</h2>
        <p className="mt-1 text-sm text-slate-500">
          Build and approve the final general contractor proposal using reviewed
          trade selections and project assumptions.
        </p>
        <p className="mt-1 text-sm font-medium">
          {project.name} · {project.projectNumber} · {project.client} ·{" "}
          {project.city}, {project.province} · Version {proposal.version}
        </p>
        <p className="mt-2 text-xs font-medium text-violet-700">
          Demo environment — proposal pricing and commercial terms shown here
          are simulated.
        </p>
      </header>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        {[
          ["Trade Scopes", "10 / 10 Approved"],
          ["Bid Packages", "10 / 10 Approved"],
          ["Trade Comparisons", "8 / 10 Reviewed"],
          ["Trade Selections", "8 / 10 Approved"],
          ["Estimator Allowances", "2 trades"],
          ["Critical Clarifications", "0"],
        ].map(([l, v]) => (
          <Card key={l} className="p-4">
            <p className="text-sm font-semibold">{v}</p>
            <p className="text-xs text-slate-500">{l}</p>
          </Card>
        ))}
      </section>
      <div className="grid gap-5 xl:grid-cols-[1fr_360px]">
        <main className="min-w-0 space-y-5">
          <Card>
            <header className="border-b p-4">
              <h3 className="font-semibold">Internal Trade Cost Roll-Up</h3>
              <p className="text-xs text-slate-500">
                Internal view · subcontractor costs and markup traceability
              </p>
            </header>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-left text-sm">
                <thead className="bg-slate-50">
                  <tr>
                    {[
                      "Trade",
                      "Selection / Source",
                      "Source Type",
                      "Internal Cost",
                      "Markup / Allocation",
                      "Client Price",
                    ].map((h) => (
                      <th
                        key={h}
                        className="px-3 py-3 text-xs uppercase text-slate-500"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {proposal.tradeLines.map((l) => (
                    <tr key={l.id}>
                      <td className="px-3 py-3 font-semibold">{l.trade}</td>
                      <td className="px-3 py-3">{l.selection}</td>
                      <td className="px-3 py-3">{l.sourceType}</td>
                      <td className="px-3 py-3">
                        {formatCurrency(l.internalCost)}
                      </td>
                      <td className="px-3 py-3">
                        {formatCurrency(l.clientPrice - l.internalCost)}
                      </td>
                      <td className="px-3 py-3 font-semibold">
                        {formatCurrency(l.clientPrice)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <Card className="p-5">
            <h3 className="font-semibold">Pricing Settings</h3>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              {(
                [
                  ["generalConditions", "General Conditions"],
                  ["permitAllowance", "Permit / Administrative Allowance"],
                  ["projectManagement", "Project Management"],
                  ["contingencyPercent", "Contingency %"],
                  ["overheadProfitPercent", "GC Overhead & Profit %"],
                ] as Array<[keyof ProposalPricingSettings, string]>
              ).map(([key, label]) => (
                <label key={key}>
                  <span className="mb-1 block text-xs font-semibold">
                    {label}
                  </span>
                  <input
                    aria-label={label}
                    type="number"
                    min="0"
                    max={key.includes("Percent") ? 100 : undefined}
                    value={settings[key]}
                    onChange={(e) => updateSetting(key, Number(e.target.value))}
                    className="h-10 w-full rounded-lg border px-3"
                  />
                </label>
              ))}
            </div>
          </Card>
          <Managers
            allowances={allowances}
            setAllowances={setAllowances}
            alternates={alternates}
            setAlternates={setAlternates}
          />
          <Card className="p-5">
            <h3 className="font-semibold">Proposal Content</h3>
            <label className="mt-3 block">
              <span className="text-xs font-semibold">
                Demo Project Summary
              </span>
              <textarea
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                rows={4}
                className="mt-1 w-full rounded-lg border p-3 text-sm"
              />
            </label>
            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <label>
                <span className="text-xs font-semibold">
                  Proposal Exclusions
                </span>
                <textarea
                  aria-label="Proposal Exclusions"
                  value={exclusions.join("\n")}
                  onChange={(e) => setExclusions(e.target.value.split("\n"))}
                  rows={8}
                  className="mt-1 w-full rounded-lg border p-3 text-sm"
                />
              </label>
              <label>
                <span className="text-xs font-semibold">
                  Clarifications and Assumptions
                </span>
                <textarea
                  aria-label="Clarifications and Assumptions"
                  value={clarifications.join("\n")}
                  onChange={(e) =>
                    setClarifications(e.target.value.split("\n"))
                  }
                  rows={8}
                  className="mt-1 w-full rounded-lg border p-3 text-sm"
                />
              </label>
            </div>
          </Card>
          <ClientPreview
            proposal={{
              ...proposal,
              projectSummary: summary,
              exclusions,
              clarifications,
              allowances,
              alternates,
              settings,
            }}
            calc={calc}
            display={display}
          />
          <Card className="p-5">
            <h3 className="font-semibold">Version History</h3>
            <div className="mt-3 grid gap-3 sm:grid-cols-3">
              {proposal.versions.map((v) => (
                <div key={v.version} className="rounded-lg border p-3">
                  <p className="font-semibold">Version {v.version}</p>
                  <p className="text-xs text-slate-500">
                    Created {v.createdAt}
                  </p>
                  <p className="mt-1 text-sm">{v.status}</p>
                </div>
              ))}
              {revision && (
                <div className="rounded-lg border border-blue-200 bg-blue-50 p-3">
                  <p className="font-semibold">Version 4</p>
                  <p className="text-xs">Current · Draft</p>
                </div>
              )}
            </div>
          </Card>
        </main>
        <aside className="space-y-5">
          <Card className="p-5">
            <h3 className="font-semibold">Pricing Summary</h3>
            <dl className="mt-4 space-y-2 text-sm">
              {[
                ["Trade Client Prices", calc.tradeSubtotal],
                ["General Conditions", settings.generalConditions],
                ["Permit / Administration", settings.permitAllowance],
                ["Project Management", settings.projectManagement],
                [
                  `Contingency (${settings.contingencyPercent}%)`,
                  calc.contingency,
                ],
                [
                  `GC O&P (${settings.overheadProfitPercent}%)`,
                  calc.overheadProfit,
                ],
                ["Included Alternates", calc.alternateImpact],
                ["Tax · Demo Calculation", calc.tax],
              ].map(([l, v]) => (
                <div key={l as string} className="flex justify-between gap-3">
                  <dt>{l}</dt>
                  <dd className="font-semibold">
                    {formatCurrency(v as number)}
                  </dd>
                </div>
              ))}
            </dl>
            <div className="mt-4 flex justify-between border-t pt-4 text-lg font-semibold">
              <span>Proposal Total</span>
              <span>{formatCurrency(calc.total)}</span>
            </div>
          </Card>
          <Card className="p-5">
            <label className="text-sm font-semibold">
              Client Pricing Display
              <select
                value={display}
                onChange={(e) => setDisplay(e.target.value)}
                className="mt-2 h-10 w-full rounded-lg border bg-white px-3 font-normal"
              >
                <option>Lump Sum Only</option>
                <option>Trade Breakdown Without Internal Cost</option>
                <option>Detailed Client Pricing</option>
              </select>
            </label>
          </Card>
          <Card className="p-5">
            <h3 className="font-semibold">Proposal Review Checklist</h3>
            <div className="mt-3 space-y-2">
              {reviewLabels.map((label) => (
                <label key={label} className="flex gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={checks.has(label)}
                    onChange={(e) => {
                      const next = new Set(checks);
                      if (e.target.checked) next.add(label);
                      else next.delete(label);
                      setChecks(next);
                    }}
                  />
                  {label}
                </label>
              ))}
            </div>
            <Button
              disabled={!approveReady || approved}
              onClick={() => setApproved(true)}
              className="mt-4 w-full bg-primary text-white"
            >
              {approved ? "Proposal Approved" : "Approve Proposal"}
            </Button>
            {approved && (
              <>
                <p className="mt-3 text-sm font-semibold text-emerald-700">
                  Approved By: Alex Morgan · Estimator
                </p>
                <p className="text-xs">
                  Version {proposal.version} · Aug 23, 2026, 5:45 PM
                </p>
                <Button
                  onClick={simulateIssue}
                  disabled={issuing}
                  className="mt-3 w-full"
                >
                  Issue Demo Proposal
                </Button>
              </>
            )}
            {(issuing || issueStep === 3) && (
              <div className="mt-3 rounded bg-violet-50 p-3 text-xs">
                <p className="font-semibold text-violet-800">
                  Demo Issue Simulation — no email or PDF will be sent.
                </p>
                {issueSteps.map((s, i) => (
                  <p
                    key={s}
                    className={i <= issueStep ? "mt-1" : "mt-1 text-slate-400"}
                  >
                    {i < issueStep ? "✓ " : ""}
                    {s}
                  </p>
                ))}
              </div>
            )}
          </Card>
          {issued && (
            <DecisionPanel
              decision={decision}
              setDecision={setDecision}
              onRevision={() => setRevision(true)}
              total={calc.total}
              awarded={awarded}
              setAwarded={setAwarded}
            />
          )}
        </aside>
      </div>
    </div>
  );
}
function Managers({
  allowances,
  setAllowances,
  alternates,
  setAlternates,
}: {
  allowances: ProposalAllowance[];
  setAllowances: React.Dispatch<React.SetStateAction<ProposalAllowance[]>>;
  alternates: Proposal["alternates"];
  setAlternates: React.Dispatch<React.SetStateAction<Proposal["alternates"]>>;
}) {
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card className="p-5">
        <div className="flex justify-between">
          <div>
            <h3 className="font-semibold">Allowances</h3>
            <p className="text-xs text-slate-500">
              Subject to final scope and pricing confirmation.
            </p>
          </div>
          <Button
            onClick={() =>
              setAllowances((v) => [
                ...v,
                {
                  id: `allowance-${v.length + 1}`,
                  name: "New Demo Allowance",
                  amount: 0,
                  description: "Estimator-entered allowance.",
                  includedInTotal: true,
                  clientVisible: true,
                },
              ])
            }
          >
            <Plus className="h-4 w-4" />
            Add
          </Button>
        </div>
        <div className="mt-3 space-y-2">
          {allowances.map((a) => (
            <div key={a.id} className="grid grid-cols-[1fr_120px_auto] gap-2">
              <input
                aria-label={`${a.name} name`}
                value={a.name}
                onChange={(e) =>
                  setAllowances((v) =>
                    v.map((x) =>
                      x.id === a.id ? { ...x, name: e.target.value } : x,
                    ),
                  )
                }
                className="h-9 rounded border px-2 text-sm"
              />
              <input
                aria-label={`${a.name} amount`}
                type="number"
                min="0"
                value={a.amount}
                onChange={(e) =>
                  setAllowances((v) =>
                    v.map((x) =>
                      x.id === a.id
                        ? { ...x, amount: Math.max(0, Number(e.target.value)) }
                        : x,
                    ),
                  )
                }
                className="h-9 rounded border px-2"
              />
              <button
                aria-label={`Remove ${a.name}`}
                onClick={() =>
                  setAllowances((v) => v.filter((x) => x.id !== a.id))
                }
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      </Card>
      <Card className="p-5">
        <h3 className="font-semibold">Alternates</h3>
        <div className="mt-3 space-y-3">
          {alternates.map((a) => (
            <div key={a.id} className="rounded border p-3">
              <div className="flex justify-between">
                <span className="text-sm font-semibold">{a.name}</span>
                <span>{formatCurrency(a.amount)}</span>
              </div>
              <select
                aria-label={`${a.name} status`}
                value={a.status}
                onChange={(e) =>
                  setAlternates((v) =>
                    v.map((x) =>
                      x.id === a.id
                        ? {
                            ...x,
                            status: e.target
                              .value as Proposal["alternates"][number]["status"],
                          }
                        : x,
                    ),
                  )
                }
                className="mt-2 h-9 w-full rounded border bg-white px-2 text-sm"
              >
                <option>Optional Add</option>
                <option>Included in Base Proposal</option>
                <option>Optional Deduct</option>
                <option>Not Included</option>
              </select>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
function ClientPreview({
  proposal,
  calc,
  display,
}: {
  proposal: Proposal;
  calc: ReturnType<typeof calculateProposalPricing>;
  display: string;
}) {
  return (
    <article className="rounded-xl border bg-white p-6 shadow-sm">
      <p className="text-xs font-semibold tracking-[0.2em]">BB BUILDERS</p>
      <h3 className="mt-2 text-2xl font-semibold">
        GENERAL CONTRACTING PROPOSAL
      </h3>
      <dl className="mt-5 grid gap-3 sm:grid-cols-3">
        <div>
          <dt className="text-xs text-slate-500">Project</dt>
          <dd>{proposal.projectName}</dd>
        </div>
        <div>
          <dt className="text-xs text-slate-500">Client</dt>
          <dd>{proposal.client}</dd>
        </div>
        <div>
          <dt className="text-xs text-slate-500">Version</dt>
          <dd>{proposal.version}</dd>
        </div>
      </dl>
      <section className="mt-6">
        <h4 className="font-semibold">Project Summary</h4>
        <p className="mt-2 text-sm leading-6">{proposal.projectSummary}</p>
      </section>
      <section className="mt-5">
        <h4 className="font-semibold">Included Scope</h4>
        <p className="mt-2 text-sm">{proposal.includedScope.join(" · ")}</p>
      </section>
      <section className="mt-5">
        <h4 className="font-semibold">Client Pricing</h4>
        {display !== "Lump Sum Only" && (
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            {proposal.tradeLines.map((l) => (
              <div
                key={l.id}
                className="flex justify-between border-b py-1 text-sm"
              >
                <span>{l.trade}</span>
                <span>{formatCurrency(l.clientPrice)}</span>
              </div>
            ))}
          </div>
        )}
        <p className="mt-4 text-xl font-semibold">
          Proposal Total: {formatCurrency(calc.total)}
        </p>
        <p className="text-xs text-slate-500">
          Taxes shown for demonstration only.
        </p>
      </section>
      {[
        [
          "Allowances",
          proposal.allowances
            .filter((a) => a.clientVisible)
            .map((a) => `${a.name}: ${formatCurrency(a.amount)}`),
        ],
        [
          "Alternates",
          proposal.alternates.map(
            (a) => `${a.name}: ${formatCurrency(a.amount)} · ${a.status}`,
          ),
        ],
        ["Exclusions", proposal.exclusions],
        ["Clarifications & Assumptions", proposal.clarifications],
        ["Schedule", proposal.schedule],
        ["Payment Terms", proposal.paymentTerms],
        ["Warranty", proposal.warranty],
      ].map(([title, items]) => (
        <section key={title as string} className="mt-5">
          <h4 className="font-semibold">{title as string}</h4>
          <ul className="mt-2 list-disc pl-5 text-sm">
            {(items as string[]).map((i) => (
              <li key={i}>{i}</li>
            ))}
          </ul>
        </section>
      ))}
      <div className="mt-8 border-t pt-5 text-sm text-slate-500">
        Signature / Acceptance Placeholder · Demo proposal only
      </div>
    </article>
  );
}
function DecisionPanel({
  decision,
  setDecision,
  onRevision,
  total,
  awarded,
  setAwarded,
}: {
  decision: ClientDecision;
  setDecision: (v: ClientDecision) => void;
  onRevision: () => void;
  total: number;
  awarded: boolean;
  setAwarded: (v: boolean) => void;
}) {
  return (
    <Card className="p-5">
      <h3 className="font-semibold">Issued to Client</h3>
      <p className="mt-1 text-xs">
        Issued Aug 22, 2026 · Version 3 · Demo Client Contact
      </p>
      <p className="mt-3 text-sm font-semibold">Client Decision: {decision}</p>
      <div className="mt-3 grid gap-2">
        <Button onClick={() => setDecision("Accepted")}>
          Mark Demo Accepted
        </Button>
        <Button onClick={() => setDecision("Revision Requested")}>
          Mark Demo Revision Requested
        </Button>
        <Button onClick={() => setDecision("Declined")}>
          Mark Demo Declined
        </Button>
      </div>
      {decision === "Revision Requested" && (
        <div className="mt-3 rounded bg-amber-50 p-3 text-sm">
          <p>
            “Please revise the proposal to separate flooring as an alternate and
            clarify after-hours work.”
          </p>
          <Button onClick={onRevision} className="mt-2">
            Create Demo Revision
          </Button>
        </div>
      )}
      {decision === "Accepted" && (
        <div className="mt-3 rounded bg-emerald-50 p-3">
          <p className="font-semibold text-emerald-800">PROJECT AWARDED</p>
          <p className="text-sm">Accepted value: {formatCurrency(total)}</p>
          <Button onClick={() => setAwarded(true)} className="mt-2">
            Convert to Awarded Project
          </Button>
        </div>
      )}
      {awarded && (
        <div className="mt-3 space-y-1 rounded border p-3 text-sm">
          <p className="font-semibold">Award Handoff</p>
          <p>Trade Selections · Ready</p>
          <p>Approved Proposal · Ready</p>
          <p>Project Contacts · Ready</p>
          <p>Subcontractor Award Packages · Pending</p>
          <p>Insurance / WCB · Pending</p>
          <p>Construction Schedule · Not Created</p>
          <p>Purchase Orders · Not Created</p>
          <Link
            href="/awarded"
            className="mt-2 inline-block font-semibold text-blue-700"
          >
            View Awarded Projects
          </Link>
        </div>
      )}
    </Card>
  );
}
