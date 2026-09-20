import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const page = readFileSync("src/app/(app)/activity/page.tsx", "utf8");
const component = readFileSync("src/components/activity-directory.tsx", "utf8");
const api = readFileSync("src/lib/activity-directory.ts", "utf8");

test("activity route uses the production organization endpoint without demo data", () => {
  assert.doesNotMatch(page, /globalActivity|@\/data/);
  assert.match(component, /getOrganizationActivity/);
  assert.match(api, /organizations.*activity/);
  assert.doesNotMatch(component, /fictional|completed demo workflow|Demo Pacific/);
});

test("activity directory renders distinct loading error empty and no-result states", () => {
  assert.match(component, /Loading activity/);
  assert.match(component, /Activity unavailable/);
  assert.match(component, /No activity recorded yet/);
  assert.match(component, /No activity matches these filters/);
  assert.match(component, /error \?/);
});

test("activity directory supports bounded filters pagination and safe links", () => {
  assert.match(component, /All projects/);
  assert.match(component, /All activity/);
  assert.match(component, /data\.previous/);
  assert.match(component, /data\.next/);
  assert.match(component, /href=\{item\.route\}/);
  assert.match(api, /page_size/);
});

test("activity directory is read only for viewers and exposes no raw metadata", () => {
  assert.match(component, /useOrganization/);
  assert.doesNotMatch(component, /method:\s*["'](?:POST|PATCH|PUT|DELETE)/);
  assert.doesNotMatch(api, /metadata|message_body|attachment|webhook|smtp_password/);
});
