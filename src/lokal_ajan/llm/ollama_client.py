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



def preload_model(model: str, host: str = "http://localhost:11434") -> bool:
    """
    Modeli RAM'e önceden yükler (warmup).
    Böylece ilk kullanıcı mesajında 'cold start' gecikmesi ve timeout yaşanmaz.
    Ollama resmi API: boş prompt ile /api/generate çağrısı.
    """
    url = f"{host.rstrip('/')}/api/generate"
    try:
        resp = httpx.post(
            url,
            json={"model": model, "prompt": "", "keep_alive": "30m"},
            timeout=httpx.Timeout(300.0, connect=5.0)
        )
        return resp.status_code == 200
    except Exception:
        return False


def chat_stream(
    messages: List[Dict[str, Any]],
    model: str,
    host: str = "http://localhost:11434",
    options: Optional[Dict[str, Any]] = None,
    think: Optional[bool] = None,
    keep_alive: Optional[str] = "30m",
    timeout: Optional[float] = None,
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

    # Yerel modellerde (özellikle CPU'da çalışan 7B+ büyük modellerde) diskten
    # yüklenme, KV cache tahsisi ve ilk prompt değerlendirmesi (prefill) uzun sürebilir.
    # Bağlantı için 15-30s yeterliyken, veri okuma/yazma için katı sınır koymamak gerekir.
    # timeout=None → sonsuz bekleme (OS soket timeout'una kadar).
    _read = timeout  # None ise sonsuz bekleme
    stream_timeout = httpx.Timeout(connect=30.0, read=_read, write=_read, pool=_read)
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
    except OllamaConnectionError:
        raise  # _iter_chat_lines'dan gelen sarmalanmış hataları aynen ilet
    except httpx.ConnectError as e:
        raise OllamaConnectionError(
            f"Ollama'ya bağlanılamadı ({host}). Ollama çalışıyor mu? "
            f"('ollama serve' ile başlatabilirsiniz.) Detay: {e}"
        ) from e
    except (TimeoutError, httpx.TimeoutException) as e:
        raise OllamaConnectionError(
            f"Ollama yanıt vermedi (zaman aşımı / timed out). "
            f"'{model}' modeli diskten belleğe yüklenirken veya yanıt üretirken gecikti. "
            f"Büyük modeller CPU üzerinde çalışırken ilk yüklemede uzun sürebilir. "
            f"Detay: {e}"
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
    except Exception as e:
        raise OllamaConnectionError(f"Ollama bağlantı hatası: {e}") from e



def _iter_chat_lines(response: httpx.Response) -> Iterator[str]:
    try:
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
    except OllamaConnectionError:
        raise  # Zaten sarmalanmış, tekrar sarmalama
    except (TimeoutError, httpx.TimeoutException) as e:
        raise OllamaConnectionError(
            f"Ollama yanıt akışı sırasında zaman aşımı oluştu (timed out): {e}"
        ) from e
    except Exception as e:
        raise OllamaConnectionError(f"Ollama stream okuma hatası: {e}") from e


def chat_once(
    messages: List[Dict[str, Any]],
    model: str,
    host: str = "http://localhost:11434",
    options: Optional[Dict[str, Any]] = None,
    think: Optional[bool] = None,
    timeout: Optional[float] = None,
) -> str:
    """Streaming olmayan, tüm yanıtı biriktirip tek seferde döndüren yardımcı.
    Örn. kısa doğrulama/özetleme çağrıları için kullanılabilir."""
    return "".join(chat_stream(messages, model, host, options, think, timeout=timeout))
