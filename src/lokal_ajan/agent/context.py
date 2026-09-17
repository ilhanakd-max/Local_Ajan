from typing import List, Dict, Any

# Kaba bir tahmin: İngilizce/Türkçe karışık teknik metinde ortalama
# 1 token ~ 3.5-4 karakter. Kesin bir tokenizer'a bağlı kalmamak için
# (Ollama tarafında model başına değişir) muhafazakar bir katsayı kullanıyoruz.
_CHARS_PER_TOKEN = 3.5

_TRUNCATION_NOTICE = (
    "[Not: Bağlam penceresi sınırlı olduğu için önceki konuşmadan bazı "
    "eski mesajlar kırpıldı. Sistem talimatı ve en güncel mesajlar korunuyor.]"
)


def truncate_tool_output(output: str, max_length: int = 2000) -> str:
    """
    Truncates tool output if it's too long, to avoid flooding context window.
    """
    if len(output) <= max_length:
        return output

    truncated = output[:max_length]
    truncated += f"\n\n... (Çıktı {max_length} karaktere kırpıldı. Devamını görmek için aracı tekrar, uygun parametrelerle çağırın.)"
    return truncated


def _estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / _CHARS_PER_TOKEN))


def prepare_context(
    messages: List[Dict[str, Any]],
    max_context: int = 4096,
    reserve_for_output_ratio: float = 0.35,
) -> List[Dict[str, Any]]:
    """
    Sistem promptunu her zaman korur; geri kalan mesajlardan, en yeniden
    en eskiye doğru, `max_context`'in bir kısmına sığana kadar ekler.
    Sığmayan en eski mesajlar (system hariç) atılır ve bunun yerine kısa
    bir bilgi notu eklenir.

    Bu, gerçek bir tokenizer olmadan (ve zayıf küçük modellerle ek bir
    LLM-özetleme çağrısı riske girmeden) uygulanan basit ama güvenilir bir
    sliding-window stratejisidir: qwen3:0.6b gibi 4K bağlamlı modellerde
    context taşması / silently truncated request hatalarını önler.
    """
    if not messages:
        return messages

    system_messages = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]

    # Modelin kendi cevabı + tool şeması için bir pay ayır, kalanı history'ye ver.
    budget_tokens = int(max_context * (1 - reserve_for_output_ratio))
    budget_chars = max(500, int(budget_tokens * _CHARS_PER_TOKEN))

    used = sum(len(m.get("content", "")) for m in system_messages)
    if used >= budget_chars:
        # Sistem promptu bile bütçeyi aşıyor (çok küçük num_ctx); yine de
        # olduğu gibi gönder, model kendi context'inde kırpar.
        return system_messages + rest

    kept_reversed: List[Dict[str, Any]] = []
    dropped = False
    for msg in reversed(rest):
        content_len = len(msg.get("content", ""))
        if used + content_len > budget_chars and kept_reversed:
            # En az bir mesaj tuttuysak burada durabiliriz; hiç mesaj
            # tutmadan direkt en yeni mesajı bile atmayız (agent'ın
            # cevap üretebilmesi için en azından son user mesajı gerekli).
            dropped = True
            continue
        kept_reversed.append(msg)
        used += content_len

    kept = list(reversed(kept_reversed))

    if dropped:
        # Notu, sistem promptundan hemen sonra (kronolojik olarak en başa)
        # bir "user" notu gibi ekliyoruz ki model bunu bir talimat gibi
        # değil, geçmişe dair bir bilgi notu gibi görsün.
        kept = [{"role": "user", "content": _TRUNCATION_NOTICE}] + kept

    return system_messages + kept
