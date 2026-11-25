export class ChatHistory {
  constructor(systemPrompt) {
    this.messages = [{ role: "system", content: systemPrompt }];
  }

  updateSystemPrompt(newPrompt) {
    if (this.messages.length && this.messages[0].role === "system") {
      this.messages[0].content = newPrompt;
    } else {
      this.messages.unshift({ role: "system", content: newPrompt });
    }
  }

  addUser(content) {
    this.messages.push({ role: "user", content });
  }

  addAssistant(content) {
    this.messages.push({ role: "assistant", content });
  }

  addToolResult(toolName, result) {
    this.messages.push({
      role: "user",
      content: `Tool Result (${toolName}):\n${result}`,
    });
  }

  getMessages() {
    return this.messages;
  }

  clear() {
    const sys = this.messages.find((m) => m.role === "system");
    this.messages = sys ? [sys] : [];
  }
}
