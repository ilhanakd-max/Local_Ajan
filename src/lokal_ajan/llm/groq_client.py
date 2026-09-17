import json
import httpx
from typing import Iterator, Dict, Any, List, Optional


class GroqConnectionError(Exception):
    """Groq API'sine bağlanılamadığında veya API hatası alındığında fırlatılır."""


def chat_stream(
    messages: List[Dict[str, Any]],
    model: str,
    api_key: str,
    options: Optional[Dict[str, Any]] = None,
) -> Iterator[str]:
    """
    Send a chat request to Groq Cloud and stream the response text.
    """
    url = "https://api.groq.com/openai/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    # "groq/openai/gpt-oss-120b" -> "openai/gpt-oss-120b"
    model_id = model.removeprefix("groq/") if model.startswith("groq/") else model
    payload: Dict[str, Any] = {
        "model": model_id,
        "messages": messages,
        "stream": True,
    }
    
    if options:
        if "temperature" in options:
            payload["temperature"] = options["temperature"]
        if "num_ctx" in options:
            payload["max_tokens"] = 4096

    try:
        with httpx.stream("POST", url, headers=headers, json=payload, timeout=None) as response:
            if response.status_code >= 400:
                response.read()
                raise GroqConnectionError(f"Groq API hata döndürdü ({response.status_code}): {response.text[:300]}")
            for line in response.iter_lines():
                if not line:
                    continue
                if line == "data: [DONE]":
                    break
                if line.startswith("data: "):
                    line = line[6:]
                    try:
                        data = json.loads(line)
                        if "choices" in data and len(data["choices"]) > 0:
                            delta = data["choices"][0].get("delta", {})
                            if "content" in delta and delta.get("content"):
                                yield delta["content"]
                    except json.JSONDecodeError:
                        pass
    except httpx.ConnectError as e:
        raise GroqConnectionError(f"Groq API'sine bağlanılamadı. Detay: {e}") from e
    except httpx.HTTPStatusError as e:
        raise GroqConnectionError(f"Groq API hata döndürdü ({e.response.status_code})") from e
