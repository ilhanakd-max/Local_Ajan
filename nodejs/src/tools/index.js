import { registry } from "./registry.js";
import {
  ReadFileTool,
  WriteFileTool,
  EditFileTool,
  ListDirTool,
  GlobTool,
  GrepTool,
} from "./fsTools.js";
import { RunShellTool } from "./shellTool.js";
import { GitStatusTool, GitDiffTool } from "./gitTools.js";
import { ReportFindingTool } from "./claimTools.js";
import { SemanticCodeSearchTool } from "./semanticSearchTool.js";

export function registerDefaultTools(workdir = null) {
  registry.register(new ReadFileTool(workdir));
  registry.register(new WriteFileTool(workdir));
  registry.register(new EditFileTool(workdir));
  registry.register(new ListDirTool(workdir));
  registry.register(new GlobTool(workdir));
  registry.register(new GrepTool(workdir));
  registry.register(new RunShellTool(workdir));
  registry.register(new GitStatusTool(workdir));
  registry.register(new GitDiffTool(workdir));
  registry.register(new ReportFindingTool(workdir));
  registry.register(new SemanticCodeSearchTool(workdir));
}

registerDefaultTools();

export { registry };
