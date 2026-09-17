import json
import httpx
from typing import Iterator, Dict, Any, List, Optional


class OpenRouterConnectionError(Exception):
    """OpenRouter'a bağlanılamadığında veya API hatası alındığında fırlatılır."""


def chat_stream(
    messages: List[Dict[str, Any]],
    model: str,
    api_key: str,
    options: Optional[Dict[str, Any]] = None,
) -> Iterator[str]:
    """
    Send a chat request to OpenRouter and stream the response text.
    """
    url = "https://openrouter.ai/api/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/lokal-ajan/lokal-ajan",
        "X-Title": "Lokal Ajan",
    }
    
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    
    if options:
        if "temperature" in options:
            payload["temperature"] = options["temperature"]
        if "num_ctx" in options:
            payload["max_tokens"] = 4096 # Provide a reasonable max_tokens for completions

    try:
        with httpx.stream("POST", url, headers=headers, json=payload, timeout=None) as response:
            response.raise_for_status()
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
        raise OpenRouterConnectionError(f"OpenRouter'a bağlanılamadı. Detay: {e}") from e
    except httpx.HTTPStatusError as e:
        error_text = ""
        try:
            e.response.read()
            error_text = e.response.text[:300]
        except Exception:
            pass
        raise OpenRouterConnectionError(f"OpenRouter hata döndürdü ({e.response.status_code}): {error_text}") from e

