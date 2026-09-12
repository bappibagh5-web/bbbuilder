const RESPONSIBILITY_LABELS: Record<string, string> = {
  unclear: "Responsibility not stated in documents",
  owner_supplied: "Owner supplied",
  landlord_supplied: "Landlord responsibility",
  by_others: "By others",
  existing_to_remain: "Existing to remain",
  relocate_reuse: "Relocate / reuse",
  install_only: "Install only",
  supply_install: "Supply & install",
};

export function responsibilityLabel(value: string) {
  return RESPONSIBILITY_LABELS[value] ?? "Responsibility confirmed";
}

export function itemTypeLabel(value: string) {
  return value
    .split("_")
    .map((word) => `${word.charAt(0).toUpperCase()}${word.slice(1)}`)
    .join(" ");
}

export function scopePackageCounts(packages: { current_version: { status: string } }[]) {
  const ready = packages.filter((item) => item.current_version.status === "ready").length;
  return { total: packages.length, ready, draft: packages.length - ready };
}

export function scopeItemCount(packages: { current_version: { scope_item_count?: number; scope_items?: unknown[] } }[]) {
  return packages.reduce((total, item) => total + (item.current_version.scope_item_count ?? item.current_version.scope_items?.length ?? 0), 0);
}

export function scopePackageGenerations<T extends { lifecycle: string }>(packages: T[]) {
  return {
    active: packages.filter((item) => item.lifecycle === "active"),
    historical: packages.filter((item) => item.lifecycle === "superseded"),
  };
}

export function linesToItems(value: string) {
  return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
}

export function itemsToLines(value: string[]) {
  return value.join("\n");
}

export function replaceScopePackage<T extends { id: number; current_version: { status: string } }>(packages: T[], updated: T) {
  return packages.map((item) => (item.id === updated.id ? updated : item));
}
