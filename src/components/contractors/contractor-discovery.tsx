"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CheckCircle2,
  Search,
  ShieldCheck,
  X,
} from "lucide-react";
import type {
  Project,
  ProjectContractorCandidate,
  Subcontractor,
  TradeProcurementStatus,
} from "@/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { contractorDiscoverySummary } from "@/data/contractor-discovery";

const simulationSteps = [
  "Searching trade database",
  "Matching service areas",
  "Checking commercial experience",
  "Removing duplicates",
  "Ranking candidates",
  "Candidates ready for review",
];
const fitLabel = (score: number) =>
  score >= 88
    ? "Strong Fit"
    : score >= 75
      ? "Good Fit"
      : score >= 60
        ? "Review"
        : "Low Fit";
const eligible = (
  candidate: ProjectContractorCandidate,
  company: Subcontractor,
) =>
  company.status === "Active" &&
  company.relationship !== "Do Not Invite" &&
  company.qualificationStatus !== "Unqualified" &&
  company.contactStatus !== "Suppressed" &&
  company.contactStatus !== "Do Not Contact" &&
  candidate.reviewStatus !== "Excluded";

export function ContractorDiscovery({
  project,
  trades,
  initialCandidates,
  companies,
  procurement,
}: {
  project: Project;
  trades: string[];
  initialCandidates: ProjectContractorCandidate[];
  companies: Subcontractor[];
  procurement: TradeProcurementStatus[];
}) {
  const [selectedTrade, setSelectedTrade] = useState("Electrical");
  const [candidates, setCandidates] = useState(initialCandidates);
  const [searching, setSearching] = useState(false);
  const [step, setStep] = useState(-1);
  const [profile, setProfile] = useState<ProjectContractorCandidate | null>(
    null,
  );
  const [selectedIds, setSelectedIds] = useState(new Set<string>());
  const companyMap = useMemo(
    () => new Map(companies.map((item) => [item.id, item])),
    [companies],
  );
  const tradeCandidates = selectedTrade === "Electrical" ? candidates : [];
  const shortlisted = tradeCandidates.filter((item) => item.shortlisted);
  const update = (
    id: string,
    fn: (item: ProjectContractorCandidate) => ProjectContractorCandidate,
  ) =>
    setCandidates((items) =>
      items.map((item) => (item.id === id ? fn(item) : item)),
    );
  const runSearch = async () => {
    setSearching(true);
    for (let index = 0; index < simulationSteps.length; index++) {
      setStep(index);
      const reduce = window.matchMedia(
        "(prefers-reduced-motion: reduce)",
      ).matches;
      await new Promise((resolve) => setTimeout(resolve, reduce ? 80 : 420));
    }
    setSearching(false);
  };
  const shortlist = (id: string) =>
    update(id, (item) => ({
      ...item,
      shortlisted: !item.shortlisted,
      reviewStatus: item.shortlisted ? "Not Reviewed" : item.reviewStatus,
    }));
  const exclude = (id: string, reason = "Capacity concern") =>
    update(id, (item) => ({
      ...item,
      shortlisted: false,
      reviewStatus: "Excluded",
      outreachStatus: "Not Ready",
      exclusionReason: reason,
    }));
  const markNeedsReview = (id: string) =>
    update(id, (item) => ({
      ...item,
      reviewStatus: "Needs Review",
      outreachStatus: "Not Ready",
    }));
  const approveSelected = () => {
    setCandidates((items) =>
      items.map((item) =>
        selectedIds.has(item.id)
          ? {
              ...item,
              reviewStatus: "Approved",
              outreachStatus: "Ready for Outreach",
              approvedBy: "Alex Morgan · Estimator",
              approvedAt: "August 23, 2026 at 3:30 PM",
            }
          : item,
      ),
    );
    setSelectedIds(new Set());
  };
  if (project.id !== "retail-store-coquitlam")
    return (
      <Card className="p-10 text-center">
        <Search className="mx-auto h-8 w-8 text-slate-400" />
        <h2 className="mt-4 text-xl font-semibold">
          Contractor Discovery Not Started
        </h2>
        <p className="mx-auto mt-2 max-w-lg text-sm text-slate-500">
          Approved bid packages are required before fictional project candidates
          can be reviewed for {project.name}.
        </p>
      </Card>
    );
  return (
    <div className="space-y-5">
      <header>
        <h2 className="text-xl font-semibold">Contractor Discovery</h2>
        <p className="mt-1 text-sm text-slate-500">
          Identify and qualify subcontractors for approved trade bid packages.
        </p>
        <p className="mt-1 text-sm font-medium">
          {project.name} · {project.city}, {project.province}
        </p>
        <p className="mt-2 text-xs font-medium text-violet-700">
          Demo environment — contractor discovery results are simulated from
          fictional data.
        </p>
      </header>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          ["Trades Requiring Bids", contractorDiscoverySummary.tradesRequired],
          ["Candidates Found", contractorDiscoverySummary.candidatesIdentified],
          ["Shortlisted", contractorDiscoverySummary.shortlisted],
          [
            "Approved for Outreach",
            contractorDiscoverySummary.approvedForOutreach,
          ],
        ].map(([label, value]) => (
          <Card key={label as string} className="p-4">
            <p className="text-2xl font-semibold">{value}</p>
            <p className="text-xs text-slate-500">{label}</p>
          </Card>
        ))}
      </section>
      <div className="grid gap-5 xl:grid-cols-[280px_1fr]">
        <aside>
          <label className="block xl:hidden">
            <span className="mb-1 block text-sm font-medium">Select trade</span>
            <select
              value={selectedTrade}
              onChange={(e) => setSelectedTrade(e.target.value)}
              className="h-10 w-full rounded-lg border bg-white px-3"
            >
              {trades.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </label>
          <Card className="hidden overflow-hidden xl:block">
            <h3 className="border-b px-4 py-3 text-sm font-semibold">
              Trade Bid Packages
            </h3>
            <nav aria-label="Discovery trades" className="divide-y">
              {trades.map((trade) => {
                const item = procurement.find((p) => p.trade === trade);
                return (
                  <button
                    key={trade}
                    onClick={() => setSelectedTrade(trade)}
                    className={`w-full p-3 text-left ${trade === selectedTrade ? "bg-blue-50" : "hover:bg-slate-50"}`}
                  >
                    <span className="text-sm font-semibold">{trade}</span>
                    <p className="mt-1 text-xs text-slate-500">
                      {item?.approvedRecipients ?? 0} approved · {item?.status}
                    </p>
                  </button>
                );
              })}
            </nav>
          </Card>
        </aside>
        <main className="min-w-0 space-y-5">
          <Card className="p-5">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
              {[
                ["Trade", selectedTrade],
                ["Project", project.name],
                ["Search Location", `${project.city}, ${project.province}`],
                ["Demo Search Radius", "40 km"],
                ["Bid Package", "Approved"],
              ].map(([label, value]) => (
                <div key={label}>
                  <p className="text-xs font-semibold text-slate-500">
                    {label}
                  </p>
                  <p className="mt-1 text-sm font-semibold">{value}</p>
                </div>
              ))}
            </div>
            <div className="mt-5 flex flex-wrap items-center gap-3">
              <Button
                onClick={runSearch}
                disabled={searching}
                className="bg-primary text-white"
              >
                <Search className="h-4 w-4" />
                {searching
                  ? "Running Demo Search…"
                  : "Run Demo Contractor Search"}
              </Button>
              <p className="text-xs text-slate-500">
                Uses centralized fictional records only; no internet search is
                performed.
              </p>
            </div>
            {(searching || step === simulationSteps.length - 1) && (
              <div
                className="mt-4 rounded-lg border bg-slate-50 p-4"
                aria-live="polite"
              >
                <p className="text-xs font-semibold uppercase tracking-wide text-violet-700">
                  Demo Search Simulation
                </p>
                <ol className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {simulationSteps.map((label, index) => (
                    <li
                      key={label}
                      className={`flex items-center gap-2 text-sm ${index <= step ? "text-slate-900" : "text-slate-400"}`}
                    >
                      {index < step ? (
                        <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      ) : (
                        <span className="flex h-4 w-4 items-center justify-center rounded-full border text-[9px]">
                          {index + 1}
                        </span>
                      )}
                      {label}
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </Card>
          {selectedTrade !== "Electrical" ? (
            <Card className="p-8 text-center">
              <Search className="mx-auto h-8 w-8 text-slate-400" />
              <h3 className="mt-3 font-semibold">
                Candidate Review In Progress
              </h3>
              <p className="mt-1 text-sm text-slate-500">
                The richest Task 05 discovery dataset is available under
                Electrical. This trade retains its procurement planning summary.
              </p>
            </Card>
          ) : (
            <>
              <CandidateResults
                candidates={tradeCandidates}
                companyMap={companyMap}
                onShortlist={shortlist}
                onExclude={exclude}
                onNeedsReview={markNeedsReview}
                onProfile={setProfile}
              />
              <BidList
                candidates={shortlisted}
                companyMap={companyMap}
                selectedIds={selectedIds}
                onSelection={setSelectedIds}
                onApprove={approveSelected}
                onRemove={shortlist}
              />
            </>
          )}
        </main>
      </div>
      <ProcurementOverview items={procurement} projectId={project.id} />
      {profile && (
        <CandidateProfile
          candidate={profile}
          company={companyMap.get(profile.subcontractorId)!}
          onClose={() => setProfile(null)}
          onShortlist={() => shortlist(profile.id)}
          onExclude={() => exclude(profile.id)}
        />
      )}
    </div>
  );
}

function CandidateResults({
  candidates,
  companyMap,
  onShortlist,
  onExclude,
  onNeedsReview,
  onProfile,
}: {
  candidates: ProjectContractorCandidate[];
  companyMap: Map<string, Subcontractor>;
  onShortlist: (id: string) => void;
  onExclude: (id: string, reason?: string) => void;
  onNeedsReview: (id: string) => void;
  onProfile: (item: ProjectContractorCandidate) => void;
}) {
  const [reasons, setReasons] = useState<Record<string, string>>({});
  return (
    <Card>
      <header className="border-b p-4">
        <h3 className="font-semibold">Electrical Candidate Results</h3>
        <p className="mt-1 text-xs text-slate-500">
          {candidates.length} fictional candidates ranked with transparent,
          precomputed demo factors.
        </p>
      </header>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1100px] text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              {[
                "Company",
                "Location",
                "Distance",
                "Rating",
                "Experience",
                "Relationship",
                "Qualification",
                "Bid History",
                "Fit Score",
                "Status",
                "Actions",
              ].map((h) => (
                <th key={h} className="px-3 py-3">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y">
            {candidates.map((item) => {
              const company = companyMap.get(item.subcontractorId)!;
              return (
                <tr key={item.id}>
                  <td className="px-3 py-3">
                    <button
                      onClick={() => onProfile(item)}
                      className="font-semibold text-blue-700 hover:underline"
                    >
                      {company.companyName}
                    </button>
                    <p className="text-xs text-slate-500">{company.source}</p>
                  </td>
                  <td className="px-3 py-3">{company.city}, BC</td>
                  <td className="px-3 py-3">{item.distanceKm} km</td>
                  <td className="px-3 py-3">★ {company.rating}</td>
                  <td className="px-3 py-3 text-xs">
                    Commercial: {company.qualification.commercialExperience}
                    <br />
                    Retail: {company.qualification.retailExperience}
                  </td>
                  <td className="px-3 py-3">{company.relationship}</td>
                  <td className="px-3 py-3">
                    <span className="font-semibold">
                      {company.qualificationStatus}
                    </span>
                    <p className="text-xs text-slate-500">
                      Contact: {company.contactStatus}
                    </p>
                  </td>
                  <td className="px-3 py-3">
                    {company.totalBids}/{company.totalInvitations}
                  </td>
                  <td className="px-3 py-3">
                    <button
                      onClick={() => onProfile(item)}
                      className="font-semibold text-blue-700"
                    >
                      {item.fit.overall}/100
                    </button>
                    <p className="text-xs">{fitLabel(item.fit.overall)}</p>
                  </td>
                  <td className="px-3 py-3">{item.reviewStatus}</td>
                  <td className="px-3 py-3">
                    <div className="flex gap-2">
                      <Button
                        onClick={() => onShortlist(item.id)}
                        disabled={item.reviewStatus === "Excluded"}
                      >
                        {item.shortlisted ? "Remove" : "Add to Shortlist"}
                      </Button>
                      <Button
                        onClick={() => onNeedsReview(item.id)}
                        disabled={item.reviewStatus === "Excluded"}
                      >
                        Needs Review
                      </Button>
                      <select
                        aria-label={`Exclusion reason for ${company.companyName}`}
                        value={reasons[item.id] ?? "Capacity concern"}
                        onChange={(event) =>
                          setReasons((current) => ({
                            ...current,
                            [item.id]: event.target.value,
                          }))
                        }
                        className="h-9 max-w-36 rounded-lg border bg-white px-2 text-xs"
                        disabled={item.reviewStatus === "Excluded"}
                      >
                        {[
                          "Outside service area",
                          "Insufficient commercial experience",
                          "Qualification incomplete",
                          "Capacity concern",
                          "Poor historical response",
                          "Conflict / unavailable",
                          "Other",
                        ].map((reason) => (
                          <option key={reason}>{reason}</option>
                        ))}
                      </select>
                      <Button
                        onClick={() => onExclude(item.id, reasons[item.id])}
                        disabled={item.reviewStatus === "Excluded"}
                      >
                        Exclude
                      </Button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="border-t p-4 text-xs text-slate-500">
        Fit score is a demo prioritization tool. Final contractor selection
        remains a human decision.
      </p>
    </Card>
  );
}
function BidList({
  candidates,
  companyMap,
  selectedIds,
  onSelection,
  onApprove,
  onRemove,
}: {
  candidates: ProjectContractorCandidate[];
  companyMap: Map<string, Subcontractor>;
  selectedIds: Set<string>;
  onSelection: (ids: Set<string>) => void;
  onApprove: () => void;
  onRemove: (id: string) => void;
}) {
  const eligibleIds = candidates
    .filter((c) => eligible(c, companyMap.get(c.subcontractorId)!))
    .map((c) => c.id);
  return (
    <Card>
      <header className="border-b p-4">
        <h3 className="font-semibold">Electrical Bid List</h3>
        <p className="mt-1 text-xs text-slate-500">
          {candidates.length} shortlisted ·{" "}
          {
            candidates.filter((c) => c.outreachStatus === "Ready for Outreach")
              .length
          }{" "}
          approved for outreach
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button onClick={() => onSelection(new Set(eligibleIds))}>
            Select All Eligible
          </Button>
          <Button onClick={() => onSelection(new Set())}>
            Clear Selection
          </Button>
          <Button
            disabled={!selectedIds.size}
            onClick={onApprove}
            className="bg-primary text-white"
          >
            Approve Selected Contractors ({selectedIds.size})
          </Button>
        </div>
      </header>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[920px] text-left text-sm">
          <thead className="bg-slate-50">
            <tr>
              {[
                "Select",
                "Company",
                "Relationship",
                "Qualification",
                "Fit",
                "Bid History",
                "Review Status",
                "Outreach Status",
                "Actions",
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
            {candidates.map((item) => {
              const company = companyMap.get(item.subcontractorId)!;
              const canSelect = eligible(item, company);
              return (
                <tr key={item.id}>
                  <td className="px-3 py-3">
                    <input
                      aria-label={`Select ${company.companyName}`}
                      type="checkbox"
                      checked={selectedIds.has(item.id)}
                      disabled={!canSelect}
                      onChange={(e) => {
                        const next = new Set(selectedIds);
                        if (e.target.checked) next.add(item.id);
                        else next.delete(item.id);
                        onSelection(next);
                      }}
                    />
                  </td>
                  <td className="px-3 py-3 font-semibold">
                    {company.companyName}
                  </td>
                  <td className="px-3 py-3">{company.relationship}</td>
                  <td className="px-3 py-3">
                    {company.qualificationStatus}
                    <p className="text-xs text-slate-500">
                      {company.contactStatus}
                    </p>
                  </td>
                  <td className="px-3 py-3">
                    {item.fit.overall} · {fitLabel(item.fit.overall)}
                  </td>
                  <td className="px-3 py-3">
                    {company.totalBids}/{company.totalInvitations}
                  </td>
                  <td className="px-3 py-3">{item.reviewStatus}</td>
                  <td className="px-3 py-3">
                    <span
                      className={
                        item.outreachStatus === "Ready for Outreach"
                          ? "font-semibold text-emerald-700"
                          : "text-slate-500"
                      }
                    >
                      {item.outreachStatus}
                    </span>
                    {item.approvedBy && (
                      <p className="text-xs text-slate-500">
                        {item.approvedBy}
                      </p>
                    )}
                  </td>
                  <td className="px-3 py-3">
                    <Button onClick={() => onRemove(item.id)}>Remove</Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="border-t p-4 text-xs text-slate-500">
        In production, recipient approval would be recorded in the project audit
        trail before invitations are sent. No email is sent in this demo.
      </p>
    </Card>
  );
}
function CandidateProfile({
  candidate,
  company,
  onClose,
  onShortlist,
  onExclude,
}: {
  candidate: ProjectContractorCandidate;
  company: Subcontractor;
  onClose: () => void;
  onShortlist: () => void;
  onExclude: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-slate-950/45"
      role="dialog"
      aria-modal="true"
      aria-label="Contractor profile"
    >
      <div className="h-full w-full max-w-2xl overflow-y-auto bg-white">
        <header className="sticky top-0 flex items-center justify-between border-b bg-white p-5">
          <div>
            <p className="text-xs font-semibold text-violet-700">
              Fictional demo contractor
            </p>
            <h2 className="font-semibold">{company.companyName}</h2>
          </div>
          <button onClick={onClose} aria-label="Close contractor profile">
            <X className="h-5 w-5" />
          </button>
        </header>
        <div className="space-y-5 p-5">
          <section>
            <h3 className="font-semibold">Company Overview</h3>
            <p className="mt-2 text-sm">
              {company.primaryTrade} · {company.city}, BC ·{" "}
              {candidate.distanceKm} km from project
            </p>
            <p className="text-sm text-slate-500">
              {company.email} · {company.phone}
            </p>
          </section>
          <section>
            <h3 className="font-semibold">Qualification Flags</h3>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              {Object.entries(company.qualification).map(([key, value]) => (
                <div key={key} className="rounded-lg border p-3">
                  <p className="text-xs capitalize text-slate-500">
                    {key.replace(/([A-Z])/g, " $1")}
                  </p>
                  <p className="text-sm font-semibold">{value}</p>
                </div>
              ))}
            </div>
          </section>
          <section>
            <h3 className="font-semibold">
              Fit Analysis · {candidate.fit.overall}/100 ·{" "}
              {fitLabel(candidate.fit.overall)}
            </h3>
            <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {Object.entries(candidate.fit)
                .filter(([, value]) => typeof value === "number")
                .map(([label, value]) => (
                  <div key={label} className="rounded bg-slate-50 p-2">
                    <p className="text-xs capitalize text-slate-500">
                      {label.replace(/([A-Z])/g, " $1")}
                    </p>
                    <p className="font-semibold">{value as number}</p>
                  </div>
                ))}
            </div>
            <h4 className="mt-4 text-sm font-semibold">Why</h4>
            <ul className="mt-1 list-disc pl-5 text-sm">
              {candidate.fit.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
            <h4 className="mt-3 text-sm font-semibold">Concerns</h4>
            <ul className="mt-1 list-disc pl-5 text-sm">
              {(candidate.fit.concerns.length
                ? candidate.fit.concerns
                : ["No material demo concerns recorded"]
              ).map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </section>
          <section>
            <h3 className="font-semibold">Demo Discovery Source</h3>
            <dl className="mt-2 rounded-lg border p-3 text-sm">
              <dt className="text-xs text-slate-500">Discovery Source</dt>
              <dd>{candidate.discoverySourceLabel}</dd>
              <dt className="mt-2 text-xs text-slate-500">Search Query</dt>
              <dd>{candidate.searchQuery}</dd>
              <dt className="mt-2 text-xs text-slate-500">Search Area</dt>
              <dd>{candidate.searchArea}</dd>
            </dl>
          </section>
          <section>
            <h3 className="font-semibold">Internal Notes</h3>
            <p className="mt-2 text-sm text-slate-600">{company.notes}</p>
          </section>
          <div className="flex flex-wrap gap-2 border-t pt-4">
            <Button onClick={onShortlist}>
              {candidate.shortlisted
                ? "Remove from Shortlist"
                : "Add to Shortlist"}
            </Button>
            <Button onClick={onExclude}>Exclude from Bid</Button>
          </div>
        </div>
      </div>
    </div>
  );
}
function ProcurementOverview({
  items,
  projectId,
}: {
  items: TradeProcurementStatus[];
  projectId: string;
}) {
  return (
    <div className="grid gap-5 xl:grid-cols-[1fr_360px]">
      <Card>
        <header className="border-b p-4">
          <h3 className="font-semibold">All-Trade Procurement Overview</h3>
        </header>
        <div className="grid gap-px bg-slate-200 sm:grid-cols-2 lg:grid-cols-5">
          {items.map((item) => (
            <div key={item.trade} className="bg-white p-4">
              <p className="text-sm font-semibold">{item.trade}</p>
              <p className="mt-1 text-2xl font-semibold">
                {item.approvedRecipients}
              </p>
              <p className="text-xs text-slate-500">
                approved recipients · target {item.targetBids}
              </p>
              <p
                className={`mt-2 text-xs font-semibold ${item.status === "Ready" ? "text-emerald-700" : "text-amber-700"}`}
              >
                {item.status}
              </p>
            </div>
          ))}
        </div>
      </Card>
      <Card className="p-5">
        <h3 className="font-semibold">Procurement Readiness</h3>
        <dl className="mt-4 space-y-3 text-sm">
          <div className="flex justify-between">
            <dt>Approved trade scopes</dt>
            <dd className="font-semibold">10 / 10</dd>
          </div>
          <div className="flex justify-between">
            <dt>Bid packages ready</dt>
            <dd className="font-semibold">10 / 10</dd>
          </div>
          <div className="flex justify-between">
            <dt>Recipient lists approved</dt>
            <dd className="font-semibold">8 / 10 trades</dd>
          </div>
        </dl>
        <div className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mb-1 h-4 w-4" />
          Needs more candidates: Flooring, Fire Protection
        </div>
        <Link
          href={`/projects/${projectId}/outreach`}
          className="mt-4 inline-flex h-10 w-full items-center justify-center rounded-lg bg-primary px-4 text-sm font-semibold text-white"
        >
          Continue to Outreach
        </Link>
        <p className="mt-3 flex gap-2 text-xs text-slate-500">
          <ShieldCheck className="h-4 w-4 shrink-0" />
          This is demo planning data. Outreach remains a separate
          human-controlled workflow.
        </p>
      </Card>
    </div>
  );
}
