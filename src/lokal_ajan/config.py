import os
from typing import Optional
from pathlib import Path
from pydantic import BaseModel

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    tomllib = None

CONFIG_PATH = Path(os.environ.get(
    "LOKAL_AJAN_CONFIG",
    Path.home() / ".config" / "lokal-ajan" / "config.toml",
))

STATE_PATH = Path(os.environ.get(
    "LOKAL_AJAN_STATE",
    Path.home() / ".config" / "lokal-ajan" / "state.json",
))


def load_state(path: Path = None) -> dict:
    state_file = path or STATE_PATH
    if not state_file.is_file():
        return {}
    try:
        import json
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state: dict, path: Path = None):
    state_file = path or STATE_PATH
    try:
        import json
        state_file.parent.mkdir(parents=True, exist_ok=True)
        current = load_state(state_file)
        current.update(state)
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


class Config(BaseModel):
    default_model: str = "qwen3:1.7b"
    ollama_host: str = "http://localhost:11434"
    ollama_timeout: Optional[float] = None
    openrouter_api_key: str = os.environ.get("OPENROUTER_API_KEY", "")
    groq_api_key: str = os.environ.get("GROQ_API_KEY", "")
    ninerouter_host: str = "http://localhost:20128/v1"
    ninerouter_api_key: str = os.environ.get("NINEROUTER_API_KEY", "")
    max_steps: int = 20
    worker_max_retries: int = 2
    require_confirm_for: list[str] = ["write_file", "edit_file", "run_shell"]
    shell_timeout: int = 120

def load_config(path: Path = None) -> Config:
    """
    ~/.config/lokal-ajan/config.toml (veya LOKAL_AJAN_CONFIG env değişkeni
    ile belirtilen dosya) varsa yükler; yoksa/parse edilemezse sessizce
    varsayılan Config'e düşer.
    Ayrıca TOML dosyasında açıkça bir model belirtilmemişse, son kullanılan
    state (durum) modelini okuyarak iki kaynak arasındaki uyumu sağlar.
    """
    config_path = path or CONFIG_PATH
    data = {}
    if tomllib is not None and config_path.is_file():
        try:
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
        except Exception:
            data = {}

    # State ile senkronizasyon: TOML'da açıkça model yoksa son kullanılan modeli al
    if "default_model" not in data:
        try:
            state = load_state()
            saved_model = state.get("model") or state.get("last_model")
            if saved_model:
                data["default_model"] = saved_model
        except Exception:
            pass

    try:
        return Config(**data)
    except Exception:
        return Config()
