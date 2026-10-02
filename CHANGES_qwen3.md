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

## 8. v0.3.5 — Dayanıklılık, Güvenlik ve Mimari İyileştirmeleri

Bu turda, uygulamanın uzun süreli oturumlarda stabilitesini artırmak ve güvenlik katmanını sıkılaştırmak için aşağıdaki geliştirmeler yapıldı:

1. **Derinlemesine Savunma (Defense-in-Depth Sandbox):**
   * Dosya ve Git araçlarının (`read_file`, `write_file`, `edit_file`, `list_dir`, `glob`, `grep`, `git_status`, `git_diff`) içine doğrudan `workdir` ve `get_safe_path` entegrasyonu sağlandı.
   * Araçlar doğrudan çağrılsalar bile çalışma alanı dışındaki dosyalara erişim kökten engellendi.

2. **Bulut API Dayanıklılığı (Retry & Exponential Backoff):**
   * Tüm bulut sağlayıcı istemcilerine (Groq, OpenRouter, NineRouter, Nvidia) bağlantı kopmalarına (`ConnectError`) ve sunucu/hız sınırı hatalarına (`429 Too Many Requests`, `500`, `502`, `503`, `504`) karşı 3 aşamalı üstel bekleme (`time.sleep(2 ** attempt)`) mekanizması eklendi.
   * `max_tokens` için sabit 4096 sınırı kaldırılarak modelin gerçek `num_ctx` değeri iletildi.

3. **Bellek Güvenliği ve Hafıza Budama (ChatHistory Pruning):**
   * `ChatHistory` sınıfına sınır (`max_size=500`) ve otomatik kaydırmalı budama mantığı eklendi.
   * Oturum çok uzun sürse dahi en baştaki kritik `system_prompt` daima korunur; eskiyen mesajlar sırayla tahliye edilerek RAM sızıntısı önlendi.

4. **Parser ve XML Yanlış Pozitif Koruması:**
   * XML/HTML biçimli araç ayrıştırıcı fonksiyonu (`_try_parse_xml_tool_call`), geçerli araç listesi (`valid_names`) ile sıkılaştırıldı; modelin ürettiği standart HTML etiketlerinin yanlışlıkla araç sanılması engellendi.
   * `extract_all_tool_calls` içindeki kapalı ve açık etiket ayrıştırma mantığı birleştirilerek kod tekrarı giderildi ve Markdown kod bloğu çıktısı veren modellerle uyumluluğu artırıldı.

5. **Döngü ve Araç Mantığı İyileştirmeleri:**
   * `_write_multiple` sonrasında döngünün erkenden sonlandırılması engellendi; modelin dosya yazdıktan sonra test çalıştırma veya özetleme yapabilmesi sağlandı.
   * Çakışan tekrar ve döngü kontrolleri tek bir akıllı `step_executed_calls` mekanizmasında sadeleştirildi.
   * İşçi model özet notu (`_worker_note`) üst limiti 2000'den 8000 karaktere çıkarıldı.
   * `RunShellTool` için yapılandırılabilir zaman aşımı (`shell_timeout`) eklendi.
   * `load_config()`, `state.json` ile senkronize çalışarak interaktif menüde seçilen modeli hatırlar hale getirildi.

## 9. v0.3.6 — Döngü Koruması, Windows PowerShell Base64 & Kararlılık

Bu sürümde, ajanın görev bitiminde gereksiz kod döngülerine girmesini engelleyen kritik düzeltmeler ve çoklu platform kararlılık iyileştirmeleri yapıldı:

1. **Özet Kod Döngüsü Koruması (Regurgitation / Loop Prevention):**
   * Küçük modellerin (Qwen 2B/3.8B vb.) görev tamamlandığında özet veya rapor amaçlı çıktıladığı Markdown kod blokları (` ```html ... ``` `) parser tarafından yanlışlıkla yeni bir `write_file` talebi olarak algılanıyordu.
   * `_ALREADY_DONE_PATTERN` filtresi genişletilerek `extract_all_tool_calls` ve `extract_tool_call` içine yerleştirildi; tamamlama başlığı/özeti altındaki kod blokları araç çağrısı olarak yorumlanmaz.
   * Döngü içi araç geri bildirimi ve sistem prompt kuralları (Minimal, Standart, Ponytail) güncellenerek modelin görev tamamlandığında kod dökmesi yasaklandı; yalnızca 1 kısa doğrulama cümlesi söyleyip durması sağlandı.

