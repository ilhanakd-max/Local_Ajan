import { execSync } from "node:child_process";

export class GitStatusTool {
  constructor(workdir = null) {
    this.name = "git_status";
    this.description = "Shows git status in the repository";
    this.requiresConfirm = false;
    this.workdir = workdir;
    this.parameters = { type: "object", properties: {}, required: [] };
  }

  run() {
    try {
      const out = execSync("git status -sb", {
        cwd: this.workdir || process.cwd(),
        encoding: "utf8",
        stdio: ["ignore", "pipe", "pipe"],
      });
      return out.trim() || "Working tree clean.";
    } catch (err) {
      return `Error running git status: ${err.stderr || err.message}`;
    }
  }
}

export class GitDiffTool {
  constructor(workdir = null) {
    this.name = "git_diff";
    this.description = "Shows git diff (unstaged or staged)";
    this.requiresConfirm = false;
    this.workdir = workdir;
    this.parameters = {
      type: "object",
      properties: {
        staged: { type: "boolean", description: "Show staged diff if true" },
        path: { type: "string", description: "Optional file path" },
      },
      required: [],
    };
  }

  run({ staged = false, path: targetPath = "" } = {}) {
    try {
      const cmd = `git diff${staged ? " --staged" : ""}${targetPath ? ` -- "${targetPath}"` : ""}`;
      const out = execSync(cmd, {
        cwd: this.workdir || process.cwd(),
        encoding: "utf8",
        stdio: ["ignore", "pipe", "pipe"],
      });
      return out.trim() || "(no diff)";
    } catch (err) {
      return `Error running git diff: ${err.stderr || err.message}`;
    }
  }
}
