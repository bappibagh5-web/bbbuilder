import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const shell = readFileSync(new URL("../components/app-shell.tsx", import.meta.url), "utf8");
const metadata = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");

const expectedLinks = [
  "/dashboard",
  "/projects",
  "/subcontractors",
  "/campaigns",
  "/comparisons",
  "/proposals",
  "/awarded",
  "/activity",
  "/settings",
];

test("production sidebar contains only supported production destinations", () => {
  for (const href of expectedLinks) {
    assert.match(shell, new RegExp(`href: "${href}"`));
  }
  assert.doesNotMatch(shell, /Bid Opportunities/);
  assert.doesNotMatch(shell, /href: "\/bid-opportunities"/);
});

test("navigation preserves exact active-state and accessible link behavior", () => {
  assert.match(shell, /path === item\.href/);
  assert.match(shell, /path\.startsWith\(`\$\{item\.href\}\/`\)/);
  assert.match(shell, /aria-current=\{active \? "page" : undefined\}/);
  assert.match(shell, /aria-label="Primary navigation"/);
});

test("global metadata and shell contain no demo positioning or fake header actions", () => {
  assert.doesNotMatch(metadata, /Demo|demonstration/i);
  assert.doesNotMatch(shell, /Open search|View notifications|Bid Opportunities/);
  assert.match(shell, /Production Workspace/);
});
