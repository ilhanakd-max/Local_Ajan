import test from "node:test";
import assert from "node:assert/strict";

import {
  shouldCollapsePaste,
  formatPasteToken,
  expandPastes,
} from "../src/ui/promptInput.js";

test("shouldCollapsePaste collapses multi-line or long text but keeps short single-line inline", () => {
  assert.equal(shouldCollapsePaste("merhaba dünya"), false);
  assert.equal(shouldCollapsePaste("satır 1\nsatır 2"), true);
  assert.equal(shouldCollapsePaste("satır 1\r\nsatır 2"), true);
  assert.equal(shouldCollapsePaste("a".repeat(101)), true);
});

test("formatPasteToken formats line and char counts like OpenCode pills", () => {
  assert.equal(formatPasteToken(1, "a\nb\nc"), "[Pasted #1 ~3 lines]");
  assert.equal(formatPasteToken(2, "x".repeat(150)), "[Pasted #2 ~150 chars]");
});

test("expandPastes restores all paste pills back to full pasted content", () => {
  const pastes = new Map([
    ["[Pasted #1 ~2 lines]", "const a = 1;\nconst b = 2;"],
    ["[Pasted #2 ~3 lines]", "line1\nline2\nline3"],
  ]);
  const buf = "Şunu incele: [Pasted #1 ~2 lines] ve [Pasted #2 ~3 lines]";
  assert.equal(
    expandPastes(buf, pastes),
    "Şunu incele: const a = 1;\nconst b = 2; ve line1\nline2\nline3"
  );
});
