import { execSync } from "node:child_process";
import { isDangerousShellCommand } from "../safety/sandbox.js";
import { recordShellDelete } from "../safety/guards.js";

export class RunShellTool {
  constructor(workdir = null, timeoutSeconds = 120) {
    this.name = "run_shell";
    this.description = "Runs a non-interactive shell command in the workspace";
    this.requiresConfirm = true;
    this.workdir = workdir;
    this.timeoutSeconds = timeoutSeconds;
    this.parameters = {
      type: "object",
      properties: {
        command: { type: "string", description: "Shell command to execute" },
      },
      required: ["command"],
    };
  }

  run({ command }) {
    if (!command || !String(command).trim()) {
      return "Error: Empty shell command.";
    }
    if (isDangerousShellCommand(command)) {
      return `Error: Blocked dangerous shell command: '${command}'`;
    }

    const cwd = this.workdir || process.cwd();
    recordShellDelete(command, cwd);

    try {
      const stdout = execSync(command, {
        cwd,
        timeout: this.timeoutSeconds * 1000,
        encoding: "utf8",
        stdio: ["ignore", "pipe", "pipe"],
      });
      return stdout.trim() || "(command completed with no output)";
    } catch (err) {
      const out = [err.stdout, err.stderr].filter(Boolean).join("\n").trim();
      return `Command exited with code ${err.status ?? 1}:\n${out || err.message}`;
    }
  }
}
