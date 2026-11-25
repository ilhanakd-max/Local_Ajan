import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { ReadFileTool, WriteFileTool, EditFileTool } from "../src/tools/fsTools.js";
import { RunShellTool } from "../src/tools/shellTool.js";
import { ReportFindingTool, loadClaimMemory } from "../src/tools/claimTools.js";
import { SemanticCodeSearchTool } from "../src/tools/semanticSearchTool.js";
import { RepetitionLoopGuard, detectTextRepetition } from "../src/safety/guards.js";

test("WriteFileTool blocks overwrite and protected dirs; EditFileTool works", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "locai-fs-"));
  try {
    const wf = new WriteFileTool(tmp);
    const ef = new EditFileTool(tmp);
    const rf = new ReadFileTool(tmp);

    assert.match(wf.run({ path: "app.js", content: "const x = 1;\n" }), /Successfully wrote/);
    assert.match(wf.run({ path: "app.js", content: "const x = 2;\n" }), /already exists.*edit_file/);
    assert.match(wf.run({ path: ".git/config", content: "bad" }), /protected directory/);
    assert.match(ef.run({ path: "app.js", old_str: "const x = 1;", new_str: "const x = 42;" }), /Successfully edited/);
    assert.match(rf.run({ path: "app.js" }), /const x = 42;/);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test("ReadFileTool redirects directory to listing and RunShell rm+write bypass is blocked", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "locai-bypass-"));
  try {
    fs.writeFileSync(path.join(tmp, "target.js"), "console.log(1);\n");
    const rf = new ReadFileTool(tmp);
    const dirOut = rf.run({ path: "." });
    assert.match(dirOut, /is a directory/);
    assert.match(dirOut, /target\.js/);

    const sh = new RunShellTool(tmp);
    sh.run({ command: "rm target.js" });
    const wf = new WriteFileTool(tmp);
    assert.match(wf.run({ path: "target.js", content: "new" }), /removed\/moved via run_shell/);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test("RepetitionLoopGuard catches identical and periodic loops, resets on mutation", () => {
  const guard = new RepetitionLoopGuard({ threshold: 3, stopAfter: 2 });
  assert.equal(guard.recordAndCheck("read_file", { path: "a.js" }).blocked, false);
  assert.equal(guard.recordAndCheck("read_file", { path: "a.js" }).blocked, false);
  const r3 = guard.recordAndCheck("read_file", { path: "a.js" });
  assert.equal(r3.blocked, true);
  assert.equal(r3.shouldAbort, false);

  assert.equal(guard.recordAndCheck("edit_file", { path: "a.js", old_str: "1", new_str: "2" }).blocked, false);

  assert.equal(guard.recordAndCheck("list_dir", { path: "." }).blocked, false);
  assert.equal(guard.recordAndCheck("git_status", {}).blocked, false);
  assert.equal(guard.recordAndCheck("list_dir", { path: "." }).blocked, false);
  assert.equal(guard.recordAndCheck("git_status", {}).blocked, true);
});

test("detectTextRepetition flags repeated lines", () => {
  const repeated = Array(5).fill("This exact line keeps repeating over and over again.").join("\n");
  assert.equal(detectTextRepetition(repeated), true);
  assert.equal(detectTextRepetition("Line one\nLine two\nLine three"), false);
});

test("ReportFindingTool validates quotes and persists refuted claims", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "locai-claim-"));
  const prevEnv = process.env.LOCAI_CLAIM_MEMORY;
  process.env.LOCAI_CLAIM_MEMORY = path.join(tmp, "claim_memory.json");
  try {
    fs.writeFileSync(path.join(tmp, "auth.js"), "function check(u) {\n  if (!u) return false;\n  return true;\n}\n");
    const tool = new ReportFindingTool(tmp);

    assert.match(
      tool.run({
        title: "Missing null check",
        file_path: "auth.js",
        line_start: 1,
        quoted_source: "DOES NOT EXIST",
        failure_scenario: "Passing null crashes check(null) immediately.",
        refutation_attempt: "Checked auth.js lines 1-4 for null guard.",
        confidence: "confirmed",
      }),
      /not found verbatim/
    );

    const disproved = tool.run({
      title: "Missing null check",
      file_path: "auth.js",
      line_start: 2,
      quoted_source: "if (!u) return false;",
      failure_scenario: "Passing null crashes check(null) immediately.",
      refutation_attempt: "Checked line 2 of auth.js for falsy check.",
      refuted_by: "Line 2 already returns false when u is falsy.",
      confidence: "likely",
    });
    assert.match(disproved, /DISPROVED/);
    assert.equal(loadClaimMemory().length, 1);
  } finally {
    if (prevEnv === undefined) delete process.env.LOCAI_CLAIM_MEMORY;
    else process.env.LOCAI_CLAIM_MEMORY = prevEnv;
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test("SemanticCodeSearchTool finds matching behavior via BM25 fallback", async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "locai-sem-"));
  try {
    fs.writeFileSync(
      path.join(tmp, "billing.js"),
      "export function calculateInvoiceTotal(items) {\n  return items.reduce((s, x) => s + x.price, 0);\n}\n"
    );
    fs.writeFileSync(
      path.join(tmp, "math.js"),
      "export function add(a, b) { return a + b; }\n"
    );
    const tool = new SemanticCodeSearchTool(tmp);
    const res = await tool.run({ query: "calculate invoice total price" });
    assert.match(res, /billing\.js/);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});
