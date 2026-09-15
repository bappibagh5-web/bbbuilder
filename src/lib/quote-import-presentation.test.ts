import assert from "node:assert/strict";
import test from "node:test";
import { quoteImportFailure } from "./quote-import-presentation.ts";

test("provider and storage import failures have safe visible copy", () => {
  assert.match(quoteImportFailure(new Error("Provider attachment location is not trusted.")), /email provider/);
  assert.match(quoteImportFailure(new Error("Attachment storage failed.")), /storage failed/);
  assert.match(quoteImportFailure(new Error("This quote attachment type is not supported.")), /not supported/);
});

test("unknown failures do not expose raw provider or internal details", () => {
  assert.equal(
    quoteImportFailure(new Error("internal traceback with credential")),
    "The quote could not be recorded. No file or submission was saved.",
  );
});
