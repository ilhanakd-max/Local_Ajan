import time
import json
import httpx
from typing import Iterator, Dict, Any, List, Optional


class OpenRouterConnectionError(Exception):
    """OpenRouter'a bağlanılamadığında veya API hatası alındığında fırlatılır."""


FREE_FALLBACK_MODELS = [
    "poolside/laguna-s-2.1:free",
    "cohere/command-r:free",
    "openrouter/free",
]


def chat_stream(
    messages: List[Dict[str, Any]],
    model: str,
    api_key: str,
    options: Optional[Dict[str, Any]] = None,
) -> Iterator[str]:
    """
    Send a chat request to OpenRouter and stream the response text.
    Handles fallbacks for free models, reasoning tokens, and SSE errors.
    """
    url = "https://openrouter.ai/api/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/lokal-ajan/lokal-ajan",
        "X-Title": "LocAi",
    }
    
    payload: Dict[str, Any] = {
        "messages": messages,
        "stream": True,
    }
    
    # openrouter/free meta-router can route to content-safety or broken models.
    # OpenRouter supports up to 3 fallback models in the 'models' parameter.
    if model == "openrouter/free":
        payload["models"] = FREE_FALLBACK_MODELS
    else:
        model_id = model.removeprefix("openrouter/") if model.startswith("openrouter/") else model
        payload["model"] = model_id
    
    if options:
        if "temperature" in options:
            payload["temperature"] = options["temperature"]
        if "num_ctx" in options:
            # num_ctx is the total context window size; cap max_tokens for completions safely
            payload["max_tokens"] = min(4096, options["num_ctx"])

    max_retries = 3
    for attempt in range(max_retries):
        try:
            with httpx.stream("POST", url, headers=headers, json=payload, timeout=None) as response:
                if response.status_code >= 400:
                    response.read()
                    if response.status_code in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    raise OpenRouterConnectionError(f"OpenRouter hata döndürdü ({response.status_code}): {response.text[:300]}")
                
                in_reasoning = False
                for line in response.iter_lines():
                    if not line:
                        continue
                    if line == "data: [DONE]":
                        break
                    if line.startswith("data: "):
                        line = line[6:]
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        # Check for mid-stream error payloads
                        if "error" in data:
                            # Instead of raising and losing all generated content, just gracefully stop.
                            # The model may have already output a valid tool call.
                            return

                        choices = data.get("choices")
                        if choices and len(choices) > 0:
                            choice = choices[0]
                            if choice.get("finish_reason") == "error":
                                return

                            delta = choice.get("delta", {})
                            
                            # Stream reasoning if provided (wrapped in <think> tags for thinking filter)
                            reasoning = delta.get("reasoning") or delta.get("reasoning_content")
                            if reasoning:
                                if not in_reasoning:
                                    yield "<think>"
                                    in_reasoning = True
                                yield reasoning

                            content = delta.get("content")
                            if content:
                                if in_reasoning:
                                    yield "</think>"
                                    in_reasoning = False
                                yield content

                if in_reasoning:
                    yield "</think>"

                return
        except httpx.ConnectError as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise OpenRouterConnectionError(f"OpenRouter'a bağlanılamadı. Detay: {e}") from e
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            error_text = ""
            try:
                e.response.read()
                error_text = e.response.text[:300]
            except Exception:
                pass
            raise OpenRouterConnectionError(f"OpenRouter hata döndürdü ({e.response.status_code}): {error_text}") from e

