import path from "node:path";

const PROTECTED_DIRS = new Set([".git", "node_modules", ".venv", "venv", "__pycache__"]);
const MUTATING_TOOLS = new Set(["write_file", "edit_file"]);

export function isProtectedWritePath(targetPath) {
  const parts = path.normalize(targetPath).split(path.sep);
  return parts.some((p) => PROTECTED_DIRS.has(p));
}

const _recentShellDeletes = new Map();
const _DELETE_CMD_RE = /(?:^|\s|&&|\|\||;)(?:rm|unlink|mv)\s+(?:-[a-zA-Z]+\s+)*([^\s;&|]+)/g;
const _SHELL_MUTATE_RE =
  /(?:>>?|tee\s+|sed\s+-i|mv\s+|cp\s+|rm\s+|mkdir\s+|touch\s+|chmod\s+|chown\s+|git\s+(?:add|commit|checkout|reset|stash|apply)|npm\s+install|pip\s+install|python3?\s+.*-m\s+pip)/i;

export function recordShellDelete(cmd, workdir = ".") {
  const now = Date.now();
  for (const [k, ts] of _recentShellDeletes.entries()) {
    if (now - ts > 120_000) _recentShellDeletes.delete(k);
  }
  let match;
  _DELETE_CMD_RE.lastIndex = 0;
  while ((match = _DELETE_CMD_RE.exec(cmd)) !== null) {
    const raw = match[1].replace(/^["']|["']$/g, "");
    if (!raw || raw.startsWith("-")) continue;
    const resolved = path.resolve(workdir, raw);
    _recentShellDeletes.set(resolved, now);
  }
}

export function checkShellDeleteBypass(resolvedPath) {
  const ts = _recentShellDeletes.get(path.resolve(resolvedPath));
  if (ts !== undefined && Date.now() - ts <= 120_000) {
    return (
      `Error: '${path.basename(resolvedPath)}' was recently removed/moved via run_shell and cannot be ` +
      "recreated with 'write_file'. Use 'edit_file' for modifying existing files instead of deleting and rewriting."
    );
  }
  return null;
}

export function clearShellDeletesForPath(resolvedPath) {
  _recentShellDeletes.delete(path.resolve(resolvedPath));
}

export function isMutatingToolCall(toolName, args) {
  if (MUTATING_TOOLS.has(toolName)) return true;
  if (toolName === "run_shell") {
    const cmd = String((args && args.command) || "");
    return _SHELL_MUTATE_RE.test(cmd);
  }
  return false;
}

export class RepetitionLoopGuard {
  constructor({ threshold = null, stopAfter = null, window = 12 } = {}) {
    this.threshold = threshold ?? Number(process.env.LOCAI_LOOP_THRESHOLD || 3);
    this.stopAfter = stopAfter ?? Number(process.env.LOCAI_LOOP_STOP_AFTER || 3);
    this.window = window;
    this.history = [];
    this.blockedRounds = 0;
  }

  _signature(toolName, args) {
    const sorted = Object.keys(args || {})
      .sort()
      .reduce((acc, k) => {
        acc[k] = args[k];
        return acc;
      }, {});
    return `${toolName}:${JSON.stringify(sorted)}`;
  }

  _detectCycle() {
    const n = this.history.length;
    for (const period of [2, 3, 4]) {
      if (n < period * 2) continue;
      const tail = this.history.slice(n - period * 2);
      let same = true;
      for (let i = 0; i < period; i++) {
        if (tail[i] !== tail[i + period]) {
          same = false;
          break;
        }
      }
      if (same && new Set(tail.slice(0, period)).size > 1) {
        return period;
      }
    }
    return null;
  }

  recordAndCheck(toolName, args, _isError = false) {
    if (isMutatingToolCall(toolName, args)) {
      this.history = [];
      this.blockedRounds = 0;
      return { blocked: false, shouldAbort: false, reason: "" };
    }

    const sig = this._signature(toolName, args);
    this.history.push(sig);
    if (this.history.length > this.window) {
      this.history.shift();
    }

    const sameCount = this.history.filter((s) => s === sig).length;
    const cyclePeriod = this._detectCycle();

    if (sameCount >= this.threshold || cyclePeriod !== null) {
      this.blockedRounds += 1;
      const shouldAbort = this.blockedRounds >= this.stopAfter;
      const reason =
        cyclePeriod !== null
          ? `Periodic tool-call loop detected (cycle of length ${cyclePeriod} repeating '${toolName}')`
          : `Identical tool call '${toolName}' repeated ${sameCount} times without state change`;
      return { blocked: true, shouldAbort, reason };
    }

    return { blocked: false, shouldAbort: false, reason: "" };
  }
}

export function detectTextRepetition(text, minLineLen = 28, minRepeats = 4) {
  if (!text || text.length < minLineLen * minRepeats) return false;
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length >= minLineLen);
  if (lines.length < minRepeats) return false;
  const counts = new Map();
  for (const line of lines.slice(-24)) {
    const next = (counts.get(line) || 0) + 1;
    counts.set(line, next);
    if (next >= minRepeats) return true;
  }
  return false;
}
