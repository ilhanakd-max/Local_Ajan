import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { AgentLoop } from "../src/agent/loop.js";

test("AgentLoop executes tool calls from mocked stream and returns final answer", async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "locai-loop-"));
  let turn = 0;
  try {
    const mockStream = async function* () {
      turn += 1;
      if (turn === 1) {
        yield '<think>planning</think><tool_call>{"name":"write_file","arguments":{"path":"hello.txt","content":"merhaba"}}</tool_call>';
      } else if (turn === 2) {
        yield '<tool_call>{"name":"read_file","arguments":{"path":"hello.txt"}}</tool_call>';
      } else {
        yield "Dosya oluşturuldu ve içeriği 'merhaba' olarak doğrulandı.";
      }
    };

    const agent = new AgentLoop({
      modelName: "qwen3:1.7b",
      workdir: tmp,
      autoConfirm: true,
      quiet: true,
      streamFn: mockStream,
    });

    const out = await agent.runTurn("hello.txt oluştur ve doğrula");
    assert.match(out, /merhaba/);
    assert.equal(fs.readFileSync(path.join(tmp, "hello.txt"), "utf8"), "merhaba");
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test("AgentLoop auto-attaches quoted local file paths dropped into the prompt", async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "locai-attach-"));
  const planPath = path.join(tmp, "Plan.md");
  fs.writeFileSync(planPath, "# Proje Planı\n- Adım 1: Test yaz", "utf8");
  let seenUserMsg = "";

  try {
    const mockStream = async function* ({ messages }) {
      const lastUser = [...messages].reverse().find((m) => m.role === "user");
      seenUserMsg = lastUser?.content || "";
      yield "Plan.md incelendi: Adım 1 test yazmak.";
    };

    const agent = new AgentLoop({
      modelName: "qwen3:1.7b",
      workdir: tmp,
      autoConfirm: true,
      quiet: true,
      streamFn: mockStream,
    });

    const out = await agent.runTurn(`'${planPath}' `);
    assert.match(seenUserMsg, /<attached_file path="Plan\.md">/);
    assert.match(seenUserMsg, /# Proje Planı/);
    assert.match(out, /Plan\.md incelendi/);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test("AgentLoop.setWorkerModel toggles orchestrator mode and updates system prompt", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "locai-orch-"));
  try {
    const agent = new AgentLoop({
      modelName: "groq/llama-3.3-70b-versatile",
      workdir: tmp,
      autoConfirm: true,
      quiet: true,
    });
    assert.doesNotMatch(agent.history.messages[0].content, /ORCHESTRATOR MODE/);

    agent.setWorkerModel("qwen3:1.7b");
    assert.equal(agent.workerModel, "qwen3:1.7b");
    assert.match(agent.history.messages[0].content, /ORCHESTRATOR MODE/);
    assert.match(agent.history.messages[0].content, /qwen3:1\.7b/);

    agent.setWorkerModel(null);
    assert.equal(agent.workerModel, null);
    assert.doesNotMatch(agent.history.messages[0].content, /ORCHESTRATOR MODE/);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test("AgentLoop nudges model when it runs mkdir and claims files were created without write_file", async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "locai-mkdir-nudge-"));
  let turn = 0;
  try {
    const mockStream = async function* () {
      turn += 1;
      if (turn === 1) {
        yield '<tool_call>{"name":"run_shell","arguments":{"command":"mkdir app_dir"}}</tool_call>';
      } else if (turn === 2) {
        yield "app_dir klasörü oluşturuldu ve içine index.html yerleştirildi.";
      } else if (turn === 3) {
        yield '<tool_call>{"name":"write_file","arguments":{"path":"app_dir/index.html","content":"<h1>OK</h1>"}}</tool_call>';
      } else {
        yield "app_dir/index.html dosyası gerçekten oluşturuldu.";
      }
    };

    const agent = new AgentLoop({
      modelName: "gemma4:4b",
      workdir: tmp,
      autoConfirm: true,
      quiet: true,
      streamFn: mockStream,
    });

    const out = await agent.runTurn("app_dir içine index.html yap");
    assert.equal(fs.readFileSync(path.join(tmp, "app_dir", "index.html"), "utf8"), "<h1>OK</h1>");
    assert.match(out, /oluşturuldu/);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});
