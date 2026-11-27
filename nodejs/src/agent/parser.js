import { registry } from "../tools/index.js";
import { stripThinking } from "./thinking.js";
import { resolveToolName, repairArgs } from "./repair.js";

function normalizeBrokenTags(text) {
  return text
    .replace(/<\s*t\s*o\s*o\s*l\s*[_\s]*c\s*a\s*l\s*l?\s*>/gi, "<tool_call>")
    .replace(/<\s*\/\s*t\s*o\s*o\s*l\s*[_\s]*c\s*a\s*l\s*l?\s*>/gi, "</tool_call>")
    .replace(/<\s*f\s*u\s*n\s*c\s*t\s*i\s*o\s*n/gi, "<function")
    .replace(/<\s*\/\s*f\s*u\s*n\s*c\s*t\s*i\s*o\s*n\s*>/gi, "</function>")
    .replace(/<\s*p\s*a\s*r\s*a\s*m\s*e\s*t\s*e\s*r/gi, "<parameter")
    .replace(/<\s*p\s*a\s*r\s*a\s*m/gi, "<param")
    .replace(/<\/\s*<\/\s*tool_call\s*>/gi, "</tool_call>");
}

function buildValidNames(extraValidNames = null) {
  const valid = new Set(registry.getAllTools().map((t) => t.name));
  if (extraValidNames) {
    for (const n of extraValidNames) valid.add(n);
  }
  return valid;
}

// Etiketli/JSON stratejilerinde: takma adlı araç adını (create_file -> write_file)
// ve parametre adlarını onarır. Geçersizse null.
function acceptResult(res, validNames) {
  if (!res) return null;
  const name = resolveToolName(res.name, validNames);
  if (!name) return null;
  const tool = registry.get(name);
  const schema = tool ? { parameters: tool.parameters } : null;
  return { ...res, name, args: schema ? repairArgs(res.args, schema) : res.args };
}

function extractBalancedJson(text) {
  const start = text.indexOf("{");
  if (start === -1) return null;
  let depth = 0;
  let inStr = false;
  let quote = "";
  let escaped = false;

  for (let i = start; i < text.length; i++) {
    const ch = text[i];
    if (escaped) {
      escaped = false;
      continue;
    }
    if (ch === "\\" && inStr) {
      escaped = true;
      continue;
    }
    if (inStr) {
      if (ch === quote) inStr = false;
      continue;
    }
    if (ch === '"' || ch === "'") {
      inStr = true;
      quote = ch;
    } else if (ch === "{") {
      depth++;
    } else if (ch === "}") {
      depth--;
      if (depth === 0) {
        return text.slice(start, i + 1);
      }
    }
  }
  return null;
}

function cleanupJson(str) {
  return str.replace(/,\s*([}\]])/g, "$1").trim();
}

