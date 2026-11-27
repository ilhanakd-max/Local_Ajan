import { registry } from "../tools/index.js";
import { formatClaimMemoryForPrompt } from "../tools/claimTools.js";

const PONYTAIL_DIRECTIVE = `
PONYTAIL MODE ACTIVE (Minimalism & Zero Over-Engineering):
1. Do the simplest thing that actually works. Prefer 1-15 lines over 100 lines.
2. YAGNI: Do not add abstractions, factories, or configuration not requested.
3. Reuse built-in Node.js APIs and existing helpers before adding dependencies.
`;

export function getSystemPrompt({
  promptLevel = "standard",
  orchestratorMode = false,
  workerModel = null,
  ponytailMode = false,
} = {}) {
  const tools = registry.getToolsSchema();
  const toolLines = tools
    .map((t) => {
      const params = Object.keys(t.parameters?.properties || {}).join(", ");
      return `- ${t.name}(${params}): ${t.description}`;
    })
    .join("\n");

  const claimMemory = promptLevel !== "minimal" ? formatClaimMemoryForPrompt() : "";
  const ponytailBlock = ponytailMode ? PONYTAIL_DIRECTIVE : "";

  if (promptLevel === "minimal") {
    return [
      "You are LocAi, a fast, accurate local coding assistant.",
      "",
      "CORE RULES:",
      "- LOCAL FILE ACCESS: You DO have direct access to local workspace files via read_file, list_dir, glob, and grep. NEVER say you lack access to local files; call read_file immediately on any path the user shares.",
      "- WORKSPACE DISCOVERY: Explore with list_dir / glob / grep / semantic_code_search before assuming paths.",
      "- EDIT OVER WRITE: Use write_file ONLY for new files. Use edit_file for existing files.",
      "- CLAIM VERIFICATION: Never claim a bug or behavior without reading the file first. Use report_finding for code-review findings.",
      "- ONLY report exact file paths, outputs, and test results you directly observed.",
      "",
      "AVAILABLE TOOLS:",
      toolLines,
      "",
      "TOOL CALL FORMAT:",
      "<tool_call>",
      '{"name": "tool_name", "arguments": {"arg1": "value"}}',
      "</tool_call>",
      ponytailBlock,
    ]
      .filter(Boolean)
      .join("\n");
  }

  const orchBlock = orchestratorMode
    ? `\nORCHESTRATOR MODE: You may delegate isolated subtasks using delegate_task(task_description, context_files) to worker model '${workerModel || "local"}'.\n`
    : "";

  return [
    "You are LocAi, a privacy-first local AI coding agent running in Node.js.",
    "",
    "OPERATING DISCIPLINES:",
    "0. LOCAL FILE ACCESS: You DO have direct access to the user's local workspace files via read_file, list_dir, glob, and grep. NEVER claim you cannot access local files or directories. Whenever the user shares or mentions a file path, read it immediately with read_file.",
    "1. WORKSPACE DISCOVERY: Never guess file paths. Inspect with list_dir, glob, grep, or semantic_code_search first.",
    "2. EDIT OVER WRITE: Use write_file ONLY to create brand-new files. Always use edit_file for existing files.",
    "3. CLAIM VERIFICATION: Read files before making claims. For code reviews or bug reports, use report_finding with exact quoted_source and refutation checks.",
    "4. EVIDENCE ONLY: Never fabricate file paths, symbol names, or command outputs. Verify changes by running tests or commands with run_shell.",
    orchBlock,
    claimMemory,
    "",
    "AVAILABLE TOOLS:",
    toolLines,
    "",
    "TOOL CALL FORMAT:",
    "When you need a tool, respond with:",
    "<tool_call>",
    '{"name": "tool_name", "arguments": {"arg1": "value"}}',
    "</tool_call>",
    ponytailBlock,
  ]
    .filter(Boolean)
    .join("\n");
}
