export async function listOllamaModels(host = "http://localhost:11434") {
  try {
    const res = await fetch(`${host.replace(/\/$/, "")}/api/tags`, {
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data.models) ? data.models.map((m) => m.name) : [];
  } catch {
    return [];
  }
}

export async function* chatStreamOllama({
  model,
  messages,
  host = "http://localhost:11434",
  numCtx = 4096,
  temperature = 0.1,
  repeatPenalty = 1.15,
  think = null,
}) {
  const payload = {
    model,
    messages,
    stream: true,
    options: {
      num_ctx: numCtx,
      temperature,
      repeat_penalty: repeatPenalty,
    },
  };
  if (think !== null) {
    payload.think = think;
  }

  const url = `${host.replace(/\/$/, "")}/api/chat`;
  let res;
  let lastErr;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Connection: "close",
        },
        body: JSON.stringify(payload),
      });
      lastErr = null;
      break;
    } catch (err) {
      lastErr = err;
      if (attempt < 2) {
        await new Promise((r) => setTimeout(r, 350 * (attempt + 1)));
      }
    }
  }
  if (lastErr) {
    const detail = lastErr?.cause?.code || lastErr?.cause?.message || lastErr?.message || String(lastErr);
    throw new Error(`Ollama bağlantı hatası (${url}): ${detail}`);
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Ollama API hatası (${res.status}): ${text || res.statusText}`);
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
      if (!trimmed) continue;
      try {
        const obj = JSON.parse(trimmed);
        const content = obj?.message?.content;
        if (content) yield content;
      } catch {
        // ignore partial JSON line
      }
    }
  }
  if (buffer.trim()) {
    try {
      const obj = JSON.parse(buffer.trim());
      if (obj?.message?.content) yield obj.message.content;
    } catch {
      // ignore
    }
  }
}
