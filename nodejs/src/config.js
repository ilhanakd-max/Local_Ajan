import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export function getConfigPath() {
  return process.env.LOKAL_AJAN_CONFIG || path.join(os.homedir(), ".config", "lokal-ajan", "config.toml");
}

export function getStatePath() {
  return process.env.LOKAL_AJAN_STATE || path.join(os.homedir(), ".config", "lokal-ajan", "state.json");
}

function parseSimpleToml(text) {
  const result = {};
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || line.startsWith("[")) continue;
    const eq = line.indexOf("=");
    if (eq === -1) continue;
    const key = line.slice(0, eq).trim();
    let val = line.slice(eq + 1).trim();
    if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
      result[key] = val.slice(1, -1);
    } else if (val === "true") {
      result[key] = true;
    } else if (val === "false") {
      result[key] = false;
    } else if (/^-?\d+(\.\d+)?$/.test(val)) {
      result[key] = Number(val);
    } else if (val.startsWith("[") && val.endsWith("]")) {
      try {
        result[key] = JSON.parse(val.replace(/'/g, '"'));
      } catch {
        // ignore malformed array
      }
    }
  }
  return result;
}

export function loadState(customPath = null) {
  const stateFile = customPath || getStatePath();
  if (!fs.existsSync(stateFile)) return {};
  try {
    return JSON.parse(fs.readFileSync(stateFile, "utf8"));
  } catch {
    return {};
  }
}

export function saveState(state, customPath = null) {
  const stateFile = customPath || getStatePath();
  try {
    fs.mkdirSync(path.dirname(stateFile), { recursive: true });
    const current = loadState(stateFile);
    Object.assign(current, state);
    fs.writeFileSync(stateFile, JSON.stringify(current, null, 2), "utf8");
  } catch {
    // ignore state write failures
  }
}

export function loadConfig(customPath = null) {
  const configFile = customPath || getConfigPath();
  let data = {};
  if (fs.existsSync(configFile)) {
    try {
      data = parseSimpleToml(fs.readFileSync(configFile, "utf8"));
    } catch {
      data = {};
    }
  }

  if (!data.default_model) {
    const state = loadState();
    const saved = state.model || state.last_model;
    if (saved) data.default_model = saved;
  }

  return {
    default_model: data.default_model || "qwen3:1.7b",
    ollama_host: process.env.OLLAMA_HOST || data.ollama_host || "http://localhost:11434",
    ollama_timeout: data.ollama_timeout ?? null,
    openrouter_api_key: process.env.OPENROUTER_API_KEY || data.openrouter_api_key || "",
    groq_api_key: process.env.GROQ_API_KEY || data.groq_api_key || "",
    ninerouter_host: process.env.NINEROUTER_HOST || data.ninerouter_host || "http://localhost:20128/v1",
    ninerouter_api_key: process.env.NINEROUTER_API_KEY || data.ninerouter_api_key || "",
    nvidia_api_key: process.env.NVIDIA_API_KEY || data.nvidia_api_key || "",
    max_steps: Number(data.max_steps ?? 20),
    worker_max_retries: Number(data.worker_max_retries ?? 2),
    require_confirm_for: Array.isArray(data.require_confirm_for)
      ? data.require_confirm_for
      : ["write_file", "edit_file", "run_shell"],
    shell_timeout: Number(data.shell_timeout ?? 120),
  };
}
