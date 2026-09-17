# lokal-ajan

Ollama üzerinde çalışan lokal LLM'lerle çalışan, terminal tabanlı, tool-calling
yeteneğine sahip agentic bir CLI aracı. Özellikle **qwen3:0.6b, qwen3:1.7b,
qwen3:4b** gibi çok küçük/hafif modellerle güvenilir tool-call üretimi için
optimize edilmiştir (bkz. [`CHANGES_qwen3.md`](./CHANGES_qwen3.md)).

## Kurulum (Tek Satırla Hızlı Kurulum)

### Linux / macOS:
```bash
curl -fsSL https://raw.githubusercontent.com/ilhanakd-max/Local_Ajan/main/scripts/install.sh | bash
```

### Windows (PowerShell):
```powershell
powershell -c "irm https://raw.githubusercontent.com/ilhanakd-max/Local_Ajan/main/scripts/install.ps1 | iex"
```

*Kurulum tamamlandıktan sonra terminalde `localajan` yazarak uygulamayı başlatabilirsiniz.*

---

### Manuel Kurulum (Geliştiriciler İçin)

```bash
git clone https://github.com/ilhanakd-max/Local_Ajan.git
cd Local_Ajan
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Ollama'nın çalıştığından ve istediğiniz modelin indirilmiş olduğundan emin olun:

```bash
ollama pull qwen3:0.6b
ollama pull qwen3:1.7b
ollama serve   # zaten çalışmıyorsa
```

## Kullanım

```bash
# Etkileşimli mod
lokal-ajan --model qwen3:1.7b --workdir ~/projelerim/foo

# Tek seferlik görev
lokal-ajan run "src/ altındaki TODO yorumlarını listele" --model qwen3:1.7b --workdir ~/projelerim/foo

# Yüklü Ollama modellerini ve profillerini listele
lokal-ajan models

# Orkestratör modu: küçük/hızlı bir "beyin" model, ağır işleri daha büyük
# bir "işçi" modele devrediyor (delegate_task tool'u ile)
lokal-ajan --model qwen3:0.6b --worker-model qwen3:4b --workdir ~/projelerim/foo
```

Etkileşimli moddaki komutlar: `/model` (model değiştir), `/new` (oturumu
sıfırla), `exit`/`quit` (çık).

## Config

`~/.config/lokal-ajan/config.toml` (opsiyonel):

```toml
default_model = "qwen3:1.7b"
ollama_host = "http://localhost:11434"
max_steps = 20
require_confirm_for = ["write_file", "edit_file", "run_shell"]
```

## Masaüstü Launcher

```bash
bash scripts/install.sh
```

Uygulama menüsüne "Lokal Ajan" ikonu ekler; tıklandığında model + çalışma
klasörü seçilip bir terminalde ajan başlatılır.

## Güvenlik

- Tüm dosya/shell işlemleri **workdir dışına çıkamaz** (`safety/sandbox.py`).
- `write_file`, `edit_file`, `run_shell` her zaman kullanıcı onayı ister.
- Bilinen yıkıcı komut kalıpları (`rm -rf /`, `mkfs`, fork bomb, vb.) ek bir
  görsel uyarıyla işaretlenir.

## Geliştirme / Test

```bash
pip install -e .
pytest tests/ -v
```
