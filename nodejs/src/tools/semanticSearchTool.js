import fs from "node:fs";
import path from "node:path";
import { getSafePath } from "../safety/sandbox.js";

const IGNORE_DIRS = new Set([
  ".git",
  "node_modules",
  ".venv",
  "venv",
  "__pycache__",
  "dist",
  "build",
  ".pytest_cache",
  ".lokal_ajan",
  "graphify-out",
]);

const CODE_EXTS = new Set([
  ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rs",
  ".java", ".c", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".sh", ".md",
]);

const DEF_BOUNDARY_RE =
  /^\s*(?:async\s+)?(?:def|class|function|export\s+(?:default\s+)?(?:function|class|const)|fn|struct|impl|interface|type)\b/;

function tokenize(text) {
  const rawTokens = text.match(/[a-zA-Z0-9_]+/g) || [];
  const out = [];
  for (const raw of rawTokens) {
    const parts = raw
      .replace(/([a-z])([A-Z])/g, "$1 $2")
      .replace(/_/g, " ")
      .toLowerCase()
      .split(/\s+/)
      .filter(Boolean);
    out.push(...parts);
  }
  return out;
}

function chunkFile(filePath, maxChunkLines = 60) {
  let lines;
  try {
    lines = fs.readFileSync(filePath, "utf8").split(/\r?\n/);
  } catch {
    return [];
  }
  if (!lines.length) return [];

  const chunks = [];
  let start = 0;
  for (let i = 0; i < lines.length; i++) {
    if (
      i > start &&
      ((DEF_BOUNDARY_RE.test(lines[i]) && i - start >= 8) || i - start >= maxChunkLines)
    ) {
      chunks.push({ line_start: start + 1, line_end: i, text: lines.slice(start, i).join("\n") });
      start = i;
    }
  }
  if (start < lines.length) {
    chunks.push({
      line_start: start + 1,
      line_end: lines.length,
      text: lines.slice(start).join("\n"),
    });
  }
  return chunks;
}

async function ollamaEmbed(texts, model, host) {
  try {
    const res = await fetch(`${host.replace(/\/$/, "")}/api/embed`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model, input: texts }),
      signal: AbortSignal.timeout(15000),
    });
    if (!res.ok) return null;
    const data = await res.json();
    if (Array.isArray(data.embeddings) && data.embeddings.length === texts.length) {
      return data.embeddings;
    }
  } catch {
    // fallback to lexical BM25
  }
  return null;
}

function cosine(a, b) {
  let dot = 0;
  let na = 0;
  let nb = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  if (na === 0 || nb === 0) return 0;
  return dot / (Math.sqrt(na) * Math.sqrt(nb));
}

export class SemanticCodeSearchTool {
  constructor(workdir = null) {
    this.name = "semantic_code_search";
    this.description =
      "Searches code by behavior/meaning when exact symbol names are unknown; returns candidate files and line ranges";
    this.requiresConfirm = false;
    this.workdir = workdir;
    this.parameters = {
      type: "object",
      properties: {
        query: { type: "string", description: "Natural-language description of what the code does" },
        path: { type: "string", description: "Root directory to search (default: '.')" },
        max_results: { type: "integer", description: "Maximum candidate files to return (default: 5)" },
      },
      required: ["query"],
    };
  }

  async run({ query, path: targetPath = ".", max_results = 5 }) {
    let rootStr;
    try {
      rootStr = getSafePath(targetPath, this.workdir);
    } catch (e) {
      return `Error: ${e.message}`;
    }

    if (!fs.existsSync(rootStr)) {
      return `Error: Path '${targetPath}' does not exist.`;
    }

    const chunks = [];
    const walk = (dir) => {
      const entries = fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name));
      for (const e of entries) {
        if (IGNORE_DIRS.has(e.name) || e.name.startsWith(".")) continue;
        const full = path.join(dir, e.name);
        if (e.isDirectory()) {
          walk(full);
        } else if (e.isFile()) {
          if (!CODE_EXTS.has(path.extname(e.name).toLowerCase())) continue;
          try {
            if (fs.statSync(full).size > 512_000) continue;
            const rel = path.relative(rootStr, full) || e.name;
            for (const ch of chunkFile(full)) {
              ch.file = rel;
              chunks.push(ch);
            }
          } catch {
            // ignore
          }
        }
      }
    };

    if (fs.statSync(rootStr).isFile()) {
      for (const ch of chunkFile(rootStr)) {
        ch.file = path.basename(rootStr);
        chunks.push(ch);
      }
    } else {
      walk(rootStr);
    }

    if (!chunks.length) {
      return `No searchable code files found in '${targetPath}'.`;
    }

    const embedModel = (process.env.LOCAI_EMBED_MODEL || "").trim();
    const ollamaHost = process.env.OLLAMA_HOST || "http://localhost:11434";
    let usedBackend = "lexical-bm25";

    if (embedModel && chunks.length <= 200) {
      const qEmb = await ollamaEmbed([query], embedModel, ollamaHost);
      const cEmbs = qEmb ? await ollamaEmbed(chunks.map((c) => c.text), embedModel, ollamaHost) : null;
      if (qEmb && cEmbs) {
        usedBackend = `ollama:${embedModel}`;
        chunks.forEach((c, idx) => {
          c.score = cosine(qEmb[0], cEmbs[idx]);
        });
      }
    }

    if (usedBackend === "lexical-bm25") {
      const qTokens = tokenize(query);
      if (!qTokens.length) return "Error: Query produced no searchable terms.";

      const docTokens = chunks.map((c) => tokenize(`${c.file} ${c.text}`));
      const df = new Map();
      for (const toks of docTokens) {
        for (const t of new Set(toks)) {
          df.set(t, (df.get(t) || 0) + 1);
        }
      }
      const nDocs = chunks.length;
      const avgLen = docTokens.reduce((acc, t) => acc + t.length, 0) / Math.max(nDocs, 1);
      const k1 = 1.5;
      const b = 0.75;

      chunks.forEach((c, idx) => {
        const toks = docTokens[idx];
        const tf = new Map();
        for (const t of toks) tf.set(t, (tf.get(t) || 0) + 1);
        const dl = toks.length;
        let score = 0;
        for (const qt of qTokens) {
          const freq = tf.get(qt) || 0;
          if (!freq) continue;
          const docFreq = df.get(qt) || 0;
          const idf = Math.log(1 + (nDocs - docFreq + 0.5) / (docFreq + 0.5));
          const denom = freq + k1 * (1 - b + b * (dl / Math.max(avgLen, 1)));
          score += idf * ((freq * (k1 + 1)) / Math.max(denom, 1e-9));
        }
        c.score = score;
      });
    }

    const bestPerFile = new Map();
    for (const c of chunks) {
      if ((c.score || 0) <= 0) continue;
      const prev = bestPerFile.get(c.file);
      if (!prev || c.score > prev.score) {
        bestPerFile.set(c.file, c);
      }
    }

    const ranked = Array.from(bestPerFile.values())
      .sort((a, b) => b.score - a.score)
      .slice(0, max_results);

    if (!ranked.length) {
      return `No semantic matches found for '${query}' in '${targetPath}'.`;
    }

    const out = [
      `Semantic search results (${usedBackend}) — read candidate files with 'read_file' before concluding:`,
    ];
    for (const item of ranked) {
      const preview = item.text.split(/\r?\n/).slice(0, 3).join(" ").slice(0, 140);
      out.push(`- ${item.file}:${item.line_start}-${item.line_end} (score=${item.score.toFixed(2)}): ${preview}`);
    }
    return out.join("\n");
  }
}
