import assert from "node:assert/strict";
import test from "node:test";
import { pendingQuoteAttachments } from "./outreach-attachment-state.ts";

test("older recipient payloads without M3-06 fields do not crash", () => {
  assert.deepEqual(pendingQuoteAttachments({}), []);
  assert.deepEqual(pendingQuoteAttachments({ inbound_attachment_responses: null }), []);
});

test("correlated attachment notices remain actionable unless already imported", () => {
  const notices = [{ id: 11, attachment_count: 2 }, { id: 12, attachment_count: 1 }];
  assert.deepEqual(pendingQuoteAttachments({ inbound_attachment_responses: notices }), notices);
  assert.deepEqual(
    pendingQuoteAttachments({ inbound_attachment_responses: notices, imported_response_ids: [11] }),
    [notices[1]],
  );
});
