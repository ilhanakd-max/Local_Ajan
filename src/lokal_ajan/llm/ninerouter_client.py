import json
import httpx
from typing import Iterator, Dict, Any, List, Optional

class NineRouterConnectionError(Exception):
    """9router'a bağlanılamadığında veya API hatası alındığında fırlatılır."""

def chat_stream(
    messages: List[Dict[str, Any]],
    model: str,
    api_key: str,
    host: str,
    options: Optional[Dict[str, Any]] = None,
) -> Iterator[str]:
    """
    Send a chat request to 9router (OpenAI compatible) and stream the response text.
    """
    # model parameter will come as "ninerouter/free-model", strip the prefix
    if model.startswith("ninerouter/"):
        model = model.replace("ninerouter/", "", 1)

    url = f"{host.rstrip('/')}/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
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
        raise NineRouterConnectionError(f"9router'a bağlanılamadı. Detay: {e}") from e
    except httpx.HTTPStatusError as e:
        error_text = ""
        try:
            e.response.read()
            error_text = e.response.text[:300]
        except Exception:
            pass
        raise NineRouterConnectionError(f"9router hata döndürdü ({e.response.status_code}): {error_text}") from e
