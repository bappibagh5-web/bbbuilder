"use client";

import { AlertTriangle, Building2, CheckCircle2, ChevronDown, MapPin, Search, Users } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ContractorProfilePanel } from "@/components/contractors/contractor-profile-panel";
import { Card } from "@/components/ui/card";
import type { OrganizationMembership } from "@/lib/auth";
import {
  canManageContractors,
  contractorFitBand,
  contractorRankingSignals,
  contractorSearchResultMessage,
  contractorSourceLabel,
  filterContractors,
  replaceCandidate,
  sortContractors,
  type ContractorSort,
} from "@/lib/contractor-discovery-state";
import {
  contractorsApi,
  type ContractorCandidate,
  type ContractorCompanyProfile,
  type ContractorContactInput,
  type ContractorContactEnrichment,
  type TradeCoverage,
} from "@/lib/contractors";
import type { ProductionProject } from "@/lib/projects";

type ReadyTrade = TradeCoverage;

export function ProductionContractorsModule({ project, membership }: { project: ProductionProject; membership: OrganizationMembership }) {
  const slug = membership.organization.slug;
  const canManage = canManageContractors(membership.role) && project.is_active;
  const [coverage, setCoverage] = useState<TradeCoverage[]>([]);
  const [candidates, setCandidates] = useState<Record<number, ContractorCandidate[]>>({});
  const [expanded, setExpanded] = useState<number | null>(null);
  const [candidateLoading, setCandidateLoading] = useState<number | null>(null);
  const [candidateErrors, setCandidateErrors] = useState<Record<number, string>>({});
  const [minimumTarget, setMinimumTarget] = useState(3);
  const [shortlistedOnly, setShortlistedOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<number | null>(null);
  const [profile, setProfile] = useState<ContractorCompanyProfile | null>(null);
  const profileRef = useRef<HTMLDivElement>(null);
  const [profileBusy, setProfileBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchMessages, setSearchMessages] = useState<Record<number, string>>({});

  useEffect(() => {
    const controller = new AbortController();
    contractorsApi.coverage(slug, project.id, controller.signal)
      .then((result) => {
        setCoverage(result.trades);
        setMinimumTarget(result.minimum_shortlist_target);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Contractors could not be loaded.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [project.id, slug]);

  async function toggleTrade(scopeId: number) {
    if (expanded === scopeId) {
      setExpanded(null);
      return;
    }
    setExpanded(scopeId);
    if (candidates[scopeId]) return;
    setCandidateLoading(scopeId);
    setCandidateErrors((current) => ({ ...current, [scopeId]: "" }));
    try {
      const rows = await contractorsApi.candidates(slug, project.id, undefined, scopeId);
      setCandidates((current) => ({ ...current, [scopeId]: rows }));
    } catch (reason) {
      setCandidateErrors((current) => ({ ...current, [scopeId]: reason instanceof Error ? reason.message : "Contractors for this trade could not be loaded." }));
    } finally {
      setCandidateLoading(null);
    }
  }

  useEffect(() => {
    if (profile) profileRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [profile]);

  async function search(scope: ReadyTrade, keywords: string) {
    setBusy(scope.scope_package);
    setError(null);
    setSearchMessages((current) => ({ ...current, [scope.scope_package]: "Searching…" }));
    try {
      const result = await contractorsApi.search(slug, project.id, {
        scope_package_id: scope.scope_package,
        keywords: keywords.split(",").map((item) => item.trim()).filter(Boolean),
      });
      setCandidates((current) => ({ ...current, [scope.scope_package]: result.candidates }));
      setSearchMessages((current) => ({ ...current, [scope.scope_package]: contractorSearchResultMessage(result.result_count, result.partial_results) }));
      const refreshed = await contractorsApi.coverage(slug, project.id);
      setCoverage(refreshed.trades);
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Contractor search could not be completed.";
      setSearchMessages((current) => ({ ...current, [scope.scope_package]: message }));
      setError(message);
    } finally {
      setBusy(null);
    }
  }

  async function setShortlist(candidate: ContractorCandidate, shortlisted: boolean) {
    setBusy(candidate.scope_package);
    setError(null);
    try {
      const updated = await contractorsApi.setStatus(slug, project.id, candidate.id, shortlisted ? "shortlisted" : "candidate");
      setCandidates((current) => ({ ...current, [candidate.scope_package]: replaceCandidate(current[candidate.scope_package] ?? [], updated) }));
      const refreshed = await contractorsApi.coverage(slug, project.id);
      setCoverage(refreshed.trades);
      if (profile?.id === candidate.company.id) setProfile(await contractorsApi.profile(slug, project.id, profile.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : shortlisted ? "The contractor could not be added to the shortlist." : "The contractor could not be removed from the shortlist.");
    } finally {
      setBusy(null);
    }
  }

  async function openProfile(candidate: ContractorCandidate) {
    setProfileBusy(true);
    setError(null);
    try {
      setProfile(await contractorsApi.profile(slug, project.id, candidate.company.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The contractor profile could not be loaded.");
    } finally {
      setProfileBusy(false);
    }
  }

  async function saveContact(contactId: number | null, input: ContractorContactInput) {
    if (!profile) return;
    setProfileBusy(true);
    setError(null);
    try {
      if (contactId === null) await contractorsApi.addContact(slug, project.id, profile.id, input);
      else await contractorsApi.updateContact(slug, project.id, profile.id, contactId, input);
      setProfile(await contractorsApi.profile(slug, project.id, profile.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The contact could not be saved.");
      throw reason;
    } finally {
      setProfileBusy(false);
    }
  }

  async function findContactDetails(): Promise<ContractorContactEnrichment> {
    if (!profile) return { suggestions: [], pages_checked: [] };
    setProfileBusy(true);
    setError(null);
    try {
      return await contractorsApi.enrichContacts(slug, project.id, profile.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Public contact details could not be checked.");
      throw reason;
    } finally {
      setProfileBusy(false);
    }
  }

  const ready: ReadyTrade[] = coverage;
  return <div className="space-y-5">
    <div><span className="inline-flex items-center gap-1 rounded-full border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-indigo-700"><Building2 className="h-3 w-3" />Contractor Discovery</span><h2 className="mt-3 text-xl font-semibold text-slate-950">Find contractors for Ready scopes</h2><p className="mt-1 text-sm text-slate-500">Your internal network is searched first. External discovery runs only when you explicitly search and never sends outreach.</p><p className="mt-2 flex items-center gap-1 text-sm font-semibold text-blue-800"><MapPin className="h-4 w-4" />Search area: within 200 miles of the project</p><p className="mt-2 text-xs font-medium text-slate-500">Best Match is a deterministic fit ranking—not AI scoring or an approval decision.</p></div>
    {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
    {loading ? <ContractorSummarySkeleton /> : ready.length === 0 ? <Empty title="No Ready scope packages" detail="Mark a scope Ready before searching for contractors." /> : <>
      <TradeCoverageSummary coverage={coverage} minimumTarget={minimumTarget} shortlistedOnly={shortlistedOnly} onShortlistedOnlyChange={setShortlistedOnly} />
      {profile && <div ref={profileRef}><ContractorProfilePanel key={profile.id} profile={profile} canManage={canManage} busy={profileBusy} onBack={() => setProfile(null)} onSave={saveContact} onFindContactDetails={findContactDetails} /></div>}
      {ready.map((scope) => <ScopeDiscovery key={scope.scope_package} scope={scope} rows={filterContractors(candidates[scope.scope_package] ?? [], shortlistedOnly)} shortlistedOnly={shortlistedOnly} city={project.city} province={project.province_state} minimumTarget={minimumTarget} canManage={canManage} busy={busy === scope.scope_package || profileBusy} expanded={expanded === scope.scope_package} loading={candidateLoading === scope.scope_package} error={candidateErrors[scope.scope_package]} searchMessage={searchMessages[scope.scope_package]} onToggle={() => void toggleTrade(scope.scope_package)} onSearch={search} onSetShortlist={setShortlist} onViewProfile={openProfile} />)}
    </>}
  </div>;
}

function TradeCoverageSummary({ coverage, minimumTarget, shortlistedOnly, onShortlistedOnlyChange }: { coverage: TradeCoverage[]; minimumTarget: number; shortlistedOnly: boolean; onShortlistedOnlyChange: (value: boolean) => void }) {
  const readyCount = coverage.filter((item) => item.coverage_status === "ready").length;
  return <Card className="overflow-hidden border-slate-200 shadow-sm"><div className="flex flex-col gap-3 border-b bg-slate-50/80 p-5 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-xs font-bold uppercase tracking-wide text-indigo-700">Trade Coverage</p><h3 className="mt-1 text-lg font-semibold text-slate-950">Shortlist readiness</h3><p className="mt-1 text-sm text-slate-500">{readyCount} of {coverage.length} trades meet the target of {minimumTarget} shortlisted contractors.</p></div><label className="inline-flex cursor-pointer items-center gap-2 text-sm font-semibold text-slate-700"><input type="checkbox" checked={shortlistedOnly} onChange={(event) => onShortlistedOnlyChange(event.target.checked)} className="h-4 w-4 rounded border-slate-300 text-blue-700" />Show shortlisted only</label></div><div className="grid gap-px bg-slate-200 sm:grid-cols-2 xl:grid-cols-4">{coverage.map((item) => {
    const isReady = item.coverage_status === "ready";
    return <div key={item.scope_package} className="bg-white p-4"><div className="flex items-start justify-between gap-3"><p className="font-semibold text-slate-900">{item.trade_category}</p><span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-[10px] font-bold uppercase ${isReady ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>{isReady ? <CheckCircle2 className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />}{isReady ? "Ready" : "Needs more candidates"}</span></div><div className="mt-4 grid grid-cols-2 gap-3 text-sm"><div><p className="text-xs text-slate-500">Active candidates</p><p className="mt-1 flex items-center gap-1 font-semibold text-slate-900"><Users className="h-4 w-4 text-blue-600" />{item.candidates_found}</p></div><div><p className="text-xs text-slate-500">Shortlisted</p><p className="mt-1 font-semibold text-slate-900">{item.shortlisted_count} / {minimumTarget}</p></div></div></div>;
  })}</div></Card>;
}

function ScopeDiscovery({ scope, rows, shortlistedOnly, city, province, minimumTarget, canManage, busy, expanded, loading, error, searchMessage, onToggle, onSearch, onSetShortlist, onViewProfile }: { scope: ReadyTrade; rows: ContractorCandidate[]; shortlistedOnly: boolean; city: string; province: string; minimumTarget: number; canManage: boolean; busy: boolean; expanded: boolean; loading: boolean; error?: string; searchMessage?: string; onToggle: () => void; onSearch: (scope: ReadyTrade, keywords: string) => void; onSetShortlist: (candidate: ContractorCandidate, shortlisted: boolean) => void; onViewProfile: (candidate: ContractorCandidate) => void }) {
  const [keywords, setKeywords] = useState("");
  const [sort, setSort] = useState<ContractorSort>("best_match");
  const rankedRows = sortContractors(rows, sort);
  return <Card className="overflow-hidden border-slate-200 shadow-sm"><button type="button" onClick={onToggle} aria-expanded={expanded} aria-controls={`contractor-trade-${scope.scope_package}`} className="flex w-full items-center justify-between gap-4 bg-white p-5 text-left hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"><div><div className="flex flex-wrap items-center gap-2"><p className="font-semibold text-slate-950">{scope.trade_category}</p><span className="rounded-full bg-emerald-50 px-2 py-1 text-[10px] font-bold uppercase text-emerald-700">Ready V{scope.scope_version}</span></div><p className="mt-1 text-sm text-slate-500">{scope.candidates_found} active candidates · {scope.shortlisted_count} / {minimumTarget} shortlisted</p></div><ChevronDown className={`h-5 w-5 shrink-0 text-slate-500 transition-transform ${expanded ? "rotate-180" : ""}`} /></button>{expanded && <div id={`contractor-trade-${scope.scope_package}`} className="border-t"><div className="border-b bg-white p-5"><p className="flex items-center gap-1 text-sm text-slate-500"><MapPin className="h-4 w-4" />{city}, {province}</p><p className="mt-1 text-xs font-semibold text-blue-800">Search area: within 200 miles of the project</p>{canManage && <div className="mt-4 flex flex-col gap-2 sm:flex-row"><input aria-label={`Keywords for ${scope.trade_category}`} value={keywords} onChange={(event) => setKeywords(event.target.value)} placeholder="Optional keywords, comma separated" className="h-10 flex-1 rounded-lg border px-3 text-sm"/><button type="button" disabled={busy} onClick={() => onSearch(scope, keywords)} className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-[#173f5f] px-4 text-sm font-semibold text-white disabled:opacity-50"><Search className="h-4 w-4" />{busy ? "Searching…" : "Search Contractors"}</button></div>}{searchMessage && <p aria-live="polite" className="mt-2 text-sm font-medium text-slate-600">{searchMessage}</p>}{rows.length > 0 && <SortControl scopeId={scope.scope_package} sort={sort} onChange={setSort} />}</div>{loading ? <p className="p-5 text-sm text-slate-500">Loading contractor candidates…</p> : error ? <div role="alert" className="m-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div> : <div className="divide-y">{rankedRows.length === 0 ? <p className="p-5 text-sm text-slate-500">{shortlistedOnly ? "No shortlisted contractors for this trade yet." : "No candidates yet. Search your internal network and configured discovery provider."}</p> : rankedRows.map((candidate, index) => <CandidateRow key={candidate.id} candidate={candidate} rank={index + 1} canManage={canManage} busy={busy} onSetShortlist={onSetShortlist} onViewProfile={onViewProfile} />)}</div>}</div>}</Card>;
}

function ContractorSummarySkeleton() { return <div className="space-y-4" aria-label="Loading Ready contractor trades"><div className="h-40 animate-pulse rounded-xl border bg-slate-100" />{Array.from({ length: 3 }, (_, index) => <div key={index} className="h-20 animate-pulse rounded-xl border bg-slate-100" />)}</div>; }

function SortControl({ scopeId, sort, onChange }: { scopeId: number; sort: ContractorSort; onChange: (sort: ContractorSort) => void }) { return <div className="mt-4 flex items-center justify-end gap-2"><label htmlFor={`contractor-sort-${scopeId}`} className="text-xs font-semibold text-slate-500">Sort by</label><select id={`contractor-sort-${scopeId}`} value={sort} onChange={(event) => onChange(event.target.value as ContractorSort)} className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700"><option value="best_match">Best Match</option><option value="internal_first">Internal First</option><option value="rating">Rating</option><option value="review_count">Review Count</option><option value="company_name">Company Name</option></select></div>; }

function CandidateRow({ candidate, rank, canManage, busy, onSetShortlist, onViewProfile }: { candidate: ContractorCandidate; rank: number; canManage: boolean; busy: boolean; onSetShortlist: (candidate: ContractorCandidate, shortlisted: boolean) => void; onViewProfile: (candidate: ContractorCandidate) => void }) { return <div className={`flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between ${candidate.status === "shortlisted" ? "bg-emerald-50/60" : ""}`}><div><div className="flex flex-wrap items-center gap-2"><span className="inline-flex h-6 min-w-6 items-center justify-center rounded-full bg-slate-900 px-1.5 text-xs font-bold text-white">{rank}</span><p className="font-semibold text-slate-900">{candidate.company.display_name}</p><span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${candidate.company.source_type === "internal" ? "bg-blue-50 text-blue-700" : "bg-indigo-50 text-indigo-700"}`}>{contractorSourceLabel(candidate)}</span><span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-bold text-amber-700">Best Match · {candidate.match_score}/100</span><span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-700">{contractorFitBand(candidate.match_score)}</span></div><p className="mt-1 text-sm text-slate-500">{candidate.company.address || `${candidate.company.city}, ${candidate.company.province}`}{candidate.company.phone ? ` · ${candidate.company.phone}` : ""}</p>{candidate.distance_miles !== null && <p className="mt-1 text-sm font-medium text-blue-700">{Math.round(candidate.distance_miles)} miles from project</p>}{candidate.google_rating !== null && <p className="mt-1 text-sm text-slate-600">Google {candidate.google_rating.toFixed(1)}{candidate.google_review_count !== null ? ` · ${candidate.google_review_count} reviews` : ""}</p>}<details className="mt-2"><summary className="cursor-pointer text-xs font-semibold text-blue-700">Why this ranks here</summary><ul className="mt-2 grid gap-1 text-xs text-slate-600 sm:grid-cols-2">{contractorRankingSignals(candidate).map((reason) => <li key={reason}>• {reason}</li>)}</ul></details>{candidate.company.website && <a href={candidate.company.website} target="_blank" rel="noreferrer" className="mt-2 inline-block text-sm font-medium text-blue-700 hover:underline">Visit website</a>}</div><div className="flex flex-wrap gap-2"><button type="button" onClick={() => onViewProfile(candidate)} disabled={busy} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 disabled:opacity-50">View profile</button>{candidate.status === "candidate" && canManage ? <button type="button" onClick={() => onSetShortlist(candidate, true)} disabled={busy} className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm font-semibold text-blue-700 disabled:opacity-50">Add to Shortlist</button> : candidate.status === "shortlisted" && canManage ? <button type="button" onClick={() => onSetShortlist(candidate, false)} disabled={busy} className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm font-semibold text-emerald-700 disabled:opacity-50">Shortlisted ✓ · Remove</button> : candidate.status === "shortlisted" ? <span className="inline-flex rounded-lg bg-emerald-50 px-3 py-2 text-sm font-semibold text-emerald-700">Shortlisted ✓</span> : candidate.status !== "candidate" ? <span className="inline-flex rounded-lg bg-slate-100 px-3 py-2 text-sm font-semibold text-slate-600">{candidate.status.replaceAll("_", " ")}</span> : null}</div></div>; }

function Empty({ title, detail }: { title: string; detail: string }) { return <section className="flex min-h-56 flex-col items-center justify-center rounded-xl border border-dashed bg-white px-6 text-center"><Building2 className="h-8 w-8 text-slate-400"/><h3 className="mt-3 font-semibold text-slate-900">{title}</h3><p className="mt-1 text-sm text-slate-500">{detail}</p></section>; }
