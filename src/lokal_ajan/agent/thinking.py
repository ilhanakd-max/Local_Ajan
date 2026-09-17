"""
Küçük hibrit-düşünme (hybrid-thinking) modelleri -- başta Qwen3 ailesi --
varsayılan olarak yanıtın başına ``<think> ... </think>`` bloğu ekler.

Bu proje tool-call'ları prompt tabanlı, düz metin ayrıştırma ile bulduğu
için bu bloklar iki soruna yol açar:

1. `parser.py`'nin ilk bulduğu ``{`` veya ``<tool_call>`` etiketini
   düşünme bloğunun İÇİNDEN yakalayıp yanlış/eksik bir çağrı üretmesi.
2. 0.6B-4B gibi çok küçük ``num_ctx`` pencereli modellerde, düşünme
   metninin (genelde asıl cevaptan çok daha uzun) history'ye eklenip
   bağlamı hızla doldurması.

Bu modül iki şey sağlar:
- `strip_thinking(text)`: tam bir metinden düşünme bloklarını temizler.
- `filter_thinking_stream(chunks)`: Ollama'dan gelen streaming parçaları
  üzerinde aynı işi, etiketler parçalar arasında bölünmüş olsa bile canlı
  olarak yapan bir generator.

Not: `ollama_client.chat_stream` çağrısına ``think=False`` verildiğinde
Ollama zaten thinking'i kapatmayı dener (destekleyen modellerde). Ancak
bazı sürümler/quantizasyonlar yine de boş ya da dolu bir ``<think>`` bloğu
üretebiliyor; bu yüzden bu filtre "think=False" ile birlikte, ona ek bir
güvenlik katmanı olarak her zaman uygulanır.
"""

from typing import Iterator

_OPEN = "<think>"
_CLOSE = "</think>"


def strip_thinking(text: str) -> str:
    """Bir metindeki tüm <think>...</think> bloklarını kaldırır.

    Kapanmamış bir <think> etiketi varsa (model orada kesildiyse), o
    noktadan itibaren metnin geri kalanı da düşünme sayılıp atılır --
    çünkü kapanmamış bir düşünme bloğu, tanım gereği henüz "final" bir
    cevap değildir.
    """
    if _OPEN not in text and _CLOSE not in text:
        return text

    out = []
    i = 0
    n = len(text)
    while i < n:
        start = text.find(_OPEN, i)
        if start == -1:
            out.append(text[i:])
            break
        out.append(text[i:start])
        end = text.find(_CLOSE, start + len(_OPEN))
        if end == -1:
            # Kapanmamış blok: geri kalan her şeyi at.
            i = n
            break
        i = end + len(_CLOSE)
    return "".join(out).strip()


def filter_thinking_stream(chunks: Iterator[str]) -> Iterator[str]:
    """Streaming metin parçalarından <think>...</think> içeriğini canlı
    olarak süzer, sadece görünür (final) metni yield eder.

    Etiketlerin iki chunk arasına bölünmesi ihtimaline karşı, her adımda
    olası bir etiketin en uzun halinin uzunluğu kadar (-1) bir "güvenlik
    payı" tampon (buffer) içinde bekletilir.
    """
    buf = ""
    in_think = False
    margin_open = len(_OPEN) - 1
    margin_close = len(_CLOSE) - 1

    for chunk in chunks:
        if not chunk:
            continue
        buf += chunk

        while True:
            if not in_think:
                idx = buf.find(_OPEN)
                if idx == -1:
                    safe_len = max(0, len(buf) - margin_open)
                    if safe_len:
                        yield buf[:safe_len]
                        buf = buf[safe_len:]
                    break
                else:
                    if idx:
                        yield buf[:idx]
                    buf = buf[idx + len(_OPEN):]
                    in_think = True
            else:
                idx = buf.find(_CLOSE)
                if idx == -1:
                    safe_len = max(0, len(buf) - margin_close)
                    buf = buf[safe_len:]
                    break
                else:
                    buf = buf[idx + len(_CLOSE):]
                    in_think = False

    if buf and not in_think:
        yield buf
