import fs from "node:fs";
import path from "node:path";

/**
 * Compact persistent work log so small local models do not lose track of
 * what they have already inspected, created, or tested across long turns or
 * context-window pruning.
 */
export class WorkLog {
  constructor(workdir, { maxEntries = 60, persist = true } = {}) {
    this.workdir = workdir || process.cwd();
    this.maxEntries = maxEntries;
    this.persist = persist;
    this.logPath = path.join(this.workdir, ".locai", "worklog.jsonl");
    this.entries = [];
    if (this.persist) {
      this._load();
    }
  }

  _load() {
    try {
      if (!fs.existsSync(this.logPath)) return;
      const lines = fs.readFileSync(this.logPath, "utf8").split("\n").filter(Boolean);
      const parsed = [];
      for (const line of lines) {
        try {
          const obj = JSON.parse(line);
          if (obj && obj.kind && obj.summary) parsed.push(obj);
        } catch {
          // skip corrupt line
        }
      }
      this.entries = parsed.slice(-this.maxEntries);
    } catch {
      // ignore read errors
    }
  }

  add(kind, summary) {
    const clean = String(summary || "").replace(/\s+/g, " ").trim().slice(0, 220);
    if (!clean) return;
    const entry = {
      ts: new Date().toISOString().slice(11, 19),
      kind,
      summary: clean,
    };
    this.entries.push(entry);
    if (this.entries.length > this.maxEntries) {
      this.entries = this.entries.slice(-this.maxEntries);
    }
    if (this.persist) {
      try {
        fs.mkdirSync(path.dirname(this.logPath), { recursive: true });
        fs.appendFileSync(this.logPath, `${JSON.stringify(entry)}\n`, "utf8");
      } catch {
        // ignore write errors
      }
    }
  }

  clear() {
    this.entries = [];
    if (this.persist) {
      try {
        if (fs.existsSync(this.logPath)) fs.unlinkSync(this.logPath);
      } catch {
        // ignore
      }
    }
  }

  getEntries(limit = 20) {
    return this.entries.slice(-limit);
  }

  formatForPrompt(limit = 12) {
    if (!this.entries.length) return "";
    const recent = this.entries.slice(-limit);
    const lines = recent.map((e, idx) => `${idx + 1}. [${e.ts}] [${e.kind}] ${e.summary}`);
    return [
      "[ÇALIŞMA GÜNLÜĞÜ (Work Log) — Şimdiye kadar yapılanlar]",
      ...lines,
      "Önemli: Yukarıdaki adımları tekrarlama; kaldığın yerden devam et.",
    ].join("\n");
  }
}