2. **Windows PowerShell Güvenliği (`-EncodedCommand`):**
   * Windows ortamında PowerShell komutları `UTF-16LE` Base64 kodlaması ile `-EncodedCommand` üzerinden çalıştırılmaya başlandı. Çok satırlı ifadeler, boru hatları (`|`), tırnaklar ve özel karakterler Windows'ta kabuk bozulması olmadan güvenle yürütülür.

3. **Uzun Oturum Bellek Uyarısı:**
   * Oturum geçmişi 40 mesajı aştığında bellek şişmesini ve token aşımını önlemek amacıyla tek seferlik kullanıcı bilgilendirme ipucu eklendi.

4. **Kod Temizliği & Testler:**
   * Kullanılmayan `_repeat_count` ölü kodu temizlendi.
   * Test dosya isimlendirmesi güncellendi (`test_groq_profiles.py`) ve Markdown tamamlama özetini doğrulayan birim test eklendi.



## 10. v0.3.7 — v0.3.7: Döngü Koruması, Windows PowerShell Base64 & Kararlılık

- Bu sürümde genel hata düzeltmeleri ve kararlılık iyileştirmeleri yapıldı.



## 11. v0.3.8 — v0.3.8: Döngü Koruması, Windows PowerShell Base64 & Kararlılık

- Bu sürümde genel hata düzeltmeleri ve kararlılık iyileştirmeleri yapıldı.



## 12. v0.3.9 — v0.3.9:  Döngü Koruması, Windows PowerShell Base64 & Kararlılık

- Bu sürümde genel hata düzeltmeleri ve kararlılık iyileştirmeleri yapıldı.



## 13. v0.3.10 — release: v0.3.10 - loop protection, windows powershell base64 and stability improvements

- Bu sürümde genel hata düzeltmeleri ve kararlılık iyileştirmeleri yapıldı.



## 14. v0.3.11 — release: v0.3.11 - v0.3.10 - loop protection, windows powershell base64 and stability improvements

- Bu sürümde genel hata düzeltmeleri ve kararlılık iyileştirmeleri yapıldı.



## 15. v0.3.12 — release: v0.3.12 - fix: LLM parser robust optimizations and OpenRouter stream handling

- Bu sürümde genel hata düzeltmeleri ve kararlılık iyileştirmeleri yapıldı.

## 16. v0.3.13 — release: v0.3.13 - feat: office tools (read/write Excel & PDF) and binary file recovery hints

- **Excel ve PDF Araçları Eklendi:**
  - `read_excel`: Excel tablolarını (.xlsx) okuyup Markdown formatında ajana sunar.
  - `write_excel`: JSON verisini (.xlsx) formatında tablo olarak kaydeder.
  - `read_pdf`: PDF belgelerinden metin çıkarır.
  - `write_pdf`: Ajanın ürettiği metinlerden standart PDF oluşturur.
- **Akıllı Hata & Yönlendirme Koruması:**
  - Küçük modellerin PDF ve Excel dosyalarını yanlışlıkla düz metin okuma aracı olan `read_file` ile açmaya çalışıp `utf-8` hatası alması engellendi.
  - İlgili araca yönlendirici rehber hata mesajları (`Please use 'read_pdf' / 'read_excel' instead`) eklendi.
- **Kapsamlı Test Kapsamı:** Yeni ofis araçları ve güvenlik kontrolleri için birim testler eklendi.



## 17. v0.3.14 — release: v0.3.14 - feat: style & formula preserving excel tools (append_excel & edit_excel_cells)

- **Stil & Formül Korumalı Excel Düzenleme:**
  - `append_excel`: Var olan bir Excel dosyasının renk, font, kenarlık ve formüllerini bozmadan en sona yeni satırlar ekler; önceki satırın stilini otomatik olarak yeni satırlara kopyalar (`copy_style`).
  - `edit_excel_cells`: Tablonun genel yapısına dokunmadan sadece belirli koordinatlardaki hücreleri (örn: `B5`, `C10`) yeni değer veya formüllerle günceller.
- **Kapsamlı Test Kapsamı:** Stil kopyalama ve formül koruma doğrulamaları birim testlere eklendi.



## 18. v0.3.15 — release: v0.3.15 - v0.3.14 - feat: style and formula preserving excel tools (append_excel and edit_excel_cells)

- Bu sürümde genel hata düzeltmeleri ve kararlılık iyileştirmeleri yapıldı.



## 19. v0.3.16 — release: v0.3.16  feat: style and formula preserving excel tools (append_excel and edit_excel_cells)

- Bu sürümde genel hata düzeltmeleri ve kararlılık iyileştirmeleri yapıldı.

## Hızlı doğrulama
```bash
pip install -e .
pytest tests/ -v
ollama pull qwen3:0.6b
lokal-ajan --model qwen3:0.6b --workdir /tmp/deneme
```