function tryParseMalformedToolCall(text) {
  if (text.includes("write_file")) {
    const pathM = /["']path["']\s*:\s*["']([^"']+)["']/.exec(text);
    const contentM = /["']content["']\s*:\s*["']/.exec(text);
    if (pathM && contentM) {
      const path = pathM[1].trim();
      const rest = text.slice(contentM.index + contentM[0].length);
      const endM = /["']\s*\}[\s\}]*$/.exec(rest);
      let content = endM ? rest.slice(0, endM.index) : rest.replace(/[\s"\}\]]*(?:<\/tool_call>)?$/, "");
      if (content.includes("\\n") && !content.includes("\n")) {
        content = content.replace(/\\n/g, "\n").replace(/\\"/g, '"').replace(/\\t/g, "\t");
      }
      return { name: "write_file", args: { path, content } };
    }
  }
  if (text.includes("edit_file")) {
    const pathM = /["']path["']\s*:\s*["']([^"']+)["']/.exec(text);
    const oldM = /["']old_str["']\s*:\s*["']/.exec(text);
    const newM = /["']new_str["']\s*:\s*["']/.exec(text);
    if (pathM && oldM && newM && newM.index > oldM.index) {
      const path = pathM[1].trim();
      const beforeNew = text.slice(oldM.index + oldM[0].length, newM.index);
      const endOld = /["']\s*,\s*["']$/.exec(beforeNew);
      if (endOld) {
        const old_str = beforeNew.slice(0, endOld.index);
        const rest = text.slice(newM.index + newM[0].length);
        const endNew = /["']\s*\}[\s\}]*$/.exec(rest);
        const new_str = endNew ? rest.slice(0, endNew.index) : rest.replace(/[\s"\}\]]*$/, "");
        return { name: "edit_file", args: { path, old_str, new_str } };
      }
    }
  }
  if (text.includes("run_shell")) {
    const cmdM = /["']command["']\s*:\s*["']/.exec(text);
    if (cmdM) {
      const rest = text.slice(cmdM.index + cmdM[0].length);
      const endM = /["']\s*\}[\s\}]*$/.exec(rest);
      const command = endM ? rest.slice(0, endM.index) : rest.replace(/[\s"\}\]]*$/, "");
      return { name: "run_shell", args: { command } };
    }
  }
  return null;
}

function tryParseToolJson(raw) {
  if (!raw) return null;
  const cleaned = cleanupJson(raw);
  const candidate = extractBalancedJson(cleaned) || cleaned;
  try {
    const obj = JSON.parse(candidate);
    if (obj && typeof obj === "object") {
      const name = obj.name || obj.tool || obj.function;
      let args = obj.arguments ?? obj.args ?? obj.parameters ?? {};
      if (typeof args === "string") {
        try {
          args = JSON.parse(args);
        } catch {
          args = {};
        }
      }
      if (typeof name === "string" && typeof args === "object" && args !== null) {
        return { name: name.trim(), args };
      }
    }
  } catch {
    return tryParseMalformedToolCall(cleaned);
  }
  return tryParseMalformedToolCall(cleaned);
}

function tryParseXmlToolCall(inner, validNames) {
  const fnMatch = /<function\s*=\s*([a-zA-Z0-9_]+)\s*>([\s\S]*?)(?:<\/function>|$)/i.exec(inner);
  if (!fnMatch) return null;
  const name = fnMatch[1].trim();
  if (!validNames.has(name)) return null;

  const body = fnMatch[2];
  const args = {};
  const paramRe = /<param(?:eter)?\s*(?:name\s*=\s*["']?|["']?=\s*)([a-zA-Z0-9_]+)["']?\s*>([\s\S]*?)<\/param(?:eter)?>/gi;
  let pm;
  while ((pm = paramRe.exec(body)) !== null) {
    args[pm[1].trim()] = pm[2].trim();
  }
  return { name, args };
}

function parseKwargs(argStr) {
  const args = {};
  const re = /([a-zA-Z0-9_]+)\s*=\s*(?:"((?:\\.|[^"\\])*)"|'((?:\\.|[^'\\])*)'|(true|false|null|-?\d+(?:\.\d+)?))/g;
  let m;
  while ((m = re.exec(argStr)) !== null) {
    const key = m[1];
    if (m[2] !== undefined) {
      args[key] = m[2].replace(/\\n/g, "\n").replace(/\\"/g, '"').replace(/\\\\/g, "\\");
    } else if (m[3] !== undefined) {
      args[key] = m[3].replace(/\\n/g, "\n").replace(/\\'/g, "'").replace(/\\\\/g, "\\");
    } else if (m[4] === "true") {
      args[key] = true;
    } else if (m[4] === "false") {
      args[key] = false;
    } else if (m[4] === "null") {
      args[key] = null;
    } else {
      args[key] = Number(m[4]);
    }
  }
  return args;
}

function tryParseFunctionCall(inner, validNames) {
  const m = /\[?([a-zA-Z_][a-zA-Z0-9_]*)\(([\s\S]*?)\)\]?/.exec(inner.trim());
  if (!m) return null;
  const name = m[1];
  if (!validNames.has(name)) return null;
  const args = parseKwargs(m[2]);
  return { name, args };
}

function tryParseArgKeyValue(inner, validNames) {
  if (!inner.includes("<arg_key>")) return null;
  const toolMatch = /^([a-zA-Z0-9_]+)/.exec(inner.trim());
  if (!toolMatch || !validNames.has(toolMatch[1])) return null;
  const args = {};
  const kvRe = /<arg_key>\s*([\s\S]*?)\s*<\/arg_key>\s*<arg_value>\s*([\s\S]*?)\s*<\/arg_value>/gi;
  let m;
  while ((m = kvRe.exec(inner)) !== null) {
    args[m[1].trim()] = m[2].trim();
  }
  return Object.keys(args).length ? { name: toolMatch[1], args } : null;
}

const FILENAME_RE =
  "[a-zA-Z0-9_\\-]+(?:\\.[a-zA-Z0-9_\\-]+)*\\.(?:html?|css|js|py|txt|json|toml|ya?ml|md|sh|ts|tsx|jsx|go|rs|java|cpp|c|h|sql)";
const ALREADY_DONE_RE =
  /(?:dosya(?:lar)?\s+(?:oluşturuldu|kaydedildi|hazır|yazıldı)|tüm\s+dosyalar\s+hazır|files?\s+(?:created|saved|written|ready))/i;

function nearestFilename(prefix, suffix) {
  const preRe = new RegExp("[`'\"( ](" + FILENAME_RE + ")[`'\")\\s]?", "gi");
  let last = null;
  let m;
  while ((m = preRe.exec(prefix)) !== null) last = m[1];
  if (last) return last;

  const sufRe = new RegExp("[`'\"( ](" + FILENAME_RE + ")[`'\")\\s]?", "i");
  const sm = sufRe.exec(suffix);
  return sm ? sm[1] : null;
}

function extractCodeFilesWithNames(text) {
  if (ALREADY_DONE_RE.test(text)) return [];
  const blockRe = /```([a-zA-Z0-9_+.-]*)\s*\n?([\s\S]*?)```/g;
  const pairs = [];
  const seen = new Set();
  let m;
  while ((m = blockRe.exec(text)) !== null) {
    const lang = (m[1] || "").trim().toLowerCase();
    const code = m[2].replace(/^\n+|\n+$/g, "");
    if (lang === "json" || !code.trim()) continue;
    const start = m.start ?? m.index;
    const end = start + m[0].length;
    const prefix = text.slice(Math.max(0, start - 1000), start);
    const nextFence = text.indexOf("```", end);
    const suffix = nextFence !== -1 ? text.slice(end, nextFence) : text.slice(end);
    const filename = nearestFilename(prefix, suffix);
    if (filename && !seen.has(filename)) {
      seen.add(filename);
      pairs.push({ name: "write_file", args: { path: filename, content: code } });
    }
  }
  return pairs;
}

export function extractToolCall(rawText, extraValidNames = null) {
  const calls = extractAllToolCalls(rawText, extraValidNames);
  return calls.length ? calls[0] : null;
}

export function extractAllToolCalls(rawText, extraValidNames = null) {
  let text = stripThinking(rawText || "");
  text = normalizeBrokenTags(text);
  const validNames = buildValidNames(extraValidNames);
  const found = [];

  // 1. <|tool_call_start|>...<|tool_call_end|>
  const lfmRe = /<\|tool_call_start\|>([\s\S]*?)<\|tool_call_end\|>/g;
  let m;
  while ((m = lfmRe.exec(text)) !== null) {
    const inner = m[1].trim();
    const res =
      tryParseToolJson(inner) ||
      tryParseXmlToolCall(inner, validNames) ||
      tryParseFunctionCall(inner, validNames) ||
      tryParseArgKeyValue(inner, validNames);
    { const acc = acceptResult(res, validNames); if (acc) found.push(acc); }
  }
  if (found.length) return found;

  // 2. <tool_call>...</tool_call> (or unclosed <tool_call>)
  const tagRe = /<tool_call>([\s\S]*?)(?:<\/tool_call>|$)/g;
  while ((m = tagRe.exec(text)) !== null) {
    const inner = m[1].trim();
    const res =
      tryParseToolJson(inner) ||
      tryParseXmlToolCall(inner, validNames) ||
      tryParseFunctionCall(inner, validNames) ||
      tryParseArgKeyValue(inner, validNames);
    { const acc = acceptResult(res, validNames); if (acc) found.push(acc); }
  }
  if (found.length) return found;

  // 3. ```json ... ``` blocks
  const jsonBlockRe = /```(?:json)?\s*([\s\S]*?)```/gi;
  while ((m = jsonBlockRe.exec(text)) !== null) {
    const res = tryParseToolJson(m[1]);
    { const acc = acceptResult(res, validNames); if (acc) found.push(acc); }
  }
  if (found.length) return found;

  // 4. Code-block file fallback (e.g. `saat.html` + ```html ... ```)
  if (validNames.has("write_file")) {
    const codeFiles = extractCodeFilesWithNames(text);
    if (codeFiles.length) return codeFiles;
  }

  // 5. Function call syntax anywhere in text
  const fnCall = tryParseFunctionCall(text, validNames);
  if (fnCall) return [fnCall];

  // 6. Raw balanced JSON
  const rawJson = tryParseToolJson(text);
  if (rawJson && validNames.has(rawJson.name)) return [rawJson];

  return [];
}
