/** Display decimal strings without converting commercial amounts to JS Number. */
export function displayBidMoney(amount: string | null, currency: string): string {
  if (amount === null) return "Amount not stated";
  if (!/^(0|[1-9]\d*)(\.\d{2})$/.test(amount)) return "Amount needs review";
  const [whole, cents] = amount.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const prefix = currency === "CAD" || currency === "USD" ? "$" : "";
  return `${currency ? `${currency} ` : "Currency not stated · "}${prefix}${grouped}.${cents}`;
}

type BidCandidateDisplay = {
  kind: string;
  title: string;
  description: string;
  amount: string | null;
  currency: string | null;
  treatment: string | null;
  included_in_base_bid?: boolean | null;
  excerpt: string;
};

const treatmentLabels: Record<string, string> = {
  add: "Add",
  deduct: "Deduct",
  no_cost: "No cost",
  price_on_request: "Price on request",
  included: "Included",
  excluded: "Excluded",
  extra: "Extra",
  allowance: "Allowance",
  not_stated: "Not stated / needs confirmation",
};

function exactEvidenceValue(candidate: BidCandidateDisplay): string {
  if (candidate.description.trim()) return candidate.description.trim();
  const line = candidate.excerpt.split(/\r?\n/).map((item) => item.trim()).filter(Boolean).at(-1) ?? "";
  const prefix = `${candidate.title}:`;
  return line.toLowerCase().startsWith(prefix.toLowerCase())
    ? line.slice(prefix.length).trim()
    : line;
}

/** Present suggestion semantics without treating every numeric value as money. */
export function displayBidCandidateValue(candidate: BidCandidateDisplay): string {
  const treatment = candidate.treatment ? treatmentLabels[candidate.treatment] ?? candidate.treatment : "";
  if (["validity", "schedule", "condition"].includes(candidate.kind)) {
    return exactEvidenceValue(candidate);
  }
  if (candidate.kind === "tax") return treatment || exactEvidenceValue(candidate);
  if (["base_bid", "alternate", "allowance", "fee"].includes(candidate.kind)) {
    const money = candidate.amount === null
      ? ""
      : displayBidMoney(candidate.amount, candidate.currency ?? "");
    const baseBid = candidate.kind === "allowance" && candidate.included_in_base_bid !== null
      && candidate.included_in_base_bid !== undefined
      ? candidate.included_in_base_bid ? "Included in Base Bid" : "Excluded from Base Bid"
      : "";
    return [money, treatment, baseBid].filter(Boolean).join(" · ") || exactEvidenceValue(candidate);
  }
  return treatment || candidate.description.trim();
}
