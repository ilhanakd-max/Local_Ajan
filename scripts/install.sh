#!/bin/bash
set -e

echo "🚀 Lokal Ajan kuruluyor..."

# Proje dizininde olup olmadığımızı kontrol et
if [ ! -f "pyproject.toml" ]; then
    echo "📦 GitHub'dan proje indiriliyor..."
    INSTALL_DIR="$HOME/.lokal-ajan"
    if [ -d "$INSTALL_DIR" ]; then
        echo "🔄 Mevcut kurulum güncelleniyor..."
        cd "$INSTALL_DIR"
        git pull origin main
    else
        git clone https://github.com/ilhanakd-max/Local_Ajan.git "$INSTALL_DIR"
        cd "$INSTALL_DIR"
    fi
else
    INSTALL_DIR="$(pwd)"
fi

echo "🐍 Python sanal ortamı oluşturuluyor..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

source .venv/bin/activate
echo "📦 Bağımlılıklar yükleniyor..."
pip install -e .

echo "🖥️ Masaüstü kısayolu oluşturuluyor..."
mkdir -p ~/.local/share/applications/
DESKTOP_FILE=~/.local/share/applications/lokal-ajan.desktop

LAUNCHER_PATH="$INSTALL_DIR/launcher/launcher.py"
if [ -f "launcher/lokal-ajan.desktop" ]; then
    cat launcher/lokal-ajan.desktop | sed "s|Exec=python3 /opt/lokal-ajan/launcher/launcher.py|Exec=python3 $LAUNCHER_PATH|g" > $DESKTOP_FILE
    chmod +x $DESKTOP_FILE
    echo "✅ .desktop dosyası oluşturuldu."
fi

echo "🔗 Terminal 'localajan' kısayolu ayarlanıyor..."
# Remove old alias if exists
sed -i '/alias localajan=/d' ~/.bashrc
sed -i '/alias localajan=/d' ~/.zshrc 2>/dev/null || true

echo "alias localajan='$INSTALL_DIR/.venv/bin/python3 -m lokal_ajan.cli'" >> ~/.bashrc
if [ -f ~/.zshrc ]; then
    echo "alias localajan='$INSTALL_DIR/.venv/bin/python3 -m lokal_ajan.cli'" >> ~/.zshrc
fi

echo "🔍 Gereksinimler kontrol ediliyor..."
if ! command -v rg &> /dev/null; then
    echo "⚠️ Uyarı: 'ripgrep' (rg) bulunamadı. Kuruluyor..."
    if command -v apt-get &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y ripgrep
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y ripgrep
    elif command -v pacman &> /dev/null; then
        sudo pacman -S --noconfirm ripgrep
    else
        echo "❌ Paket yöneticisi bulunamadı. Ripgrep'i manuel kurmalısınız."
    fi
else
    echo "✅ ripgrep (rg) yüklü."
fi

if ! command -v ollama &> /dev/null; then
    echo "⚠️ Uyarı: Ollama bulunamadı. Kuruluyor..."
    curl -fsSL https://ollama.com/install.sh | sh
else
    echo "✅ Ollama yüklü."
    if curl -s http://localhost:11434/api/tags &> /dev/null; then
        echo "✅ Ollama servisi çalışıyor."
    else
        echo "⚠️ Uyarı: Ollama servisi şu an yanıt vermiyor. Lütfen 'ollama serve' komutuyla başlatın."
    fi
fi

echo ""
echo "🎉 KURULUM BAŞARIYLA TAMAMLANDI! 🎉"
echo "👉 Terminalinizi yeniden başlatın veya şu komutu çalıştırın:"
echo "    source ~/.bashrc"
echo "👉 Ardından istediğiniz her yerde şu komutla ajanı başlatabilirsiniz:"
echo "    localajan"
