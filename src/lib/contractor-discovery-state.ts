import type { ContractorCandidate } from "./contractors.ts";
import type { ScopePackage } from "./scope-packages.ts";
export function readyScopePackages(packages: ScopePackage[]) { return packages.filter((item) => item.current_version.status === "ready"); }
export function candidatesForScope(candidates: ContractorCandidate[], scopeId: number) { return candidates.filter((item) => item.scope_package === scopeId); }
export function replaceCandidate(candidates: ContractorCandidate[], updated: ContractorCandidate) { return candidates.map((item) => item.id === updated.id ? updated : item); }
export function canManageContractors(role: string) { return role === "admin" || role === "estimator_operator"; }
export function contractorSourceLabel(candidate: ContractorCandidate) { if (candidate.company.source_type === "internal") return "Internal"; return candidate.company.external_provider === "google_places" ? "External / Google" : "External"; }
export function contractorSearchResultMessage(count: number) { if (count === 0) return "No candidates found"; return `${count} ${count === 1 ? "candidate" : "candidates"} found`; }
