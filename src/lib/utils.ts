import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
export function formatCurrency(value: number, currency = "CAD") {
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}
export function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-CA", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(value));
}
export function formatPercentage(value: number) {
  return new Intl.NumberFormat("en-CA", {
    style: "percent",
    maximumFractionDigits: 0,
  }).format(value / 100);
}
export function formatRelativeTime(
  value: string,
  now = new Date("2026-08-23T12:00:00Z"),
) {
  const minutes = Math.max(
    1,
    Math.round((now.getTime() - new Date(value).getTime()) / 60000),
  );
  if (minutes < 60) return `${minutes} minutes ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} ${hours === 1 ? "hour" : "hours"} ago`;
  if (hours < 48) return "Yesterday";
  return `${Math.round(hours / 24)} days ago`;
}
export function daysRemaining(dateOnly: string, reference = "2026-08-23") {
  const target = Date.parse(`${dateOnly}T00:00:00Z`);
  const start = Date.parse(`${reference}T00:00:00Z`);
  return Math.max(0, Math.round((target - start) / 86400000) + 1);
}
export function calculateProposalPricing(
  tradeCosts: number[],
  settings: {
    generalConditions: number;
    permitAllowance: number;
    projectManagement: number;
    contingencyPercent: number;
    overheadProfitPercent: number;
    taxPercent: number;
  },
  includedAlternates: number[] = [],
) {
  const tradeSubtotal = tradeCosts.reduce((sum, value) => sum + value, 0);
  const directSubtotal =
    tradeSubtotal +
    settings.generalConditions +
    settings.permitAllowance +
    settings.projectManagement;
  const contingency = Math.round(
    (directSubtotal * Math.max(0, settings.contingencyPercent)) / 100,
  );
  const overheadProfit = Math.round(
    ((directSubtotal + contingency) *
      Math.max(0, settings.overheadProfitPercent)) /
      100,
  );
  const alternateImpact = includedAlternates.reduce(
    (sum, value) => sum + value,
    0,
  );
  const subtotal =
    directSubtotal + contingency + overheadProfit + alternateImpact;
  const tax = Math.round((subtotal * Math.max(0, settings.taxPercent)) / 100);
  return {
    tradeSubtotal,
    directSubtotal,
    contingency,
    overheadProfit,
    alternateImpact,
    subtotal,
    tax,
    total: subtotal + tax,
  };
}
