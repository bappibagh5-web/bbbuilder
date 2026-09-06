import type { ScopePackage } from "./scope-packages.ts";

export function scopePackageCounts(packages: Pick<ScopePackage, "current_version">[]) {
  const ready = packages.filter((item) => item.current_version.status === "ready").length;
  return { total: packages.length, ready, draft: packages.length - ready };
}

export function linesToItems(value: string) {
  return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
}

export function itemsToLines(value: string[]) {
  return value.join("\n");
}

export function replaceScopePackage(packages: ScopePackage[], updated: ScopePackage) {
  return packages.map((item) => (item.id === updated.id ? updated : item));
}
