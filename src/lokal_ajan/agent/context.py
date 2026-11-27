import re
from typing import List, Dict, Any

# Kaba bir tahmin: İngilizce/Türkçe karışık teknik metinde ortalama
# 1 token ~ 3.5-4 karakter. Kesin bir tokenizer'a bağlı kalmamak için
# (Ollama tarafında model başına değişir) muhafazakar bir katsayı kullanıyoruz.
_CHARS_PER_TOKEN = 3.5

_TRUNCATION_NOTICE = (
    "[Not: Bağlam penceresi sınırlı olduğu için önceki konuşmadan bazı "
    "eski mesajlar kırpıldı. Sistem talimatı ve en güncel mesajlar korunuyor.]"
)


def truncate_tool_output(output: str, max_length: int = 2000, keep_tail: int = 0) -> str:
    """
    Truncates tool output if it's too long, to avoid flooding context window.

    keep_tail > 0 ise çıktının SONUNDAN da bu kadar karakter korunur (kabuk
    komutlarında hata/stack-trace genelde sondadır; sadece baş kısmı tutmak
    küçük modelin asıl hatayı görmesini engelliyordu).
    """
    if len(output) <= max_length:
        return output

    if keep_tail and keep_tail < max_length:
        head = output[:max_length - keep_tail]
        tail = output[-keep_tail:]
        omitted = len(output) - len(head) - len(tail)
        return (
            f"{head}\n\n... ({omitted} karakter atlandı; baş ve son kısım gösteriliyor. "
            f"Ara kısım için aracı satır aralığı/filtre ile tekrar çağırın.) ...\n\n{tail}"
        )

    truncated = output[:max_length]
    truncated += f"\n\n... (Çıktı {max_length} karaktere kırpıldı. Devamını görmek için aracı tekrar, uygun parametrelerle çağırın.)"
    return truncated


_TOOL_OUTPUT_MARKER = "<tool_output>"
_STALE_RESULT_LIMIT = 160
_STALE_CALL_LIMIT = 400


def _compact_tool_output_message(content: str) -> str:
    """Eski bir '<tool_output>' mesajını, her sonuç için tek kısa satıra indirir."""
    start = content.find(_TOOL_OUTPUT_MARKER)
    end = content.find("</tool_output>")
    if start == -1 or end == -1:
        return content
    body = content[start + len(_TOOL_OUTPUT_MARKER):end].strip()
    # Sonuçlar "'tool' → ..." ile başlar; satırlar arasında ayır
    parts = re.split(r"(?m)^(?='[a-zA-Z_]+' → )", body)
    lines = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        first = part.splitlines()[0]
        if len(part) > _STALE_RESULT_LIMIT:
            first = first[:_STALE_RESULT_LIMIT] + f"… [{len(part)} karakter, eski çıktı özetlendi]"
        lines.append(first)
    return "Önceki araç sonuçları (özet):\n" + "\n".join(lines)


def _compact_tool_call_message(content: str) -> str:
    """Eski bir assistant mesajındaki büyük <tool_call> gövdesini (ör. yazılan dosyanın
    tüm içeriği) yer tutucuya çevirir. Model neyi yazdığını zaten dosyadan okuyabilir."""
    if "<tool_call>" not in content or len(content) <= _STALE_CALL_LIMIT:
        return content

    def _shrink(m: "re.Match[str]") -> str:
        inner = m.group(1)
        if len(inner) <= _STALE_CALL_LIMIT:
            return m.group(0)
        name = re.search(r'"(?:name|tool)"\s*:\s*"([^"]+)"', inner)
        path = re.search(r'"path"\s*:\s*"([^"]+)"', inner)
        label = name.group(1) if name else "tool"
        target = f', "path": "{path.group(1)}"' if path else ""
        return (
            f'<tool_call>\n{{"name": "{label}", "arguments": {{{target.lstrip(", ")}'
            f'{", " if target else ""}"…": "[{len(inner)} karakter, özetlendi]"}}}}\n</tool_call>'
        )

    shrunk = re.sub(r"<tool_call>(.*?)(?:</tool_call>|$)", _shrink, content, flags=re.DOTALL)
    return shrunk


def compact_history(messages: List[Dict[str, Any]], keep_recent: int = 4) -> List[Dict[str, Any]]:
    """Son `keep_recent` mesaj dışındaki eski araç çıktılarını ve devasa tool_call
    gövdelerini özetler. Orijinal listeyi DEĞİŞTİRMEZ (kopya döndürür).

    Küçük bağlam pencerelerinde (4K-8K) bağlamı en çok şişiren şey, eski
    read_file çıktıları ve modelin kendi yazdığı dosya içerikleridir; ikisi de
    gerektiğinde araçla yeniden alınabilir. Bu yüzden sohbetin kendisini
    atmadan önce bunlar küçültülür.
    """
    if len(messages) <= keep_recent:
        return list(messages)
    cutoff = len(messages) - keep_recent
    out: List[Dict[str, Any]] = []
    for i, m in enumerate(messages):
        if i >= cutoff or m.get("role") == "system":
            out.append(m)
            continue
        content = m.get("content", "") or ""
        new_content = content
        if m.get("role") == "user" and _TOOL_OUTPUT_MARKER in content:
            new_content = _compact_tool_output_message(content)
        elif m.get("role") == "assistant":
            new_content = _compact_tool_call_message(content)
        if new_content != content:
            m = {**m, "content": new_content}
        out.append(m)
    return out


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

    # Her şey bütçeye sığıyorsa dokunma. Sığmıyorsa önce eski araç çıktılarını/
    # tool_call gövdelerini özetle (konuşmanın kendisini atmadan önce).
    if used + sum(len(m.get("content", "")) for m in rest) > budget_chars:
        for keep in (6, 4, 2):
            compacted = compact_history(rest, keep_recent=keep)
            if used + sum(len(m.get("content", "")) for m in compacted) <= budget_chars:
                break
        rest = compacted
    else:
        return messages

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
