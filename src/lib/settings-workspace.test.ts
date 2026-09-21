import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const workspace = readFileSync(
  new URL("../components/settings/production-settings-workspace.tsx", import.meta.url),
  "utf8",
);
const page = readFileSync(new URL("../app/(app)/settings/page.tsx", import.meta.url), "utf8");
const api = readFileSync(new URL("./settings.ts", import.meta.url), "utf8");

test("settings uses four production sections", () => {
  assert.match(page, /ProductionSettingsWorkspace/);
  assert.match(workspace, /label: "Organization"/);
  assert.match(workspace, /label: "Users & Access"/);
  assert.match(workspace, /label: "Email & Outreach"/);
  assert.match(workspace, /label: "Integrations"/);
});

test("member management uses backend-authoritative access flags", () => {
  assert.match(api, /can_manage_members/);
  assert.match(workspace, /data\?\.can_manage_members/);
  assert.match(workspace, /member\.can_change_role/);
  assert.match(workspace, /member\.can_deactivate/);
  assert.match(workspace, /member\.can_reactivate/);
  assert.match(workspace, /window\.confirm/);
});

test("access can be added only to an existing account", () => {
  assert.match(workspace, /Add existing user/);
  assert.match(workspace, /Email invitations are not implemented/);
  assert.match(api, /addMembership/);
  assert.match(api, /updateMembership/);
});

test("production email and webhook settings remain available", () => {
  assert.match(workspace, /<SettingsPanel section="email" \/>/);
  assert.match(workspace, /<SettingsPanel section="integrations" \/>/);
});
