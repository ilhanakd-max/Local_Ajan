#!/bin/bash

echo "Lokal Ajan kuruluyor..."

# 1. Virtual Environment
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

# 2. Kurulum
pip install -e .

# 3. .desktop dosyasını kullanıcı klasörüne kopyala
mkdir -p ~/.local/share/applications/
DESKTOP_FILE=~/.local/share/applications/lokal-ajan.desktop

# Exec yolunu güncelleyelim ki yerel repodan çalışsın
LAUNCHER_PATH="$(pwd)/launcher/launcher.py"
cat launcher/lokal-ajan.desktop | sed "s|Exec=python3 /opt/lokal-ajan/launcher/launcher.py|Exec=python3 $LAUNCHER_PATH|g" > $DESKTOP_FILE
chmod +x $DESKTOP_FILE

echo ".desktop dosyası ~/.local/share/applications/ içine kopyalandı."

# 4. Ripgrep kontrol
if ! command -v rg &> /dev/null; then
    echo "Uyarı: 'ripgrep' (rg) bulunamadı. Arama aracı grep'e düşecektir."
fi

# 5. Ollama kontrol
if curl -s http://localhost:11434/api/tags &> /dev/null; then
    echo "Ollama servisi çalışıyor."
else
    echo "Uyarı: Ollama servisi şu an http://localhost:11434 adresinde yanıt vermiyor."
fi

echo "Kurulum tamamlandı! Ajanı terminalden 'source .venv/bin/activate && lokal-ajan' ile veya uygulama menüsünden 'Lokal Ajan' ile başlatabilirsiniz."
