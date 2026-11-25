export class ToolRegistry {
  constructor() {
    this._tools = new Map();
  }

  register(tool) {
    this._tools.set(tool.name, tool);
  }

  get(name) {
    return this._tools.get(name) || null;
  }

  getAllTools() {
    return Array.from(this._tools.values());
  }

  setWorkdir(workdir) {
    for (const tool of this._tools.values()) {
      if ("workdir" in tool) {
        tool.workdir = workdir;
      }
    }
  }

  getToolsSchema() {
    return this.getAllTools().map((t) => ({
      name: t.name,
      description: t.description,
      parameters: t.parameters || { type: "object", properties: {}, required: [] },
    }));
  }
}

export const registry = new ToolRegistry();
