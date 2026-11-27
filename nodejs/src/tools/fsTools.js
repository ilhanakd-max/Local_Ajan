import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { getSafePath } from "../safety/sandbox.js";
import {
  checkShellDeleteBypass,
  clearShellDeletesForPath,
  isProtectedWritePath,
} from "../safety/guards.js";

function formatDirEntries(dirPath, limit = 200) {
  const entries = fs.readdirSync(dirPath, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name));
  const lines = entries.slice(0, limit).map((e) => (e.isDirectory() ? `[DIR]  ${e.name}` : `[FILE] ${e.name}`));
  if (entries.length > limit) {
    lines.push(`... (${entries.length - limit} more entries omitted; pass a more specific path)`);
  }
  return lines.join("\n") || "(empty directory)";
}

export class ReadFileTool {
  constructor(workdir = null) {
    this.name = "read_file";
    this.description = "Reads the contents of a file";
    this.requiresConfirm = false;
    this.workdir = workdir;
    this.parameters = {
      type: "object",
      properties: {
        path: { type: "string", description: "Path to the file" },
        start_line: { type: "integer", description: "Optional 1-indexed start line" },
        end_line: { type: "integer", description: "Optional 1-indexed end line" },
      },
      required: ["path"],
    };
  }

  run({ path: targetPath, start_line = null, end_line = null }) {
    let safePath;
    try {
      safePath = getSafePath(targetPath, this.workdir);
    } catch (e) {
      return `Error: ${e.message}`;
    }

    if (!fs.existsSync(safePath)) {
      return `Error: File '${targetPath}' does not exist.`;
    }

    try {
      const stat = fs.statSync(safePath);
      if (stat.isDirectory()) {
        const limit = Number(process.env.LOCAI_READ_DIR_LIMIT || 200);
        const listing = formatDirEntries(safePath, limit);
        return `Note: '${targetPath}' is a directory, not a file. Use 'list_dir' next time.\nDirectory contents:\n${listing}`;
      }

      let content;
      if (path.extname(safePath).toLowerCase() === ".pdf") {
        try {
          content = execFileSync("pdftotext", ["-layout", safePath, "-"], {
            encoding: "utf8",
            maxBuffer: 5 * 1024 * 1024,
          });
        } catch (pdfErr) {
          return `Error reading PDF '${targetPath}': ${pdfErr.message}. Install 'poppler-utils' (pdftotext) to read PDFs.`;
        }
      } else {
        content = fs.readFileSync(safePath, "utf8");
      }
      const lines = content.split(/\r?\n/);
      if (start_line !== null || end_line !== null) {
        const s = Math.max(0, (start_line ?? 1) - 1);
        const e = end_line !== null ? Math.min(lines.length, end_line) : lines.length;
        return lines
          .slice(s, e)
          .map((line, i) => `${s + i + 1}: ${line}`)
          .join("\n");
      }
      return content;
    } catch (err) {
      return `Error reading file '${targetPath}': ${err.message}`;
    }
  }
}

export class WriteFileTool {
  constructor(workdir = null) {
    this.name = "write_file";
    this.description = "Creates a NEW file with content (use edit_file for existing files)";
    this.requiresConfirm = true;
    this.workdir = workdir;
    this.parameters = {
      type: "object",
      properties: {
        path: { type: "string", description: "Path to the new file" },
        content: { type: "string", description: "Full content to write" },
      },
      required: ["path", "content"],
    };
  }

  run({ path: targetPath, content }) {
    let safePath;
    try {
      safePath = getSafePath(targetPath, this.workdir);
    } catch (e) {
      return `Error: ${e.message}`;
    }

    if (isProtectedWritePath(safePath)) {
      return `Error: Writing to protected directory '${targetPath}' is blocked.`;
    }

    const bypassMsg = checkShellDeleteBypass(safePath);
    if (bypassMsg) return bypassMsg;

    if (fs.existsSync(safePath)) {
      return (
        `Error: File '${targetPath}' already exists. ` +
        "Do not overwrite existing files with 'write_file'; use 'edit_file(path, old_str, new_str)' instead."
      );
    }

    try {
      fs.mkdirSync(path.dirname(safePath), { recursive: true });
      fs.writeFileSync(safePath, content, "utf8");
      clearShellDeletesForPath(safePath);
      return `Successfully wrote to '${targetPath}'.`;
    } catch (err) {
      return `Error writing to '${targetPath}': ${err.message}`;
    }
  }
}

export class EditFileTool {
  constructor(workdir = null) {
    this.name = "edit_file";
    this.description = "Replaces an exact string in an existing file";
    this.requiresConfirm = true;
    this.workdir = workdir;
    this.parameters = {
      type: "object",
      properties: {
        path: { type: "string", description: "Path to the existing file" },
        old_str: { type: "string", description: "Exact string to replace" },
        new_str: { type: "string", description: "Replacement string" },
      },
      required: ["path", "old_str", "new_str"],
    };
  }

