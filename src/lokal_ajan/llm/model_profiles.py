import re
from typing import Optional
from pydantic import BaseModel


class ModelProfile(BaseModel):
    name_pattern: str
    num_ctx: int = 4096
    temperature: float = 0.1
    native_tool_call: bool = False
    prompt_level: str = "standard"  # "minimal" or "standard"
    max_tool_output: int = 2000

    # --- Küçük/hibrit-düşünme modelleri için eklenen alanlar ---
    # Model Ollama'nın "think" alanını destekliyor mu (Qwen3 ailesi gibi)?
    supports_think_control: bool = False
    # Destekliyorsa thinking kapatılsın mı? (tool-call ayrıştırmasını
    # bozmaması ve dar context'i şişirmemesi için küçük modellerde True.)
    disable_thinking: bool = True
    # Ollama "repeat_penalty" -- küçük modellerde takılıp aynı token'ı
    # tekrar üretme (loop) eğilimini azaltır.
    repeat_penalty: float = 1.15
    # Ard arda parse hatası durumunda modele kaç kez düzeltme isteği
    # gönderileceği (agent/loop.py tarafından kullanılır).
    parse_retry_limit: int = 2


# Modelin adından yaklaşık parametre büyüklüğünü (milyar cinsinden) çıkarır.
# "qwen3:0.6b" -> 0.6, "qwen2.5-coder:7b" -> 7.0, "phi4-mini" -> None
_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*b\b", re.IGNORECASE)


def _extract_size_b(model_name: str) -> Optional[float]:
    m = _SIZE_RE.search(model_name)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


# ---------------------------------------------------------------------
# Explicit profiles, en spesifikten en genele doğru sırayla denenir
# (get_profile_for_model ilk eşleşeni döndürür).
# ---------------------------------------------------------------------
PROFILES = [
    # --- Cloud API modelleri (öncelikli eşleşir) ---
    ModelProfile(
        name_pattern=r"^groq/",
        num_ctx=32768,
        temperature=0.1,
        native_tool_call=True,
        prompt_level="standard",
        max_tool_output=30000,
    ),
    ModelProfile(
        name_pattern=r"^openrouter/",
        num_ctx=8192,
        temperature=0.1,
        native_tool_call=True,
        prompt_level="standard",
        max_tool_output=15000,
    ),
    ModelProfile(
        name_pattern=r"^ninerouter/",
        num_ctx=8192,
        temperature=0.1,
        native_tool_call=True,
        prompt_level="standard",
        max_tool_output=15000,
    ),
    # --- Qwen3 ailesi: hepsi Ollama "think" kontrolünü destekler ve
    #     eğitilmiş oldukları native tool-call formatı {"name":..,
    #     "arguments":..} şeklindedir (bkz. agent/prompt.py). ---
    ModelProfile(
        name_pattern=r"qwen3(?:\.\d+)?[.:\-]?\s*0\.6b",
        num_ctx=4096,
        temperature=0.15,
        native_tool_call=False,
        prompt_level="minimal",
        max_tool_output=4000,
        supports_think_control=True,
        disable_thinking=True,
        repeat_penalty=1.2,
        parse_retry_limit=3,
    ),
    ModelProfile(
        # kullanıcının bahsettiği "qwen3.5:0.8b" gibi varyantları da
        # yakalar (qwen3 + ~0.5-1b arası ufak sürümler).
        name_pattern=r"qwen3(?:\.\d+)?[.:\-]?\s*0\.[5-9]b",
        num_ctx=4096,
        temperature=0.15,
        native_tool_call=False,
        prompt_level="minimal",
        max_tool_output=4000,
        supports_think_control=True,
        disable_thinking=True,
        repeat_penalty=1.2,
        parse_retry_limit=3,
    ),
    ModelProfile(
        name_pattern=r"qwen3(?:\.\d+)?[.:\-]?\s*1\.[5-9]b",
        num_ctx=8192,
        temperature=0.15,
        native_tool_call=False,
        prompt_level="minimal",
        max_tool_output=8000,
        supports_think_control=True,
        disable_thinking=True,
        repeat_penalty=1.15,
        parse_retry_limit=3,
    ),
    ModelProfile(
        name_pattern=r"qwen3(?:\.\d+)?[.:\-]?\s*(?:2|3)(?:\.\d+)?b",
        num_ctx=8192,
        temperature=0.15,
        native_tool_call=False,
        prompt_level="minimal",
        max_tool_output=8000,
        supports_think_control=True,
        disable_thinking=True,
        repeat_penalty=1.15,
        parse_retry_limit=3,
    ),
    ModelProfile(
        name_pattern=r"qwen3(?:\.\d+)?[.:\-]?\s*4b",
        num_ctx=16384,
        temperature=0.2,
        native_tool_call=True,
        prompt_level="minimal",
        max_tool_output=20000,
        supports_think_control=True,
        disable_thinking=True,
        repeat_penalty=1.1,
        parse_retry_limit=2,
    ),
    ModelProfile(
        name_pattern=r"qwen3(?:\.\d+)?[.:\-]?\s*(8|14|32)b",
        num_ctx=32768,
        temperature=0.2,
        native_tool_call=True,
        prompt_level="standard",
        max_tool_output=35000,
        supports_think_control=True,
        disable_thinking=True,
        repeat_penalty=1.1,
        parse_retry_limit=2,
    ),
    # Yukarıdaki spesifik boyutlara uymayan diğer tüm qwen3 varyantları
    # (qwen3-coder, qwen3-vl, qwen3-ram, gelecekteki yeni boyutlar, vb.).
    ModelProfile(
        name_pattern=r"qwen3(?:\.\d+)?",
        num_ctx=16384,
        temperature=0.2,
        native_tool_call=True,
        prompt_level="standard",
        max_tool_output=20000,
        supports_think_control=True,
        disable_thinking=True,
        repeat_penalty=1.1,
        parse_retry_limit=2,
    ),

    # --- Diğer bilinen küçük modeller ---
    ModelProfile(
        name_pattern=r"qwen2\.5[.:\-]?\s*0\.5b",
        num_ctx=4096,
        temperature=0.15,
        native_tool_call=False,
        prompt_level="minimal",
        max_tool_output=4000,
        repeat_penalty=1.2,
        parse_retry_limit=3,
    ),
    ModelProfile(
        name_pattern=r"qwen2\.5[.:\-]?\s*1\.5b",
        num_ctx=8192,
        temperature=0.15,
        native_tool_call=False,
        prompt_level="minimal",
        max_tool_output=8000,
        repeat_penalty=1.15,
        parse_retry_limit=3,
    ),
    ModelProfile(
        name_pattern=r"qwen2\.5-coder",
        num_ctx=8192,
        temperature=0.1,
        native_tool_call=True,
        prompt_level="standard",
        max_tool_output=10000,
    ),
    ModelProfile(
        name_pattern=r"llama3\.2[.:\-]?\s*1b",
        num_ctx=8192,
        temperature=0.15,
        native_tool_call=False,
        prompt_level="minimal",
        max_tool_output=6000,
        repeat_penalty=1.15,
        parse_retry_limit=3,
    ),
    ModelProfile(
        name_pattern=r"llama3\.2",
        num_ctx=8192,
        temperature=0.1,
        native_tool_call=True,
        prompt_level="standard",
        max_tool_output=10000,
    ),
    ModelProfile(
        name_pattern=r"gemma2:2b",
        num_ctx=4096,
        temperature=0.1,
        native_tool_call=False,
        prompt_level="minimal",
        max_tool_output=4000,
        repeat_penalty=1.15,
        parse_retry_limit=3,
    ),
    ModelProfile(
        name_pattern=r"nemotron-3-super-120b",
        num_ctx=32768,
        temperature=0.1,
        native_tool_call=True,
        prompt_level="standard",
        max_tool_output=35000,
    ),
    ModelProfile(
        name_pattern=r"llama-3\.3-nemotron-super-49b",
        num_ctx=32768,
        temperature=0.1,
        native_tool_call=True,
        prompt_level="standard",
        max_tool_output=30000,
    ),
    ModelProfile(
        name_pattern=r"nemotron-3-nano-30b",
        num_ctx=16384,
        temperature=0.1,
        native_tool_call=True,
        prompt_level="standard",
        max_tool_output=25000,
    ),
    ModelProfile(
        name_pattern=r"lfm(?:2\.5)?[-.:]?\s*8b",
        num_ctx=8192,
        temperature=0.15,
        native_tool_call=True,
        prompt_level="standard",
        max_tool_output=15000,
        repeat_penalty=1.1,
        parse_retry_limit=2,
    ),
    ModelProfile(
        name_pattern=r"lfm",
        num_ctx=8192,
        temperature=0.15,
        native_tool_call=False,
        prompt_level="minimal",
        max_tool_output=8000,
        repeat_penalty=1.15,
        parse_retry_limit=3,
    ),
]

