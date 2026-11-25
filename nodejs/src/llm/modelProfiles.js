const PROFILES = [
  { name_pattern: /^groq\//i, num_ctx: 32768, temperature: 0.1, native_tool_call: true, prompt_level: "standard", max_tool_output: 30000, supports_think_control: false, disable_thinking: true, repeat_penalty: 1.1, parse_retry_limit: 2 },
  { name_pattern: /^openrouter\//i, num_ctx: 32768, temperature: 0.1, native_tool_call: true, prompt_level: "standard", max_tool_output: 30000, supports_think_control: false, disable_thinking: true, repeat_penalty: 1.1, parse_retry_limit: 2 },
  { name_pattern: /^ninerouter\//i, num_ctx: 8192, temperature: 0.1, native_tool_call: true, prompt_level: "standard", max_tool_output: 15000, supports_think_control: false, disable_thinking: true, repeat_penalty: 1.1, parse_retry_limit: 2 },
  { name_pattern: /^nvidia\//i, num_ctx: 32768, temperature: 0.1, native_tool_call: true, prompt_level: "standard", max_tool_output: 30000, supports_think_control: false, disable_thinking: true, repeat_penalty: 1.1, parse_retry_limit: 2 },
  { name_pattern: /qwen3(?:\.\d+)?[.:\-]?\s*0\.[5-9]b/i, num_ctx: 4096, temperature: 0.15, native_tool_call: false, prompt_level: "minimal", max_tool_output: 4000, supports_think_control: true, disable_thinking: true, repeat_penalty: 1.2, parse_retry_limit: 3 },
  { name_pattern: /qwen3(?:\.\d+)?[.:\-]?\s*1\.[5-9]b/i, num_ctx: 8192, temperature: 0.15, native_tool_call: false, prompt_level: "minimal", max_tool_output: 8000, supports_think_control: true, disable_thinking: true, repeat_penalty: 1.15, parse_retry_limit: 3 },
  { name_pattern: /qwen3(?:\.\d+)?[.:\-]?\s*(?:2|3)(?:\.\d+)?b/i, num_ctx: 8192, temperature: 0.15, native_tool_call: false, prompt_level: "minimal", max_tool_output: 8000, supports_think_control: true, disable_thinking: true, repeat_penalty: 1.15, parse_retry_limit: 3 },
  { name_pattern: /qwen3(?:\.\d+)?[.:\-]?\s*4b/i, num_ctx: 16384, temperature: 0.2, native_tool_call: true, prompt_level: "minimal", max_tool_output: 20000, supports_think_control: true, disable_thinking: true, repeat_penalty: 1.1, parse_retry_limit: 2 },
  { name_pattern: /qwen3(?:\.\d+)?[.:\-]?\s*(?:8|14|32)b/i, num_ctx: 32768, temperature: 0.2, native_tool_call: true, prompt_level: "standard", max_tool_output: 35000, supports_think_control: true, disable_thinking: true, repeat_penalty: 1.1, parse_retry_limit: 2 },
  { name_pattern: /qwen3(?:\.\d+)?/i, num_ctx: 16384, temperature: 0.2, native_tool_call: true, prompt_level: "standard", max_tool_output: 20000, supports_think_control: true, disable_thinking: true, repeat_penalty: 1.1, parse_retry_limit: 2 },
  { name_pattern: /qwen2\.5.*(?:0\.5|1\.5|3)b/i, num_ctx: 4096, temperature: 0.1, native_tool_call: false, prompt_level: "minimal", max_tool_output: 4000, supports_think_control: false, disable_thinking: true, repeat_penalty: 1.15, parse_retry_limit: 3 },
  { name_pattern: /qwen2\.5/i, num_ctx: 16384, temperature: 0.15, native_tool_call: true, prompt_level: "standard", max_tool_output: 20000, supports_think_control: false, disable_thinking: true, repeat_penalty: 1.1, parse_retry_limit: 2 },
  { name_pattern: /deepseek-r1/i, num_ctx: 16384, temperature: 0.2, native_tool_call: false, prompt_level: "standard", max_tool_output: 15000, supports_think_control: false, disable_thinking: false, repeat_penalty: 1.1, parse_retry_limit: 2 },
  { name_pattern: /llama3\.[1-3]|gemma|phi|mistral|codellama/i, num_ctx: 8192, temperature: 0.15, native_tool_call: false, prompt_level: "standard", max_tool_output: 10000, supports_think_control: false, disable_thinking: true, repeat_penalty: 1.15, parse_retry_limit: 2 },
];

function extractSizeB(modelName) {
  const m = /(\d+(?:\.\d+)?)\s*b\b/i.exec(modelName);
  return m ? Number(m[1]) : null;
}

export function getProfileForModel(modelName) {
  for (const profile of PROFILES) {
    if (profile.name_pattern.test(modelName)) {
      return { ...profile };
    }
  }
  const sizeB = extractSizeB(modelName);
  if (sizeB !== null && sizeB <= 3.5) {
    return {
      name_pattern: "fallback-small",
      num_ctx: 4096,
      temperature: 0.15,
      native_tool_call: false,
      prompt_level: "minimal",
      max_tool_output: 4000,
      supports_think_control: false,
      disable_thinking: true,
      repeat_penalty: 1.2,
      parse_retry_limit: 3,
    };
  }
  return {
    name_pattern: "fallback-standard",
    num_ctx: 8192,
    temperature: 0.15,
    native_tool_call: false,
    prompt_level: "standard",
    max_tool_output: 12000,
    supports_think_control: false,
    disable_thinking: true,
    repeat_penalty: 1.15,
    parse_retry_limit: 2,
  };
}
