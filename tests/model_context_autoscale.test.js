import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import {
  resolveDynamicNumCtx,
  scanWorkspaceSize,
} from "../src/llm/modelProfiles.js";
import { AgentLoop } from "../src/agent/loop.js";

test("resolveDynamicNumCtx scales 4K model to 8K or 16K based on project size", () => {
  // Small project -> stays at 4096
  assert.equal(
    resolveDynamicNumCtx({
      modelName: "qwen3:0.6b",
      baseNumCtx: 4096,
      workspaceStats: { files: 4, totalBytes: 5000 },
    }),
    4096
  );

  // Medium project -> scales 4096 -> 8192
  assert.equal(
    resolveDynamicNumCtx({
      modelName: "qwen3:0.6b",
      baseNumCtx: 4096,
      workspaceStats: { files: 22, totalBytes: 30000 },
    }),
    8192
  );

  // Large project with 1.7b/3b model -> scales up to 16384
  assert.equal(
    resolveDynamicNumCtx({
      modelName: "hf.co/LiquidAI/LFM3-1.7B-GGUF:Q8_0",
      baseNumCtx: 4096,
      workspaceStats: { files: 75, totalBytes: 150000 },
    }),
    16384
  );

  // Cloud models keep their configured num_ctx
  assert.equal(
    resolveDynamicNumCtx({
      modelName: "groq/llama-3.3-70b-versatile",
      baseNumCtx: 32768,
      workspaceStats: { files: 200, totalBytes: 900000 },
    }),
    32768
  );
});

test("scanWorkspaceSize counts project files and ignores node_modules/.git", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "locai-scan-"));
  try {
    fs.writeFileSync(path.join(tmp, "a.js"), "console.log(1);", "utf8");
    fs.mkdirSync(path.join(tmp, "node_modules"));
    fs.writeFileSync(path.join(tmp, "node_modules", "ignored.js"), "x".repeat(50000), "utf8");

    const stats = scanWorkspaceSize(tmp);
    assert.equal(stats.files, 1);
    assert.equal(stats.totalBytes, 15);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test("AgentLoop dynamically scales activeNumCtx when prompt load exceeds 4K", async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "locai-dynctx-"));
  let observedCtx = 0;
  try {
    const agent = new AgentLoop({
      modelName: "hf.co/LiquidAI/LFM3-1.7B-GGUF:Q8_0",
      workdir: tmp,
      autoConfirm: true,
      quiet: true,
      streamFn: async function* ({ numCtx }) {
        observedCtx = numCtx;
        yield "Tamamlandı.";
      },
    });
    assert.equal(agent.activeNumCtx, 4096);

    // Send a large prompt (~20k chars > 4096 token budget)
    await agent.runTurn("x".repeat(20000));
    assert.ok(observedCtx >= 8192, `Expected numCtx >= 8192, got ${observedCtx}`);
    assert.equal(agent.activeNumCtx, observedCtx);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});