DEFAULT_PROFILE = ModelProfile(
    name_pattern=r".*",
    num_ctx=4096,
    temperature=0.1,
    native_tool_call=False,
    prompt_level="standard",
    max_tool_output=5000,
)


def _size_based_profile(model_name: str, size_b: float) -> ModelProfile:
    """Listede tanımlı olmayan bir model için, adındaki parametre
    büyüklüğüne (B) göre makul bir varsayılan profil üretir.
    """
    is_qwen3 = bool(re.search(r"qwen3", model_name, re.IGNORECASE))
    if size_b <= 1.0:
        return ModelProfile(
            name_pattern=re.escape(model_name),
            num_ctx=4096,
            temperature=0.15,
            native_tool_call=False,
            prompt_level="minimal",
            max_tool_output=4000,
            supports_think_control=is_qwen3,
            disable_thinking=True,
            repeat_penalty=1.2,
            parse_retry_limit=3,
        )
    if size_b <= 3.0:
        return ModelProfile(
            name_pattern=re.escape(model_name),
            num_ctx=8192,
            temperature=0.15,
            native_tool_call=False,
            prompt_level="minimal",
            max_tool_output=8000,
            supports_think_control=is_qwen3,
            disable_thinking=True,
            repeat_penalty=1.15,
            parse_retry_limit=3,
        )
    if size_b <= 9.0:
        return ModelProfile(
            name_pattern=re.escape(model_name),
            num_ctx=8192,
            temperature=0.2,
            native_tool_call=True,
            prompt_level="standard" if size_b >= 7 else "minimal",
            max_tool_output=15000,
            supports_think_control=is_qwen3,
            disable_thinking=True,
            repeat_penalty=1.1,
            parse_retry_limit=2,
        )
    return ModelProfile(
        name_pattern=re.escape(model_name),
        num_ctx=32768,
        temperature=0.2,
        native_tool_call=True,
        prompt_level="standard",
        max_tool_output=35000,
        supports_think_control=is_qwen3,
        disable_thinking=True,
        repeat_penalty=1.1,
        parse_retry_limit=2,
    )


def get_profile_for_model(model_name: str) -> ModelProfile:
    for profile in PROFILES:
        if re.search(profile.name_pattern, model_name, re.IGNORECASE):
            return profile

    size_b = _extract_size_b(model_name)
    if size_b is not None:
        return _size_based_profile(model_name, size_b)

    return DEFAULT_PROFILE

