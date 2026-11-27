import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { getSafePath } from "../safety/sandbox.js";

export function getClaimMemoryPath() {
  return process.env.LOCAI_CLAIM_MEMORY || path.join(os.homedir(), ".lokal_ajan", "claim_memory.json");
}

export function loadClaimMemory() {
  const memPath = getClaimMemoryPath();
  if (!fs.existsSync(memPath)) return [];
  try {
    const data = JSON.parse(fs.readFileSync(memPath, "utf8"));
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

export function saveRefutedClaim(entry) {
  const memPath = getClaimMemoryPath();
  fs.mkdirSync(path.dirname(memPath), { recursive: true });
  let items = loadClaimMemory();
  items = items.filter((it) => !(it.title === entry.title && it.file_path === entry.file_path));
  items.push(entry);
  fs.writeFileSync(memPath, JSON.stringify(items.slice(-50), null, 2), "utf8");
}

export function formatClaimMemoryForPrompt() {
  const items = loadClaimMemory();
  if (!items.length) return "";
  const lines = ["PREVIOUSLY REFUTED CLAIMS (do not repeat these false positives):"];
  for (const it of items.slice(-10)) {
    lines.push(`- ${it.title} (${it.file_path}): ${it.refuted_by}`);
  }
  return lines.join("\n");
}

export class ReportFindingTool {
  constructor(workdir = null) {
    this.name = "report_finding";
    this.description =
      "Reports a verified code review or bug finding with mandatory source quote, trace, and refutation check";
    this.requiresConfirm = false;
    this.workdir = workdir;
    this.parameters = {
      type: "object",
      properties: {
        title: { type: "string", description: "Short title of the bug or finding" },
        file_path: { type: "string", description: "Path to the cited source file" },
        line_start: { type: "integer", description: "1-indexed starting line number" },
        quoted_source: { type: "string", description: "Exact verbatim source lines from file_path" },
        failure_scenario: { type: "string", description: "Concrete failing input and step-by-step trace" },
        refutation_attempt: { type: "string", description: "Where you checked for a guard preventing this" },
        refuted_by: { type: "string", description: "If a defeating guard was found, describe it here" },
        confidence: { type: "string", enum: ["confirmed", "likely", "unverified"] },
        severity: { type: "string", enum: ["high", "medium", "low", "none"] },
        verified_by: { type: "string", description: "Command executed to verify runtime behavior" },
      },
      required: ["title", "file_path", "line_start", "quoted_source", "failure_scenario", "refutation_attempt", "confidence"],
    };
  }

  run({
    title,
    file_path,
    line_start,
    quoted_source,
    failure_scenario,
    refutation_attempt,
    confidence,
    severity = "none",
    refuted_by = null,
    verified_by = null,
  }) {
    let resolved;
    try {
      resolved = getSafePath(file_path, this.workdir);
    } catch (e) {
      return `Error: ${e.message}`;
    }

    if (!fs.existsSync(resolved) || !fs.statSync(resolved).isFile()) {
      return `Error: Cited file '${file_path}' does not exist.`;
    }

    const content = fs.readFileSync(resolved, "utf8");
    const normContent = content.split(/\s+/).join(" ");
    const normQuote = String(quoted_source || "").split(/\s+/).join(" ").trim();
    if (!normQuote || !normContent.includes(normQuote)) {
      return (
        `Error: quoted_source was not found verbatim in '${file_path}'. ` +
        "Read the file with 'read_file' and quote the exact source lines."
      );
    }

    if (!refutation_attempt || refutation_attempt.trim().length < 10) {
      return "Error: refutation_attempt must describe where you looked for a guard that prevents the bug.";
    }

    if (refuted_by && refuted_by.trim()) {
      const lower = refuted_by.toLowerCase();
      if (lower.includes("comment says") || lower.includes("docstring says")) {
        return "Error: A comment or docstring is not a valid refutation; verify against actual code.";
      }
      saveRefutedClaim({
        title: title.trim(),
        file_path,
        line_start,
        refuted_by: refuted_by.trim(),
      });
      return `Finding DISPROVED and recorded in claim memory (dropped): ${title}`;
    }

    if (confidence === "unverified" && severity !== "none") {
      return "Error: unverified findings cannot carry a severity; set severity='none'.";
    }

    if (confidence === "confirmed" && String(failure_scenario || "").trim().length < 20) {
      return "Error: 'confirmed' findings require a concrete step-by-step failure_scenario.";
    }

    const verNote = verified_by ? ` | verified_by: ${verified_by}` : "";
    return `Finding RECORDED [${confidence.toUpperCase()} | severity=${severity}]: ${title} (${file_path}:${line_start})${verNote}`;
  }
}
