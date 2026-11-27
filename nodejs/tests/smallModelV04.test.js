import test from "node:test";
import assert from "node:assert/strict";
import os from "node:os";
import path from "node:path";
import fs from "node:fs";

import { resolveToolName, repairArgs } from "../src/agent/repair.js";
import { extractAllToolCalls } from "../src/agent/parser.js";
import { truncateToolOutput } from "../src/agent/context.js";
import { getProfileForModel } from "../src/llm/modelProfiles.js";
import { EditFileTool } from "../src/tools/fsTools.js";

const VALID = new Set(["read_file", "write_file", "edit_file", "list_dir", "glob", "grep", "run_shell"]);

test("resolveToolName handles aliases and fuzzy names", () => {
  assert.equal(resolveToolName("create_file", VALID), "write_file");
  assert.equal(resolveToolName("readfile", VALID), "read_file");
  assert.equal(resolveToolName("Read-File", VALID), "read_file");
  assert.equal(resolveToolName("bash", VALID), "run_shell");
  assert.equal(resolveToolName("launch_missiles", VALID), null);
});

test("repairArgs fixes aliases, types and single-param mapping", () => {
  const writeSchema = { parameters: { properties: { path: { type: "string" }, content: { type: "string" } }, required: ["path", "content"] } };
  assert.deepEqual(repairArgs({ file_path: "a.txt", text: "hi" }, writeSchema), { path: "a.txt", content: "hi" });
  const readSchema = { parameters: { properties: { path: { type: "string" }, start_line: { type: "integer" } }, required: ["path"] } };
  assert.equal(repairArgs({ path: "a", start_line: "3" }, readSchema).start_line, 3);
  assert.deepEqual(repairArgs({ whatever: "src" }, readSchema), { path: "src" });
});

test("parser maps alias tool name inside <tool_call>", () => {
  const text = '<tool_call>{"name": "create_file", "arguments": {"file_path": "a.txt", "text": "hi"}}</tool_call>';
  const calls = extractAllToolCalls(text);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].name, "write_file");
  assert.deepEqual(calls[0].args, { path: "a.txt", content: "hi" });
});

test("parser still rejects unknown tools", () => {
  assert.deepEqual(extractAllToolCalls('<tool_call>{"name": "launch_missiles", "arguments": {}}</tool_call>'), []);
});

test("truncateToolOutput keepTail preserves the end", () => {
  const out = "A".repeat(1000) + "TRACEBACK_END";
  const res = truncateToolOutput(out, 200, 50);
  assert.ok(res.startsWith("A".repeat(150)));
  assert.ok(res.endsWith("TRACEBACK_END"));
  assert.ok(res.includes("atlandı"));
  assert.ok(truncateToolOutput("x".repeat(5000), 100).startsWith("x".repeat(100)));
});

test("small qwen3 profiles carry sampling limits", () => {
  const p = getProfileForModel("qwen3:1.7b");
  assert.ok(p.num_predict >= 3072);
  assert.equal(p.top_k, 20);
  assert.equal(getProfileForModel("qwen3:8b").num_predict, undefined);
});

test("edit_file shows closest lines when old_str is not found", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "locai-"));
  fs.writeFileSync(path.join(dir, "style.css"), "body {\n    background-color: #f4f4f4;\n    margin: 0;\n}\n");
  const tool = new EditFileTool(dir);
  const res = tool.run({ path: "style.css", old_str: "background-colour: #f4f4f4;", new_str: "x" });
  assert.ok(res.startsWith("Error"));
  assert.ok(res.includes("Closest lines"));
  assert.ok(res.includes("line 2"));
});
