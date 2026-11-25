const PROVIDERS = {
  "openrouter/": {
    baseUrl: "https://openrouter.ai/api/v1",
    envKey: "OPENROUTER_API_KEY",
    extraHeaders: { "HTTP-Referer": "https://github.com/ilhanakd-max/Local_Ajan", "X-Title": "LocAi-JS" },
  },
  "groq/": {
    baseUrl: "https://api.groq.com/openai/v1",
    envKey: "GROQ_API_KEY",
    extraHeaders: {},
  },
  "ninerouter/": {
    baseUrl: "http://localhost:20128/v1",
    envKey: "NINEROUTER_API_KEY",
    extraHeaders: {},
  },
  "nvidia/": {
    baseUrl: "https://integrate.api.nvidia.com/v1",
    envKey: "NVIDIA_API_KEY",
    extraHeaders: {},
  },
};

export function resolveProvider(modelName, config = {}) {
  for (const [prefix, info] of Object.entries(PROVIDERS)) {
    if (modelName.startsWith(prefix)) {
      const apiModel = modelName.slice(prefix.length);
      let baseUrl = info.baseUrl;
      let apiKey = process.env[info.envKey] || "";
      if (prefix === "openrouter/") apiKey = apiKey || config.openrouter_api_key || "";
      if (prefix === "groq/") apiKey = apiKey || config.groq_api_key || "";
      if (prefix === "ninerouter/") {
        baseUrl = config.ninerouter_host || baseUrl;
        apiKey = apiKey || config.ninerouter_api_key || "ninerouter";
      }
      if (prefix === "nvidia/") apiKey = apiKey || config.nvidia_api_key || "";
      return { prefix, apiModel, baseUrl, apiKey, extraHeaders: info.extraHeaders };
    }
  }
  return null;
}

export async function* chatStreamOpenAICompat({
  model,
  messages,
  config = {},
  temperature = 0.1,
}) {
  const prov = resolveProvider(model, config);
  if (!prov) throw new Error(`Bilinmeyen bulut sağlayıcı öneki: ${model}`);
  if (!prov.apiKey && prov.prefix !== "ninerouter/") {
    throw new Error(`${prov.prefix} için API anahtarı eksik.`);
  }

  const headers = {
    "Content-Type": "application/json",
    ...(prov.apiKey ? { Authorization: `Bearer ${prov.apiKey}` } : {}),
    ...prov.extraHeaders,
  };

  const res = await fetch(`${prov.baseUrl.replace(/\/$/, "")}/chat/completions`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      model: prov.apiModel,
      messages,
      temperature,
      stream: true,
    }),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API Hatası (${res.status}): ${text || res.statusText}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data:")) continue;
      const dataStr = trimmed.slice(5).trim();
      if (dataStr === "[DONE]") return;
      try {
        const obj = JSON.parse(dataStr);
        const delta = obj?.choices?.[0]?.delta?.content;
        if (delta) yield delta;
      } catch {
        // ignore malformed chunk
      }
    }
  }
}
