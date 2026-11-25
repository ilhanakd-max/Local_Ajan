import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import os from "node:os";
import fs from "node:fs";

import { stripThinking, filterThinkingStream } from "../src/agent/thinking.js";
import { extractToolCall, extractAllToolCalls } from "../src/agent/parser.js";
import { prepareContext, truncateToolOutput } from "../src/agent/context.js";
import { getProfileForModel } from "../src/llm/modelProfiles.js";
import { getSafePath, isDangerousShellCommand } from "../src/safety/sandbox.js";

test("stripThinking removes complete and unclosed think blocks", () => {
  assert.equal(stripThinking("<think>secret</think>Hello"), "Hello");
  assert.equal(stripThinking("Start<think>cut off"), "Start");
  assert.equal(stripThinking("No think here"), "No think here");
});

test("filterThinkingStream filters split think tags across chunks", async () => {
  async function* gen() {
    yield "Hi ";
    yield "<thi";
    yield "nk>internal";
    yield "</thi";
    yield "nk>World!";
  }
  let out = "";
  for await (const ch of filterThinkingStream(gen())) out += ch;
  assert.equal(out, "Hi World!");
});

test("parser extracts <tool_call>, broken tags, json blocks, and function calls", () => {
  const c1 = extractToolCall('<tool_call>{"name":"read_file","arguments":{"path":"a.js"}}</tool_call>');
  assert.deepEqual(c1, { name: "read_file", args: { path: "a.js" } });

  const c2 = extractToolCall('<tool_ca\nll>{"name":"list_dir","arguments":{}}</tool_call>');
  assert.deepEqual(c2, { name: "list_dir", args: {} });

  const c3 = extractToolCall('```json\n{"name":"grep","arguments":{"pattern":"foo"}}\n```');
  assert.deepEqual(c3, { name: "grep", args: { pattern: "foo" } });

  const c4 = extractToolCall('[read_file(path="src/app.js", start_line=10)]');
  assert.deepEqual(c4, { name: "read_file", args: { path: "src/app.js", start_line: 10 } });

  const c5 = extractAllToolCalls('<tool_call><function=read_file><parameter=path>x.txt</parameter></function></tool_call>');
  assert.deepEqual(c5, [{ name: "read_file", args: { path: "x.txt" } }]);
});

test("context truncation and sliding window preserve system and newest messages", () => {
  const longText = "x".repeat(3000);
  assert.ok(truncateToolOutput(longText, 100).length < 250);

  const msgs = [
    { role: "system", content: "SYS" },
    { role: "user", content: "old ".repeat(600) },
    { role: "assistant", content: "mid ".repeat(600) },
    { role: "user", content: "latest question" },
  ];
  const prepared = prepareContext(msgs, 500, 0.35);
  assert.equal(prepared[0].role, "system");
  assert.equal(prepared[prepared.length - 1].content, "latest question");
  assert.ok(prepared.some((m) => m.content.includes("kırpıldı")));
});

test("model profiles match small, cloud, and fallback models", () => {
  assert.equal(getProfileForModel("qwen3:0.6b").prompt_level, "minimal");
  assert.equal(getProfileForModel("qwen3:1.7b").num_ctx, 8192);
  assert.equal(getProfileForModel("openrouter/free").native_tool_call, true);
  assert.equal(getProfileForModel("groq/llama-3.3-70b").num_ctx, 32768);
});

test("sandbox blocks path traversal and dangerous commands", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "locai-sb-"));
  try {
    assert.throws(() => getSafePath("../etc/passwd", tmp), /Güvenlik İhlali/);
    assert.ok(getSafePath("sub/file.txt", tmp).startsWith(fs.realpathSync(tmp)));
    assert.equal(isDangerousShellCommand("rm -rf /"), true);
    assert.equal(isDangerousShellCommand("npm test"), false);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});
