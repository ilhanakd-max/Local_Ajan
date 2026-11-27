import test from "node:test";
import assert from "node:assert/strict";
import { extractAllToolCalls } from "../src/agent/parser.js";
import { AgentLoop } from "../src/agent/loop.js";

test("parser recovers malformed write_file JSON, arg_key format, and code-block fallback", () => {
  const malformed = `<tool_call>{"name": "write_file", "arguments": {"path": "index.html", "content": "<link rel="stylesheet" href="s.css">"}}</tool_call>`;
  const c1 = extractAllToolCalls(malformed);
  assert.equal(c1.length, 1);
  assert.equal(c1[0].name, "write_file");
  assert.equal(c1[0].args.path, "index.html");
  assert.ok(c1[0].args.content.includes("stylesheet"));

  const argKv = `<tool_call>run_shell\n<arg_key>command</arg_key><arg_value>ls -la</arg_value></tool_call>`;
  const c2 = extractAllToolCalls(argKv);
  assert.equal(c2.length, 1);
  assert.equal(c2[0].name, "run_shell");
  assert.equal(c2[0].args.command, "ls -la");

  const codeBlock = "İşte `saat.html` dosyası:\n```html\n<h1>Saat</h1>\n```";
  const c3 = extractAllToolCalls(codeBlock);
  assert.equal(c3.length, 1);
  assert.equal(c3[0].name, "write_file");
  assert.equal(c3[0].args.path, "saat.html");

  const summary = "Tüm dosyalar oluşturuldu (`saat.html`):\n```html\n<h1>Saat</h1>\n```";
  const c4 = extractAllToolCalls(summary);
  assert.equal(c4.length, 0);
});

test("AgentLoop retries on think-only empty output and malformed tool tags", async () => {
  let turn = 0;
  const loop = new AgentLoop({
    modelName: "qwen3:0.6b",
    quiet: true,
    streamFn: async function* () {
      turn++;
      if (turn === 1) {
        yield "<think>hmm</think>";
      } else if (turn === 2) {
        yield "<tool_call>{broken json";
      } else {
        yield "Tamamlandı.";
      }
    },
  });

  const out = await loop.runTurn("Merhaba");
  assert.equal(turn, 3);
  assert.equal(out, "Tamamlandı.");
});
