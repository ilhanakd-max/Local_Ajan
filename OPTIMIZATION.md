# 🚀 LocAi Repository SEO & Discoverability Guide

Bu doküman, **LocAi (`Local_Ajan`)** deposunun GitHub arama algoritmasında (GitHub Search Engine) ve arama motorlarında (Google, Bing) en üst sıralarda yer alması, topluluk etkileşiminin artırılması ve projenin keşfedilebilirliği için uygulanması gereken adımları içerir.

---

## 📋 Hızlı Kontrol Listesi (Checklist)

### 1. GitHub Repository Ayarları (En Yüksek Öncelik ⭐)
- [ ] **Repository Topics (Etiketler)** eklendi.
- [ ] **About / Açıklama** optimize edildi (anahtar kelime odaklı).
- [ ] **Website URL** eklendi (`https://locai-cli.netlify.app/`).
- [ ] **GitHub Discussions** etkinleştirildi.
- [ ] **Social Preview Image** (sosyal medya önizleme görseli) yüklendi.

### 2. Dokümantasyon & Topluluk Standartları
- [x] Detaylı ve iki dilli (TR/EN) `README.md`
- [x] Rozetler (Badges) eklendi (Python, License, Stars, Ollama, PRs)
- [x] `INSTALL.md` (Çapraz platform kurulum rehberi)
- [x] `CONTRIBUTING.md` (Katkı rehberi & standartlar)
- [x] `.github/pull_request_template.md` (PR şablonu)
- [x] `.github/ISSUE_TEMPLATE/bug_report.md` (Hata şablonu)
- [x] `.github/ISSUE_TEMPLATE/feature_request.md` (Özellik önerisi şablonu)

---

## 🎯 Adım Adım Uygulama Rehberi

### Adım 1: Repository Topics (Etiketler) Ekleme ⭐

GitHub arama motoru, depo etiketlerine (`topics`) çok yüksek ağırlık verir.

1. Deponuzun ana sayfasına gidin: `https://github.com/ilhanakd-max/Local_Ajan`
2. Sağ tarafta yer alan **About** kutusunun yanındaki ⚙️ (dişli) simgesine tıklayın.
3. **Topics** alanına aşağıdaki etiketleri tek tek yapıştırıp Enter'a basın:

```text
ollama
ai-agents
local-llm
qwen
qwen3
coding-assistant
terminal-tool
python
agent
llm
agentic-ai
developer-tools
cli
```

4. **Save changes** butonuna tıklayın.

---

### Adım 2: Depo Açıklamasını (About Section) Güçlendirme

GitHub aramasında ilk iki satır snippet olarak gösterilir. Bu nedenle açıklama hem net hem de aranan terimleri içermelidir:

- **Önerilen Açıklama (Description):**
  > `LocAi - Lightweight terminal-based AI coding agent runtime for local LLMs (Ollama, Qwen3). Read files, edit code, run commands, and execute multi-step tasks.`

- **Website:**
  > `https://locai-cli.netlify.app/`

- **Include in the home page:**
  - ✅ Releases
  - ✅ Packages
  - ✅ Environments

---

### Adım 3: GitHub Discussions Etkinleştirme

Discussions açık olan depolar, GitHub Explore ve arama indekslerinde daha dinamik bir topluluk sinyali verir:

1. Depo sayfasında **Settings** sekmesine tıklayın.
2. **General** altında **Features** bölümüne kaydırın.
3. **Discussions** kutucuğunu işaretleyin (Set up discussions).
4. `Announcements`, `General`, `Ideas`, `Q&A` kategorilerini hazır olarak etkinleştirin.

---

### Adım 4: Social Preview Görseli Yükleme

Depo bağlantısı Twitter, LinkedIn, Reddit veya Discord'da paylaşıldığında dikkat çekici bir kart görseli görünmesi için:

1. **Settings → General → Social preview** bölümüne gidin.
2. **Edit → Upload an image** seçeneğini seçin.
3. Projede hazır olarak oluşturulan tam 1280x640 piksel boyutundaki `assets/social_preview.png` görselini yükleyin.


---

### Adım 5: GitHub Releases ve Tagleme

GitHub aramalarında sürümlere (`Releases`) sahip depolar daha güvenilir ve popüler kabul edilir:

1. Depo ana sayfasında **Releases → Create a new release** seçeneğine tıklayın.
2. Tag: `v0.3.16`
3. Release Title: `LocAi v0.3.16 - Small Models. Real Agents.`
4. [CHANGES_qwen3.md](CHANGES_qwen3.md) içeriğini kopyalayarak sürüm notu olarak yayınlayın.

---

## 📈 Beklenen Sonuçlar ve SEO Etkisi

| Kriter | Öncesi | Optimizasyon Sonrası |
| :--- | :--- | :--- |
| **Arama Terimleri** | Yalnızca "Local Ajan" | "ollama coding agent", "local llm cli", "qwen3 agent", "ai coding assistant" |
| **Topluluk Sağlığı (Community Health)** | %30 | **%100** (PR & Issue şablonları, Contributing, Code of Conduct) |
| **Dış Bağlantı & Paylaşım** | Metin linki | Zengin önizleme kartı (OG Image & Description) |
| **Katkıcı Katılımı** | Belirsiz | Standart kurallar ve kolay kurulum (`INSTALL.md`) |
