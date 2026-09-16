import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { displayBidCandidateValue, displayBidMoney } from "./bid-money.ts";

const inbox = readFileSync(new URL("../components/bids/production-bids-module.tsx", import.meta.url), "utf8");
const editor = readFileSync(new URL("../components/bids/structured-bid-editor.tsx", import.meta.url), "utf8");
const api = readFileSync(new URL("./bid-revisions.ts", import.meta.url), "utf8");

test("original quote inbox remains visible and structuring is an explicit action", () => {
  assert.match(inbox, /Download privately/);
  assert.match(inbox, /Structure Bid \/ View History/);
  assert.match(inbox, /View structured bid/);
  assert.match(editor, /Original source quote/);
  assert.match(editor, /Download original/);
  assert.match(editor, /Create Draft Revision/);
});

test("structured editor keeps commercial sections separate and avoids single-price simplification", () => {
  for (const section of ["Commercial Summary", "Alternates / Options", "Allowances",
    "Permits / Fees / Taxes", "Exclusions", "Qualifications / Conditions",
    "Scope Coverage / Differences", "Notes / Evidence"]) {
    assert.match(editor, new RegExp(section.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
  assert.match(editor, /Not addressed does not mean excluded/);
  assert.match(editor, /displayBidMoney/);
  assert.match(editor, /commercialReviewed/);
  assert.match(editor, /scopeReviewed/);
});

test("commercial display groups Decimal strings without JavaScript arithmetic", () => {
  assert.equal(displayBidMoney("185000.00", "CAD"), "CAD $185,000.00");
  assert.equal(displayBidMoney(null, "CAD"), "Amount not stated");
  assert.equal(displayBidMoney("6500.00", ""), "Currency not stated · 6,500.00");
  assert.equal(displayBidMoney("NaN", "CAD"), "Amount needs review");
});

test("AI suggestion presentation respects money, duration, condition, fee, and tax semantics", () => {
  const candidate = (values: Partial<Parameters<typeof displayBidCandidateValue>[0]>) => ({
    kind: "condition", title: "", description: "", amount: null, currency: null,
    treatment: null, excerpt: "", ...values,
  });
  assert.equal(displayBidCandidateValue(candidate({ kind: "validity", title: "Bid Validity", amount: "30.00", excerpt: "Bid Validity: 30 days" })), "30 days");
  assert.equal(displayBidCandidateValue(candidate({ kind: "schedule", title: "Schedule", amount: "4.00", excerpt: "Schedule: 4 weeks from mobilization" })), "4 weeks from mobilization");
  assert.equal(displayBidCandidateValue(candidate({ title: "Equipment lead time", amount: "10.00", excerpt: "Qualification:\nEquipment lead time is 10 weeks." })), "Equipment lead time is 10 weeks.");
  assert.equal(displayBidCandidateValue(candidate({ kind: "fee", title: "Mechanical permit", treatment: "included", excerpt: "Permit:\nMechanical permit included." })), "Included");
  assert.equal(displayBidCandidateValue(candidate({ kind: "tax", title: "HST", treatment: "extra", excerpt: "HST: Extra" })), "Extra");
  assert.equal(displayBidCandidateValue(candidate({ kind: "alternate", title: "Controls Upgrade", amount: "6500.00", currency: "CAD", treatment: "add" })), "CAD $6,500.00 · Add");
});

test("AI extraction is explicit, suggestion-only, and never triggers on page load", () => {
  assert.match(editor, /Extract Bid Details/);
  assert.match(editor, /Human confirm/);
  assert.match(editor, /Correct & confirm/);
  assert.match(editor, /Ignore/);
  assert.match(editor, /No quote is processed on upload or page load/);
  assert.doesNotMatch(inbox, /\.extract\(/);
});

test("Viewer stays read-only and Ready requires a separate human action", () => {
  assert.match(editor, /canEdit &&/);
  assert.match(editor, /Mark Ready for Comparison/);
  assert.match(editor, /selected\.readiness_blockers\.length > 0/);
  assert.match(api, /method: "POST"/);
  assert.match(api, /bidReadinessCopy/);
});