  run({ path: targetPath, old_str, new_str }) {
    let safePath;
    try {
      safePath = getSafePath(targetPath, this.workdir);
    } catch (e) {
      return `Error: ${e.message}`;
    }

    if (!fs.existsSync(safePath)) {
      return `Error: File '${targetPath}' does not exist.`;
    }

    try {
      const content = fs.readFileSync(safePath, "utf8");
      if (!content.includes(old_str)) {
        return `Error: 'old_str' not found in '${targetPath}'. Read the file first and copy exact text.`;
      }
      const count = content.split(old_str).length - 1;
      if (count > 1) {
        return `Error: 'old_str' matches ${count} locations in '${targetPath}'. Include more surrounding context.`;
      }
      const updated = content.replace(old_str, () => new_str);
      fs.writeFileSync(safePath, updated, "utf8");
      return `Successfully edited '${targetPath}'.`;
    } catch (err) {
      return `Error editing '${targetPath}': ${err.message}`;
    }
  }
}

export class ListDirTool {
  constructor(workdir = null) {
    this.name = "list_dir";
    this.description = "Lists files and directories in a path";
    this.requiresConfirm = false;
    this.workdir = workdir;
    this.parameters = {
      type: "object",
      properties: {
        path: { type: "string", description: "Directory path (default: '.')" },
      },
      required: [],
    };
  }

  run({ path: targetPath = "." } = {}) {
    let safePath;
    try {
      safePath = getSafePath(targetPath, this.workdir);
    } catch (e) {
      return `Error: ${e.message}`;
    }
    if (!fs.existsSync(safePath)) return `Error: Directory '${targetPath}' does not exist.`;
    if (!fs.statSync(safePath).isDirectory()) return `Error: '${targetPath}' is not a directory.`;
    return formatDirEntries(safePath);
  }
}

export class GlobTool {
  constructor(workdir = null) {
    this.name = "glob";
    this.description = "Finds files matching a glob pattern (e.g. '**/*.js')";
    this.requiresConfirm = false;
    this.workdir = workdir;
    this.parameters = {
      type: "object",
      properties: {
        pattern: { type: "string", description: "Glob pattern" },
        path: { type: "string", description: "Base directory (default: '.')" },
      },
      required: ["pattern"],
    };
  }

  run({ pattern, path: targetPath = "." }) {
    let safeBase;
    try {
      safeBase = getSafePath(targetPath, this.workdir);
    } catch (e) {
      return `Error: ${e.message}`;
    }
    try {
      const matches = fs.globSync(pattern, {
        cwd: safeBase,
        exclude: (name) => name === "node_modules" || name === ".git" || name === ".venv",
      });
      if (!matches.length) return `No files matched '${pattern}'.`;
      return matches.slice(0, 100).join("\n");
    } catch (err) {
      return `Error running glob: ${err.message}`;
    }
  }
}

export class GrepTool {
  constructor(workdir = null) {
    this.name = "grep";
    this.description = "Searches for a regex or text pattern across files";
    this.requiresConfirm = false;
    this.workdir = workdir;
    this.parameters = {
      type: "object",
      properties: {
        pattern: { type: "string", description: "Regex or substring to search for" },
        path: { type: "string", description: "Directory or file to search (default: '.')" },
      },
      required: ["pattern"],
    };
  }

  run({ pattern, path: targetPath = "." }) {
    let safePath;
    try {
      safePath = getSafePath(targetPath, this.workdir);
    } catch (e) {
      return `Error: ${e.message}`;
    }

    let regex;
    try {
      regex = new RegExp(pattern, "i");
    } catch (err) {
      return `Error: Invalid regex '${pattern}': ${err.message}`;
    }

    const results = [];
    const walk = (dir) => {
      if (results.length >= 60) return;
      const entries = fs.readdirSync(dir, { withFileTypes: true });
      for (const e of entries) {
        if (results.length >= 60) break;
        if (e.name === ".git" || e.name === "node_modules" || e.name === ".venv" || e.name === "__pycache__") {
          continue;
        }
        const full = path.join(dir, e.name);
        if (e.isDirectory()) {
          walk(full);
        } else if (e.isFile()) {
          try {
            if (fs.statSync(full).size > 512_000) continue;
            const lines = fs.readFileSync(full, "utf8").split(/\r?\n/);
            const rel = path.relative(safePath, full) || e.name;
            for (let i = 0; i < lines.length; i++) {
              if (regex.test(lines[i])) {
                results.push(`${rel}:${i + 1}: ${lines[i].trim().slice(0, 160)}`);
                if (results.length >= 60) break;
              }
            }
          } catch {
            // ignore unreadable binary files
          }
        }
      }
    };

    if (fs.statSync(safePath).isFile()) {
      const lines = fs.readFileSync(safePath, "utf8").split(/\r?\n/);
      for (let i = 0; i < lines.length; i++) {
        if (regex.test(lines[i])) {
          results.push(`${targetPath}:${i + 1}: ${lines[i].trim().slice(0, 160)}`);
        }
      }
    } else {
      walk(safePath);
    }

    return results.length ? results.join("\n") : `No matches found for '${pattern}'.`;
  }
}
