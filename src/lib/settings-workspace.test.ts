import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const workspace = readFileSync(
  new URL("../components/settings/production-settings-workspace.tsx", import.meta.url),
  "utf8",
);
const page = readFileSync(new URL("../app/(app)/settings/page.tsx", import.meta.url), "utf8");
const api = readFileSync(new URL("./settings.ts", import.meta.url), "utf8");
const resend = readFileSync(
  new URL("../components/settings/resend-integration-panel.tsx", import.meta.url),
  "utf8",
);

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

test("Admins can create a new account or add access to an existing account", () => {
  assert.match(workspace, /Create new user/);
  assert.match(workspace, /Temporary password/);
  assert.match(workspace, /Confirm temporary password/);
  assert.match(workspace, /settingsApi\.createUser/);
  assert.match(workspace, /settingsApi\.memberships\(slug\)/);
  assert.match(workspace, /New user created with organization access/);
  assert.match(api, /createUser/);
  assert.match(workspace, /Add existing user/);
  assert.match(workspace, /Email invitations are not implemented/);
  assert.match(api, /addMembership/);
  assert.match(api, /updateMembership/);
});

test("production email and webhook settings remain available", () => {
  assert.match(workspace, /<SettingsPanel section="email" \/>/);
  assert.match(workspace, /<ResendIntegrationPanel \/>/);
  assert.match(resend, /Resend Email &amp; Tracking/);
  assert.match(resend, /Leave blank to keep saved API key/);
  assert.match(resend, /Saved securely/);
  assert.match(resend, /Paste this URL into Resend → Webhooks/);
  assert.match(resend, /Required Resend events/);
  assert.match(resend, /Tracking requirements/);
  assert.match(resend, /Test SMTP Connection/);
  assert.match(resend, /Controlled test email/);
  assert.doesNotMatch(workspace, /Future integrations/);
  assert.doesNotMatch(resend, /encrypted_password|encrypted_signing_secret/);
});
