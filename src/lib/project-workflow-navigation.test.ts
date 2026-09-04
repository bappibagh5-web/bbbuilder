import assert from "node:assert/strict";
import test from "node:test";
import { projectWorkflowHref, projectWorkflowNavigation } from "./project-workflow-navigation.ts";

test("project workflow keeps every established horizontal stage", () => {
  const labels: string[] = projectWorkflowNavigation.map((tab) => tab.label);
  assert.deepEqual(labels, [
    "Overview", "Documents", "Document Review", "Scopes", "Contractors",
    "Outreach", "Bids", "Comparisons", "Proposal", "Activity",
  ]);
  assert.equal(labels.includes("AI Review"), false);
  assert.equal(labels.includes("Settings"), false);
});

test("numeric and fixture project routes remain isolated by project identity", () => {
  const review = projectWorkflowNavigation.find((tab) => tab.label === "Document Review");
  assert.ok(review);
  assert.equal(projectWorkflowHref("2", review.slug), "/projects/2/ai-review");
  assert.equal(projectWorkflowHref("retail-store-coquitlam", review.slug), "/projects/retail-store-coquitlam/ai-review");
  assert.equal(projectWorkflowHref("2", "scopes"), "/projects/2/scopes");
  assert.equal(projectWorkflowHref("2", "activity"), "/projects/2/activity");
});
