import type { ContractorCandidate } from "./contractors.ts";
import type { ScopePackage } from "./scope-packages.ts";
export function readyScopePackages(packages: ScopePackage[]) { return packages.filter((item) => item.current_version.status === "ready"); }
export function candidatesForScope(candidates: ContractorCandidate[], scopeId: number) { return candidates.filter((item) => item.scope_package === scopeId); }
export function replaceCandidate(candidates: ContractorCandidate[], updated: ContractorCandidate) { return candidates.map((item) => item.id === updated.id ? updated : item); }
export function canManageContractors(role: string) { return role === "admin" || role === "estimator_operator"; }
