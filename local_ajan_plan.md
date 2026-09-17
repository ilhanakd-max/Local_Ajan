# Proje Planı: `lokal-ajan` — Ollama Tabanlı Agentic CLI Aracı

## 0. Amaç ve Kapsam

OpenCode / Claude Code benzeri, terminalden çalışan, dosya okuma/yazma, bash komutu
çalıştırma, arama gibi **tool-calling** yeteneklerine sahip bir agentic CLI aracı.
Fark: bulut LLM yerine **Ollama üzerinde çalışan hafif/küçük modeller** (ör. qwen2.5-coder:7b,
llama3.2:3b, phi4-mini, gemma2:2b vb.) ile çalışacak ve bu modellerin sınırlı context
penceresi ile zayıf/tutarsız function-calling yeteneğine göre **özel olarak optimize
edilecek**.

İkinci bir parça: bir **masaüstü launcher** (`.desktop` dosyası + basit GUI seçim
penceresi). Bu launcher açıldığında kullanıcıya (a) hangi Ollama modelini kullanacağını
ve (b) hangi çalışma klasöründe (workdir) ajan çalıştıracağını sorar, sonra bir terminal
penceresi açıp ajanı o klasörde, o modelle başlatır.

Bu belge, opencode'a (veya başka bir kod ajanına) adım adım yaptırılacak iş planıdır.
Her faz sonunda çalışan bir ara ürün olmalı; fazlar bağımsız test edilebilir olmalı.

---

## 1. Genel Mimari

```
lokal-ajan/
├── pyproject.toml
├── README.md
├── plan.md
├── src/lokal_ajan/
│   ├── __init__.py
│   ├── cli.py                 # Typer/Click giriş noktası (entry point: `lokal-ajan`)
│   ├── config.py              # Config yükleme (~/.config/lokal-ajan/config.toml)
│   ├── agent/
│   │   ├── loop.py            # Ana ReAct/agent döngüsü
│   │   ├── prompt.py          # Sistem prompt şablonları (model boyutuna göre)
│   │   ├── parser.py          # Model çıktısından tool-call ayrıştırma (JSON/regex fallback)
│   │   ├── context.py         # Context/pencere yönetimi, sıkıştırma (compaction)
│   │   └── history.py         # Konuşma geçmişi, oturum kaydı
│   ├── llm/
│   │   ├── ollama_client.py   # Ollama /api/chat ve /api/generate sarmalayıcı
│   │   └── model_profiles.py  # Model bazlı ayarlar (context uzunluğu, tool-call stili)
│   ├── tools/
│   │   ├── base.py            # Tool arayüzü (name, schema, run())
│   │   ├── registry.py        # Tool kayıt/keşif sistemi
│   │   ├── fs_tools.py        # read_file, write_file, edit_file, list_dir, glob, grep
│   │   ├── shell_tool.py      # bash komutu çalıştırma (onaylı/sandbox'lı)
│   │   ├── search_tool.py     # ripgrep tabanlı kod arama
│   │   └── git_tools.py       # git status/diff/commit (opsiyonel faz)
│   ├── safety/
│   │   ├── confirm.py         # Yıkıcı işlemler için kullanıcı onayı
│   │   └── sandbox.py         # Çalışma dizini dışına çıkışı engelleme
│   └── ui/
│       └── console.py         # `rich` ile terminal çıktısı (renkli, streaming)
├── launcher/
│   ├── lokal-ajan.desktop     # .desktop dosyası (masaüstüne kopyalanacak)
│   ├── launcher.py            # GUI seçim penceresi (Tkinter, bağımlılıksız)
│   └── icon.png
├── tests/
│   ├── test_parser.py
│   ├── test_tools.py
│   └── test_agent_loop.py
└── scripts/
    └── install.sh              # kurulum + .desktop dosyasını ~/.local/share/applications'a koyar
```

### Teknoloji seçimi
- **Python 3.11+**
- **Ollama Python client** (`ollama` paketi) veya doğrudan `httpx` ile `/api/chat`
  (streaming + `format: json` desteği için düşük seviye `httpx` tercih edilir — daha
  fazla kontrol sağlar).
