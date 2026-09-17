import json
import httpx
from typing import Iterator, Dict, Any, List, Optional


class OllamaConnectionError(Exception):
    """Ollama'ya ulaşılamadığında (kapalı, yanlış host, vb.) fırlatılır."""


def list_ollama_models(host: str = "http://localhost:11434") -> List[str]:
    """
    Fetch the list of locally installed Ollama models.
    """
    url = f"{host.rstrip('/')}/api/tags"
    try:
        response = httpx.get(url, timeout=5.0)
        response.raise_for_status()
        data = response.json()
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def free_unused_models(active_model: str, worker_model: Optional[str] = None, host: str = "http://localhost:11434"):
    """
    Checks currently running Ollama models via /api/ps.
    If there are models loaded in RAM other than the active model (and worker_model),
    it terminates them to free up RAM using `ollama stop` and API fallback.
    """
    url = f"{host.rstrip('/')}/api/ps"
    try:
        response = httpx.get(url, timeout=3.0)
        if response.status_code == 200:
            data = response.json()
            running_models = [m.get("name") for m in data.get("models", []) if m.get("name")]
            
            allowed = {active_model}
            if worker_model:
                allowed.add(worker_model)
                
            for rm in running_models:
                if rm not in allowed:
                    # Unload model from RAM
                    try:
                        # 1. Fallback / Standard API way (works on remote hosts too)
                        httpx.post(
                            f"{host.rstrip('/')}/api/chat",
                            json={"model": rm, "messages": [], "keep_alive": 0},
                            timeout=2.0
                        )
                    except Exception:
                        pass
                    
                    try:
                        # 2. Local CLI command way as requested
                        import subprocess
                        subprocess.run(["ollama", "stop", rm], capture_output=True, check=False)
                    except Exception:
                        pass
    except Exception:
        pass



def chat_stream(
    messages: List[Dict[str, Any]],
    model: str,
    host: str = "http://localhost:11434",
    options: Optional[Dict[str, Any]] = None,
    think: Optional[bool] = None,
    keep_alive: Optional[str] = "5m",
) -> Iterator[str]:
    """
    Send a chat request to Ollama and stream the response text.

    think: Qwen3 gibi hibrit-düşünme modellerini destekleyen Ollama
        sürümlerinde thinking modunu açıp kapatır (bkz. model_profiles.py
        `supports_think_control`). Bu alanı desteklemeyen modeller ekstra
        bir alanı sessizce yok sayar; None verilirse hiç gönderilmez.
    """
    url = f"{host.rstrip('/')}/api/chat"

    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
    }

    if options:
        payload["options"] = options
    if think is not None:
        payload["think"] = think
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive

    # Use generous timeout for local models (allow 120s between chunks for slow CPU inference)
    stream_timeout = httpx.Timeout(300.0, connect=10.0, read=120.0)
    try:
        with httpx.stream("POST", url, json=payload, timeout=stream_timeout) as response:
            if response.status_code >= 400:
                # Ollama, bilinmeyen bir alan (ör. modelin desteklemediği
                # "think") gönderildiğinde bazı sürümlerde 400 dönebilir.
                # "think" alanını çıkarıp bir kez daha deneriz.
                if "think" in payload:
                    payload.pop("think", None)
                    with httpx.stream("POST", url, json=payload, timeout=stream_timeout) as retry_resp:
                        if retry_resp.status_code >= 400:
                            try:
                                retry_resp.read()
                            except Exception:
                                pass
                            retry_resp.raise_for_status()
                        yield from _iter_chat_lines(retry_resp)
                        return
                try:
                    response.read()
                except Exception:
                    pass
                response.raise_for_status()
            yield from _iter_chat_lines(response)
    except httpx.ConnectError as e:
        raise OllamaConnectionError(
            f"Ollama'ya bağlanılamadı ({host}). Ollama çalışıyor mu? "
            f"('ollama serve' ile başlatabilirsiniz.) Detay: {e}"
        ) from e
    except httpx.HTTPStatusError as e:
        error_text = ""
        try:
            e.response.read()
            error_text = e.response.text[:300]
        except Exception:
            pass
        raise OllamaConnectionError(
            f"Ollama hata döndürdü ({e.response.status_code}): {error_text}"
        ) from e


def _iter_chat_lines(response: httpx.Response) -> Iterator[str]:
    for line in response.iter_lines():
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "error" in data:
            raise OllamaConnectionError(str(data["error"]))
        if "message" in data and "content" in data["message"]:
            content = data["message"]["content"]
            if content:
                yield content
        if data.get("done"):
            break


def chat_once(
    messages: List[Dict[str, Any]],
    model: str,
    host: str = "http://localhost:11434",
    options: Optional[Dict[str, Any]] = None,
    think: Optional[bool] = None,
) -> str:
    """Streaming olmayan, tüm yanıtı biriktirip tek seferde döndüren yardımcı.
    Örn. kısa doğrulama/özetleme çağrıları için kullanılabilir."""
    return "".join(chat_stream(messages, model, host, options, think))
