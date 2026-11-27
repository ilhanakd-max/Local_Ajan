import fs from "node:fs";
import path from "node:path";

const PROFILES = [
  { name_pattern: /^groq\//i, num_ctx: 32768, temperature: 0.1, native_tool_call: true, prompt_level: "standard", max_tool_output: 30000, supports_think_control: false, disable_thinking: true, repeat_penalty: 1.1, parse_retry_limit: 2 },
  { name_pattern: /^openrouter\//i, num_ctx: 32768, temperature: 0.1, native_tool_call: true, prompt_level: "standard", max_tool_output: 30000, supports_think_control: false, disable_thinking: true, repeat_penalty: 1.1, parse_retry_limit: 2 },
  { name_pattern: /^ninerouter\//i, num_ctx: 8192, temperature: 0.1, native_tool_call: true, prompt_level: "standard", max_tool_output: 15000, supports_think_control: false, disable_thinking: true, repeat_penalty: 1.1, parse_retry_limit: 2 },
  { name_pattern: /^nvidia\//i, num_ctx: 32768, temperature: 0.1, native_tool_call: true, prompt_level: "standard", max_tool_output: 30000, supports_think_control: false, disable_thinking: true, repeat_penalty: 1.1, parse_retry_limit: 2 },
  { name_pattern: /qwen3(?:\.\d+)?[.:\-]?\s*0\.[5-9]b/i, num_ctx: 4096, temperature: 0.15, native_tool_call: false, prompt_level: "minimal", max_tool_output: 4000, supports_think_control: true, disable_thinking: true, repeat_penalty: 1.2, parse_retry_limit: 3, num_predict: 3072, top_k: 20, top_p: 0.8 },
  { name_pattern: /qwen3(?:\.\d+)?[.:\-]?\s*1\.[5-9]b/i, num_ctx: 8192, temperature: 0.15, native_tool_call: false, prompt_level: "minimal", max_tool_output: 8000, supports_think_control: true, disable_thinking: true, repeat_penalty: 1.15, parse_retry_limit: 3, num_predict: 4096, top_k: 20, top_p: 0.8 },
  { name_pattern: /qwen3(?:\.\d+)?[.:\-]?\s*(?:2|3)(?:\.\d+)?b/i, num_ctx: 8192, temperature: 0.15, native_tool_call: false, prompt_level: "minimal", max_tool_output: 8000, supports_think_control: true, disable_thinking: true, repeat_penalty: 1.15, parse_retry_limit: 3, num_predict: 4096, top_k: 20, top_p: 0.8 },
  { name_pattern: /qwen3(?:\.\d+)?[.:\-]?\s*4b/i, num_ctx: 16384, temperature: 0.2, native_tool_call: true, prompt_level: "minimal", max_tool_output: 20000, supports_think_control: true, disable_thinking: true, repeat_penalty: 1.1, parse_retry_limit: 2 },
  { name_pattern: /qwen3(?:\.\d+)?[.:\-]?\s*(?:8|14|32)b/i, num_ctx: 32768, temperature: 0.2, native_tool_call: true, prompt_level: "standard", max_tool_output: 35000, supports_think_control: true, disable_thinking: true, repeat_penalty: 1.1, parse_retry_limit: 2 },
  { name_pattern: /qwen3(?:\.\d+)?/i, num_ctx: 16384, temperature: 0.2, native_tool_call: true, prompt_level: "standard", max_tool_output: 20000, supports_think_control: true, disable_thinking: true, repeat_penalty: 1.1, parse_retry_limit: 2 },
  { name_pattern: /qwen2\.5.*(?:0\.5|1\.5|3)b/i, num_ctx: 4096, temperature: 0.1, native_tool_call: false, prompt_level: "minimal", max_tool_output: 4000, supports_think_control: false, disable_thinking: true, repeat_penalty: 1.15, parse_retry_limit: 3, num_predict: 3072, top_k: 20, top_p: 0.8 },
  { name_pattern: /qwen2\.5/i, num_ctx: 16384, temperature: 0.15, native_tool_call: true, prompt_level: "standard", max_tool_output: 20000, supports_think_control: false, disable_thinking: true, repeat_penalty: 1.1, parse_retry_limit: 2 },
  { name_pattern: /deepseek-r1/i, num_ctx: 16384, temperature: 0.2, native_tool_call: false, prompt_level: "standard", max_tool_output: 15000, supports_think_control: false, disable_thinking: false, repeat_penalty: 1.1, parse_retry_limit: 2 },
  { name_pattern: /llama3\.[1-3]|gemma|phi|mistral|codellama/i, num_ctx: 8192, temperature: 0.15, native_tool_call: false, prompt_level: "standard", max_tool_output: 10000, supports_think_control: false, disable_thinking: true, repeat_penalty: 1.15, parse_retry_limit: 2 },
];

function extractSizeB(modelName) {
  const m = /(\d+(?:\.\d+)?)\s*b\b/i.exec(modelName);
  return m ? Number(m[1]) : null;
}

export function getProfileForModel(modelName) {
  for (const profile of PROFILES) {
    if (profile.name_pattern.test(modelName)) {
      return { ...profile };
    }
  }
  const sizeB = extractSizeB(modelName);
  if (sizeB !== null && sizeB <= 3.5) {
    return {
      name_pattern: "fallback-small",
      num_ctx: 4096,
      temperature: 0.15,
      native_tool_call: false,
      prompt_level: "minimal",
      max_tool_output: 4000,
      supports_think_control: false,
      disable_thinking: true,
      repeat_penalty: 1.2,
      parse_retry_limit: 3,
      num_predict: 3072,
      top_k: 20,
      top_p: 0.8,
    };
  }
  return {
    name_pattern: "fallback-standard",
    num_ctx: 8192,
    temperature: 0.15,
    native_tool_call: false,
    prompt_level: "standard",
    max_tool_output: 12000,
    supports_think_control: false,
    disable_thinking: true,
    repeat_penalty: 1.15,
    parse_retry_limit: 2,
  };
}

const SKIP_DIRS = new Set([
  "node_modules",
  ".git",
  ".locai",
  ".lokal_ajan",
  "dist",
  "build",
  "graphify-out",
  ".venv",
  "__pycache__",
]);

export function scanWorkspaceSize(workdir, maxFiles = 200) {
  let files = 0;
  let totalBytes = 0;
  if (!workdir || !fs.existsSync(workdir)) return { files, totalBytes };

  const stack = [workdir];
  while (stack.length && files < maxFiles) {
    const dir = stack.pop();
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      if (files >= maxFiles) break;
      if (entry.isDirectory()) {
        if (!SKIP_DIRS.has(entry.name) && !entry.name.startsWith(".")) {
          stack.push(path.join(dir, entry.name));
        }
      } else if (entry.isFile()) {
        try {
          const st = fs.statSync(path.join(dir, entry.name));
          files += 1;
          totalBytes += st.size;
        } catch {
          // ignore
        }
      }
    }
  }
  return { files, totalBytes };
}

export function getMaxAutoCtxForModel(modelName) {
  const sizeB = extractSizeB(modelName);
  if (sizeB !== null && sizeB <= 1.0) return 8192;
  if (sizeB !== null && sizeB <= 3.5) return 16384;
  return 32768;
}

const CTX_TIERS = [4096, 8192, 16384, 32768];

export function resolveDynamicNumCtx({
  modelName,
  baseNumCtx = 4096,
  workspaceStats = { files: 0, totalBytes: 0 },
  messagesChars = 0,
  reserveRatio = 0.35,
} = {}) {
  if (/^(groq|openrouter|ninerouter|nvidia)\//i.test(String(modelName || ""))) {
    return baseNumCtx;
  }

  let projectFloor = baseNumCtx;
  if (workspaceStats.files > 60 || workspaceStats.totalBytes > 120000) {
    projectFloor = Math.max(projectFloor, 16384);
  } else if (workspaceStats.files > 15 || workspaceStats.totalBytes > 25000) {
    projectFloor = Math.max(projectFloor, 8192);
  }

  const neededTokens = messagesChars > 0 ? Math.ceil(messagesChars / 3.5 / (1 - reserveRatio)) : 0;
  const target = Math.max(baseNumCtx, projectFloor, neededTokens);
  const cap = Math.max(baseNumCtx, getMaxAutoCtxForModel(modelName));

  for (const tier of CTX_TIERS) {
    if (tier >= target && tier <= cap) return tier;
  }
  return cap;
}
