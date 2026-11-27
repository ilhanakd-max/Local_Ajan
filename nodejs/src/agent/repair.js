// Küçük modellerin araç adı / parametre hatalarını onarır (Python: agent/repair.py ile aynı mantık).

export const TOOL_ALIASES = {
  create_file: "write_file", createfile: "write_file", save_file: "write_file", writefile: "write_file",
  write: "write_file", new_file: "write_file", make_file: "write_file",
  update_file: "edit_file", modify_file: "edit_file", replace_in_file: "edit_file", str_replace: "edit_file",
  editfile: "edit_file", edit: "edit_file",
  open_file: "read_file", cat: "read_file", view_file: "read_file", readfile: "read_file", read: "read_file",
  ls: "list_dir", list_files: "list_dir", list_directory: "list_dir", listdir: "list_dir", dir: "list_dir",
  find_files: "glob", search_files: "glob", search: "grep", find_text: "grep",
  shell: "run_shell", bash: "run_shell", run_command: "run_shell", execute: "run_shell",
  exec: "run_shell", terminal: "run_shell", cmd: "run_shell", run: "run_shell",
  delegate: "delegate_task",
};

export const ARG_ALIASES = {
  path: ["file_path", "filepath", "filename", "file_name", "file", "dir", "directory", "folder", "dir_path", "name"],
  content: ["text", "code", "contents", "data", "body", "file_content", "file_contents", "source"],
  old_str: ["old", "old_string", "old_text", "search", "find", "original", "target", "before"],
  new_str: ["new", "new_string", "new_text", "replace", "replacement", "replace_with", "after"],
  command: ["cmd", "shell_command", "bash", "script", "commands"],
  pattern: ["query", "regex", "glob_pattern", "search", "text", "keyword"],
  task: ["description", "instruction", "prompt", "goal", "request"],
  task_description: ["task", "description", "instruction", "prompt", "goal"],
  query: ["q", "search", "text", "question", "pattern"],
};

const norm = (s) => String(s).trim().toLowerCase().replace(/[-\s]/g, "_").replace(/[^a-z0-9_]/g, "");

function similarity(a, b) {
  // Basit Levenshtein tabanlı benzerlik (0..1)
  const m = a.length, n = b.length;
  if (!m || !n) return 0;
  const dp = Array.from({ length: m + 1 }, (_, i) => [i, ...Array(n).fill(0)]);
  for (let j = 0; j <= n; j++) dp[0][j] = j;
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] = Math.min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
  }
  return 1 - dp[m][n] / Math.max(m, n);
}

export function resolveToolName(name, validNames) {
  if (typeof name !== "string" || !name.trim()) return null;
  const valid = [...validNames];
  if (valid.includes(name)) return name;
  const n = norm(name);
  for (const v of valid) if (norm(v) === n) return v;
  const alias = TOOL_ALIASES[n];
  if (alias && valid.includes(alias)) return alias;
  const squashed = n.replace(/_/g, "");
  for (const v of valid) if (v.replace(/_/g, "") === squashed) return v;
  let best = null, bestScore = 0.82;
  for (const v of valid) {
    const s = similarity(n, norm(v));
    if (s >= bestScore) { best = v; bestScore = s; }
  }
  return best;
}

function propType(schema) {
  if (schema?.type) return schema.type;
  for (const sub of schema?.anyOf || []) if (sub.type && sub.type !== "null") return sub.type;
  return "any";
}

function coerce(value, type) {
  try {
    if (type === "integer" && typeof value === "string" && /^-?\d+$/.test(value.trim())) return parseInt(value.trim(), 10);
    if (type === "integer" && typeof value === "number" && Number.isInteger(value)) return value;
    if (type === "number" && typeof value === "string" && value.trim() !== "" && !Number.isNaN(Number(value))) return Number(value);
    if (type === "boolean" && typeof value === "string") {
      const low = value.trim().toLowerCase();
      if (["true", "evet", "yes", "1"].includes(low)) return true;
      if (["false", "hayır", "hayir", "no", "0"].includes(low)) return false;
    }
    if (type === "string" && typeof value === "number") return String(value);
    if (type === "string" && Array.isArray(value) && value.every((v) => typeof v === "string")) return value.join("\n");
    if ((type === "array" || type === "object") && typeof value === "string") return JSON.parse(value);
  } catch { /* değeri olduğu gibi bırak */ }
  return value;
}

export function repairArgs(args, schema) {
  const params = schema?.parameters || {};
  const props = params.properties || {};
  const required = params.required || [];
  if (args === null || typeof args !== "object" || Array.isArray(args)) {
    if (typeof args === "string" && required.length === 1) return { [required[0]]: args };
    return {};
  }
  if (!Object.keys(props).length) return args;

  const fixed = {};
  const leftovers = {};
  for (const [k, v] of Object.entries(args)) (k in props ? fixed : leftovers)[k] = v;

  for (const real of Object.keys(props)) {
    if (real in fixed) continue;
    let hit = (ARG_ALIASES[real] || []).find((a) => a in leftovers);
    if (!hit) hit = Object.keys(leftovers).find((k) => norm(k) === norm(real));
    if (hit) { fixed[real] = leftovers[hit]; delete leftovers[hit]; }
  }

  const missing = required.filter((r) => !(r in fixed));
  const left = Object.keys(leftovers);
  if (missing.length === 1 && left.length === 1) {
    fixed[missing[0]] = leftovers[left[0]];
  }
  for (const [k, v] of Object.entries(fixed)) fixed[k] = coerce(v, propType(props[k]));
  return fixed;
}
