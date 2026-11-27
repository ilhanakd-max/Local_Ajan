import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { WorkLog } from "../src/agent/workLog.js";
import { prepareContext } from "../src/agent/context.js";

test("WorkLog persists entries to .locai/worklog.jsonl and reloads them", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "locai-worklog-"));
  try {
    const log1 = new WorkLog(tmp);
    log1.add("GÖREV", "app.py oluştur");
    log1.add("write_file", '{"path":"app.py"} -> Dosya oluşturuldu');

    const log2 = new WorkLog(tmp);
    assert.equal(log2.getEntries().length, 2);
    const formatted = log2.formatForPrompt();
    assert.match(formatted, /ÇALIŞMA GÜNLÜĞÜ/);
    assert.match(formatted, /app\.py oluştur/);
    assert.match(formatted, /write_file/);

    log2.clear();
    assert.equal(log2.getEntries().length, 0);
    assert.equal(fs.existsSync(path.join(tmp, ".locai", "worklog.jsonl")), false);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test("prepareContext injects workLogSummary when older messages are pruned", () => {
  const messages = [
    { role: "system", content: "You are LocAi." },
    { role: "user", content: "old task " + "x".repeat(1200) },
    { role: "assistant", content: "old reply " + "y".repeat(1200) },
    { role: "user", content: "devam et" },
  ];
  const summary = "[ÇALIŞMA GÜNLÜĞÜ]\n1. [write_file] app.js -> OK";
  const prepared = prepareContext(messages, 600, 0.35, summary);

  assert.equal(prepared[0].role, "system");
  assert.match(prepared[1].content, /ÇALIŞMA GÜNLÜĞÜ/);
  assert.equal(prepared[prepared.length - 1].content, "devam et");
});
