# qwen3 (0.6b / 1.7b / 4b ve benzeri ufak modeller) için yapılan değişiklikler

Bu sürüm, mevcut `lokal-ajan` kod tabanı üzerine, **çok küçük Ollama modellerinde
(0.6B-4B parametre)** tool-calling'i güvenilir hale getirmeye odaklanan bir
geliştirme turudur. Kod tabanı zaten sağlam bir iskelete sahipti (toleranslı
parser, sandbox, onay akışı); eklenenler özellikle qwen3 ailesinin gerçek
davranışına göre ince ayar.

## 1. Qwen3'ün `<think>...</think>` bloğu artık sorun çıkarmıyor
Qwen3, varsayılan olarak her yanıtın başına bir "hybrid thinking" bloğu
ekliyor. Bu, eski parser'da hem tool-call ayrıştırmasını (düşünme içindeki
sahte bir JSON'u yanlışlıkla tool-call sanma riski), hem de dar context
pencerelerini (thinking metni asıl cevaptan çok daha uzun olabiliyor) tehdit
ediyordu.

- `agent/thinking.py` (yeni): hem tam bir string üzerinde
  (`strip_thinking`), hem de canlı streaming üzerinde, etiketler chunk
  sınırlarına bölünse bile (`filter_thinking_stream`) `<think>` bloklarını
  temizler.
- `llm/ollama_client.chat_stream(..., think=False)`: Ollama'nın kendi
  `think` API alanını da kullanarak, destekleyen modellerde thinking'i
  kaynağında kapatmayı dener (model desteklemiyorsa alanı çıkarıp sessizce
  tekrar dener).
- Bu iki katman birlikte: hem hız kazandırıyor (thinking token'ları
  üretilmiyor), hem de tool-call ayrıştırmasını ve context bütçesini thinking
  metninden tamamen izole ediyor.

## 2. Tool-call formatı Qwen'in **kendi eğitildiği** formatla değiştirildi
Eski prompt `{"tool": "...", "args": {...}}` gibi özel bir şema kullanıyordu.
Qwen ailesi (2.5 ve 3) resmi olarak `<tool_call>{"name": ..., "arguments":
{...}}</tool_call>` formatıyla fine-tune edilmiş durumda. Prompt artık bu
formatı örnek gösteriyor -- modelin daha önce hiç görmediği bir şema yerine,
eğitim dağılımıyla birebir örtüşen bir kalıp istiyoruz. Parser zaten her iki
formatı da (`tool`/`args` ve `name`/`arguments`) destekliyordu, o yüzden
diğer model aileleri (llama, gemma vb.) için geriye dönük uyumluluk korundu.

## 3. Model profilleri (`llm/model_profiles.py`) genişletildi
- `qwen3:0.6b`, `qwen3:1.7b`, `qwen3:4b`, `qwen3:8b/14b/32b` ve genel bir
  `qwen3` fallback'i eklendi (num_ctx, temperature, prompt_level,
  max_tool_output, repeat_penalty, thinking kontrolü, parse retry limiti).
- Kullanıcının bahsettiği "qwen3.5:0.8b" gibi henüz tam olarak bilinmeyen /
  standart olmayan bir isimlendirme için bile: model adı listede yoksa,
  isimden parametre büyüklüğü (ör. "0.8b") regex ile çıkarılıp **boyuta göre
  otomatik, makul bir profil** üretiliyor (`_size_based_profile`). Yani
  yarın çıkacak yeni bir qwen3 varyantı için de elle profil eklemeye gerek
  kalmıyor.
- Yeni alanlar: `supports_think_control`, `disable_thinking`,
  `repeat_penalty` (küçük modellerde tekrar/loop eğilimini azaltır),
  `parse_retry_limit`.

## 4. Prompt boyutu küçültüldü (`agent/prompt.py`)
Eskiden sistem promptuna her tool'un ham `model_json_schema()` çıktısı
(`$defs`, `title`, `type: object`, `required: [...]`) gömülüyordu -- tool
başına 100-200+ token. 0.6B-4B gibi modellerde bu, context'in büyük kısmını
işgal edip modelin talimatı unutmasına yol açıyor. Artık
`format_tools_compact()` ile tek satırlık, ör.
`write_file(path:string, content:string): Creates a new file...` formatı
kullanılıyor (~10-15 token/tool).

## 5. Gerçek context/history kırpma (`agent/context.py`)
Eskiden `prepare_context` hiçbir şey yapmıyordu (TODO yorumu vardı). Artık
karakter-bütçesi tabanlı bir sliding-window uyguluyor: sistem promptu her
zaman korunuyor, geri kalan mesajlar en yeniden en eskiye doğru bütçeye
sığana kadar tutuluyor; sığmayanlar atılıp yerine kısa bir bilgi notu
ekleniyor. (Küçük modellerle ek bir LLM-özetleme çağrısı riskli/güvenilmez
olacağından bilinçli olarak tercih edilmedi.)

## 6. Agent döngüsü (`agent/loop.py`)
- Streaming, `filter_thinking_stream` üzerinden geçiyor; hem ekrana basılan
  hem history'ye kaydedilen metin zaten temizlenmiş oluyor.
- `options`'a `repeat_penalty` eklendi; `think` alanı profile göre
  API'ye gönderiliyor.
- **Boş yanıt kurtarma**: model her şeyi `<think>` içinde bırakıp görünür
  hiçbir şey üretmezse (küçük modellerde sık görülür), sessizce turu
  bitirmek yerine kısa bir düzeltme mesajıyla (profile göre 2-3 kez)
  yeniden deniyor.
- `OllamaConnectionError` ile Ollama kapalıyken/erişilemezken anlaşılır bir
  hata mesajı.

## 7. Diğer küçük iyileştirmeler
- `config.py`: `~/.config/lokal-ajan/config.toml` artık gerçekten okunuyor
  (plan.md'de vardı ama uygulanmamıştı); varsayılan model `qwen3:1.7b`
  yapıldı.
- `safety/confirm.py`: bilinen yıkıcı `run_shell` komut kalıpları (rm -rf /,
  mkfs, fork bomb, `curl | sh`, vb.) onay ekranında ekstra kırmızı bir
  uyarıyla vurgulanıyor.
- Eksik olan `README.md` eklendi (pyproject.toml onu referans alıyordu).
- `tests/test_qwen3_optimizations.py`: yukarıdaki tüm davranışlar için 20
  yeni birim testi (toplam 34 test, hepsi geçiyor).

## Hızlı doğrulama
```bash
pip install -e .
pytest tests/ -v
ollama pull qwen3:0.6b
lokal-ajan --model qwen3:0.6b --workdir /tmp/deneme
```