- **Typer**: CLI arayüzü.
- **Rich**: terminal çıktısı, streaming yazı, tool çağrısı görselleştirme.
- **Pydantic**: tool şemaları ve config doğrulama.
- **Tkinter**: launcher GUI (harici bağımlılık istemiyoruz; Tkinter çoğu Linux
  dağıtımında `python3-tk` ile hazır gelir — kurulum script'i bunu kontrol etsin).
- Harici sistem bağımlılığı: `ripgrep` (arama için, yoksa `grep`'e fallback).

---

## 2. Hafif Modeller İçin Kritik Optimizasyon Kararları

Bu proje bulut modelleri değil, 2B–8B parametreli lokal modelleri hedeflediği için
aşağıdaki noktalar **tasarımın merkezinde** olmalı:

1. **Native function-calling'e güvenme.** Ollama'daki birçok küçük model
   `tools=[...]` parametresini ya desteklemiyor ya da tutarsız kullanıyor. Bu yüzden
   birincil strateji: **prompt tabanlı, sıkı yapılandırılmış JSON tool-call formatı**
   (ör. tek satırlık `{"tool": "...", "args": {...}}` bloğu, belirli
   `<tool_call>...</tool_call>` etiketleri içinde). Model destekliyorsa native modu da
   dene, desteklemiyorsa bu fallback'e düş (`model_profiles.py` içinde model bazlı flag).
2. **Toleranslı parser.** `parser.py` küçük modellerin ürettiği bozuk JSON'u
   (fazladan virgül, tek tırnak, markdown code fence içine sarma) temizleyip
   parse etmeye çalışmalı. Parse başarısız olursa modele "sadece geçerli JSON döndür"
   şeklinde kısa bir düzeltme mesajı gönderip 1-2 kez yeniden dene.
3. **Kısa ve net sistem promptu.** Uzun, karmaşık sistem promptları küçük modellerde
   talimat kaybına yol açar. `prompt.py` modele göre iki seviyeli prompt üretmeli:
   "minimal" (≤3B modeller) ve "standart" (7B+ modeller). Tool listesi promptun içine
   kısa örneklerle (few-shot, 1-2 örnek) gömülmeli.
4. **Context penceresi yönetimi.** `context.py`:
   - Ollama modelinin `num_ctx` değerini `model_profiles.py`'den okuyup isteğe
     ekler (çoğu Ollama modeli varsayılan olarak küçük context ile açılır, bunu
     büyütmek gerekir).
   - Belirli bir token eşiğine yaklaşınca eski konuşma turlarını özetleyip
     (aynı model ile kısa bir "summarize" çağrısı) history'yi sıkıştırır.
   - Tool çıktıları (özellikle dosya içerikleri, komut çıktıları) varsayılan olarak
     belirli bir satır/karakter sınırına kırpılır, "... (kırpıldı, devamı için tekrar
     iste)" notu eklenir.
5. **Tek seferde tek tool çağrısı.** Küçük modeller çoklu paralel tool çağrısında
   karışabiliyor. Agent loop'u bir turda **tek tool çağrısı** bekleyip sonucu
   döndürecek, sıradaki adımı yeni bir turda isteyecek şekilde tasarlanmalı
   (ReAct: Thought → Action → Observation → tekrar).
6. **Model profilleri.** `model_profiles.py` içinde model adına göre (regex eşleşmesi:
   `qwen2.5-coder`, `llama3.2`, `phi4-mini`, `gemma2`, vb.) şu ayarlar tutulur:
   `num_ctx`, `temperature` (tool çağrısı için düşük, ör. 0.1-0.3), native tool-call
   desteği var mı, prompt seviyesi (minimal/standart), max tool output karakteri.
   Tanınmayan modeller için güvenli varsayılanlar kullanılır.
7. **Döngü/sonsuz-loop koruması.** Maksimum adım sayısı (config'ten, varsayılan 15-20)
   ve aynı tool+args kombinasyonunun art arda tekrarını tespit edip kullanıcıya
   sorma/durdurma mantığı.

---

## 3. Tool Seti (İlk Sürüm)

| Tool | Açıklama | Onay gerekir mi |
|---|---|---|
| `read_file(path, start_line?, end_line?)` | Dosya oku | Hayır |
| `write_file(path, content)` | Yeni dosya oluştur/üzerine yaz | Evet |
| `edit_file(path, old_str, new_str)` | Bul-değiştir tarzı düzenleme | Evet |
| `list_dir(path)` | Dizin listele | Hayır |
| `glob(pattern)` | Dosya deseniyle arama | Hayır |
| `grep(pattern, path?)` | İçerik arama (ripgrep/grep) | Hayır |
| `run_shell(command)` | Bash komutu çalıştır (workdir içinde, timeout'lu) | Evet |
| `git_status` / `git_diff` | Git durumu göster | Hayır |

Tüm dosya/shell işlemleri **çalışma dizini (workdir) dışına çıkamaz** —
`safety/sandbox.py` path'leri normalize edip workdir prefix kontrolü yapar.
`run_shell` için tehlikeli komut kalıpları (rm -rf /, dd, mkfs vb.) ek onay ister.

---

## 4. Agent Döngüsü (Yüksek Seviye Akış)

1. Kullanıcı görevini terminalden yazar.
2. `context.py` mevcut history + sistem promptu + tool listesini birleştirip
   Ollama'ya gönderir (`stream=True`).
3. Model çıktısı streaming olarak ekrana yazılır; aynı anda `parser.py` bir
   tool-call bloğu arar.
4. Tool-call bulunduysa:
   - Yıkıcı işlemse kullanıcıdan onay istenir (`[E]vet/[H]ayır/[D]üzenle`).
   - Tool çalıştırılır, sonucu (kırpılmış) observation olarak history'ye eklenir.
   - Döngü 2. adıma döner.
5. Tool-call yoksa ve model "bitti/final answer" işareti verdiyse döngü sonlanır,
   nihai cevap kullanıcıya gösterilir.
6. Adım limiti aşılırsa veya tekrar eden döngü tespit edilirse kullanıcıya
   durum bildirilir ve devam edip etmeyeceği sorulur.

---

## 5. CLI Kullanımı (Hedef)

```bash
# Etkileşimli mod, mevcut dizinde, varsayılan modelle
lokal-ajan

# Belirli model ve workdir ile
lokal-ajan --model qwen2.5-coder:7b --workdir ~/projeler/foo

# Tek seferlik görev (non-interactive)
lokal-ajan run "src/ altındaki TODO yorumlarını listele" --workdir ~/projeler/foo

# Kullanılabilir Ollama modellerini listele
lokal-ajan models
```

Config dosyası `~/.config/lokal-ajan/config.toml`:
```toml
default_model = "qwen2.5-coder:7b"
ollama_host = "http://localhost:11434"
max_steps = 20
require_confirm_for = ["write_file", "edit_file", "run_shell"]
```

---

## 6. Masaüstü Launcher

### 6.1 Davranış
1. Kullanıcı masaüstündeki/uygulama menüsündeki "Lokal Ajan" ikonuna tıklar.
2. `launcher.py` (Tkinter) açılır:
   - Ollama'ya `GET /api/tags` isteği atıp yüklü modelleri dropdown'da listeler.
   - "Çalışma Klasörü Seç" butonu (`filedialog.askdirectory`).
   - "Başlat" butonu.
3. "Başlat"a basınca, sistemde bulunan bir terminal emülatörü tespit edilip
   (öncelik sırası: `x-terminal-emulator`, `gnome-terminal`, `konsole`, `xfce4-terminal`,
   `xterm`) şu şekilde açılır:
   ```
   <terminal> -- lokal-ajan --model "<seçilen_model>" --workdir "<seçilen_klasör>"
   ```
4. Launcher penceresi kapanır, ajan terminalde etkileşimli olarak çalışmaya başlar.

### 6.2 `.desktop` dosyası
```ini
[Desktop Entry]
Type=Application
Name=Lokal Ajan
Comment=Ollama tabanlı lokal agentic CLI başlatıcı
Exec=python3 /opt/lokal-ajan/launcher/launcher.py
Icon=/opt/lokal-ajan/launcher/icon.png
Terminal=false
Categories=Development;Utility;
```
Kurulum script'i (`scripts/install.sh`) bu dosyayı `~/.local/share/applications/`
içine kopyalar ve `chmod +x` uygular; ayrıca isteğe bağlı olarak `~/Desktop/`'a
da bir kopya koyar (dağıtıma göre `gio set metadata::trusted true` gerekebilir,
script bunu dener/hatasını yutar).

---

## 7. Kurulum ve Paketleme

- `pyproject.toml` ile pip paketleme, `entry_points` üzerinden `lokal-ajan` komutu.
- `scripts/install.sh`:
  1. Python venv oluşturur / mevcut ortamı kullanır.
  2. `pip install -e .` ile paketi kurar.
  3. `.desktop` dosyasını kopyalar, ikon yollarını günceller.
  4. `ripgrep` kurulu değilse uyarı basar (yoksa grep fallback zaten var).
  5. Ollama'nın çalışıp çalışmadığını kontrol eder (`curl localhost:11434`).

---

## 8. Fazlı Uygulama Planı (opencode'a verilecek sıra)

**Faz 1 — Çekirdek altyapı**
- Proje iskeleti, `pyproject.toml`, `ollama_client.py` (basit chat isteği, streaming).
- `config.py`, `model_profiles.py` (2-3 model için ilk profil).
- Basit CLI: sadece model ile sohbet, tool yok. Çalıştığını doğrula.

**Faz 2 — Tool sistemi ve parser**
- `tools/base.py`, `registry.py`, `fs_tools.py` (read/write/list/glob/grep).
- `parser.py`: JSON tool-call ayrıştırma + toleranslı fallback.
- `prompt.py`: minimal/standart sistem promptları, few-shot örnekler.
- Birim testler: bozuk JSON senaryoları için `test_parser.py`.

**Faz 3 — Agent döngüsü**
- `agent/loop.py`: ReAct döngüsü, adım limiti, tekrar tespiti.
- `history.py`, `context.py`: context sıkıştırma, tool çıktısı kırpma.
- `run_shell` tool'u + `safety/confirm.py`, `safety/sandbox.py`.
- Uçtan uca test: "bir dosya oluştur, içine yaz, oku" gibi basit görevler.

**Faz 4 — Terminal UX**
- `ui/console.py`: `rich` ile streaming çıktı, tool çağrılarını renkli/etiketli gösterme,
  onay promptları.
- `lokal-ajan run` (non-interactive) modu.
- `lokal-ajan models` komutu.

**Faz 5 — Masaüstü launcher**
- `launcher/launcher.py` (Tkinter): model listesi + klasör seçimi + başlat.
- `.desktop` dosyası ve `install.sh`.
- Farklı terminal emülatörlerinde manuel test.

**Faz 6 — Cilalama / opsiyonel**
- `git_tools.py`.
- Oturum kaydetme/devam ettirme (`--resume`).
- Daha fazla model profili + kullanıcıların kendi profillerini
  `~/.config/lokal-ajan/models.toml` ile override edebilmesi.

---

## 9. Kabul Kriterleri (her faz için genel)
- `lokal-ajan --model <ufak_model> --workdir <klasör>` komutu hatasız açılır.
- Model geçersiz/bozuk bir tool-call ürettiğinde uygulama çökmez, kullanıcıya
  anlaşılır bir mesaj gösterip devam eder veya nazikçe durur.
- Tüm dosya/shell işlemleri workdir dışına çıkamaz.
- Yıkıcı işlemler onay istemeden çalışmaz.
- Masaüstü launcher, Ollama kapalıyken de çökmeden anlamlı bir hata gösterir.

---

## 10. opencode'a Verilecek İlk Talimat (öneri)

> "Bu `plan.md` dosyasındaki Faz 1'i uygula: proje iskeletini oluştur, `ollama_client.py`
> içinde Ollama `/api/chat` endpoint'ine streaming istek atan basit bir fonksiyon yaz,
> ve `lokal-ajan` CLI komutunu tool'suz, sade bir sohbet döngüsü olarak çalışır hale
> getir. Bitince bana çalıştırma talimatı ver, ben test edeceğim, sonra Faz 2'ye geçeceğiz."

Fazları tek tek, birbiri ardına ve her fazdan sonra test ederek ilerletmen,
küçük modellerle çalışırken ortaya çıkacak sürpriz davranışları (bozuk JSON,
kısa context, tekrar eden döngüler) erken yakalamanı sağlar.
