import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export function getSessionsDir() {
  return process.env.LOCAI_SESSIONS_DIR || path.join(os.homedir(), ".lokal_ajan", "sessions");
}

function safeName(name) {
  return name.replace(/[^a-zA-Z0-9._-]/g, "_");
}

export function saveSession(name, { model, messages, workdir }) {
  const dir = getSessionsDir();
  fs.mkdirSync(dir, { recursive: true });
  const file = path.join(dir, `${safeName(name)}.json`);
  const payload = {
    name,
    model,
    workdir,
    savedAt: new Date().toISOString(),
    messages,
  };
  fs.writeFileSync(file, JSON.stringify(payload, null, 2), "utf8");
  return file;
}

export function loadSession(name) {
  const file = path.join(getSessionsDir(), `${safeName(name)}.json`);
  if (!fs.existsSync(file)) return null;
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

export function listSessions() {
  const dir = getSessionsDir();
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((f) => f.endsWith(".json"))
    .map((f) => {
      try {
        const data = JSON.parse(fs.readFileSync(path.join(dir, f), "utf8"));
        return {
          name: data.name || f.replace(/\.json$/, ""),
          model: data.model || "",
          savedAt: data.savedAt || "",
          messageCount: Array.isArray(data.messages) ? data.messages.length : 0,
        };
      } catch {
        return { name: f.replace(/\.json$/, ""), model: "", savedAt: "", messageCount: 0 };
      }
    });
}
