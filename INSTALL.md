# 📦 LocAi Installation Guide

Comprehensive installation instructions for **LocAi** across Windows, macOS, and Linux.

---

## 📋 Table of Contents
- [Prerequisites](#prerequisites)
- [🪟 Windows Installation](#-windows-installation)
- [🍎 macOS Installation](#-macos-installation)
- [🐧 Linux Installation (Ubuntu/Debian)](#-linux-installation-ubuntudebian)
- [📋 Supported & Recommended Models](#-supported--recommended-models)
- [💾 Configuration](#-configuration)
- [🔧 Troubleshooting](#-troubleshooting)
- [🚀 Next Steps](#-next-steps)

---

## Prerequisites

Before installing LocAi, ensure you have:
1. **Python 3.11+** installed (`python --version` or `python3 --version`)
2. **Ollama** installed and running for local model inference: [Download Ollama](https://ollama.ai/)
3. **pipx** (recommended for isolated CLI tools) or standard `pip`

---

## 🪟 Windows Installation

### Step 1: Install Python & pipx
Ensure Python 3.11+ is installed (check "Add python.exe to PATH" during installation).

Open PowerShell as Administrator or standard user:
```powershell
# Verify Python version
python --version

# Install pipx
python -m pip install --user pipx
python -m pipx ensurepath
```
*Note: Restart PowerShell or Windows Terminal after running `ensurepath`.*

### Step 2: Install and Start Ollama
1. Download installer from [ollama.ai](https://ollama.ai/).
2. Run the installer (Ollama starts as a Windows background service automatically).
3. Verify in PowerShell:
```powershell
ollama --version
```

### Step 3: Download a Recommended Model
```powershell
ollama pull qwen3:1.7b
```

### Step 4: Install LocAi
```powershell
pipx install https://github.com/ilhanakd-max/Local_Ajan/archive/refs/heads/main.zip
```

*Alternative via standard pip:*
```powershell
pip install https://github.com/ilhanakd-max/Local_Ajan/archive/refs/heads/main.zip
```

### Step 5: Start LocAi
```powershell
locai --model qwen3:1.7b --workdir D:\Projects\MyProject
```

---

## 🍎 macOS Installation

### Step 1: Install Python & pipx
Using [Homebrew](https://brew.sh/):
```bash
# Install Python 3.11+
brew install python@3.11

# Install pipx
brew install pipx
pipx ensurepath

# Refresh shell environment
source ~/.zprofile   # or ~/.bash_profile
```

### Step 2: Install Ollama
```bash
brew install --cask ollama
# Or download directly from https://ollama.ai/
```
Launch Ollama from your Applications folder.

### Step 3: Download a Model
```bash
ollama pull qwen3:1.7b
```

### Step 4: Install LocAi
```bash
pipx install https://github.com/ilhanakd-max/Local_Ajan/archive/refs/heads/main.zip
```

### Step 5: Start LocAi
```bash
locai --model qwen3:1.7b --workdir ~/projects/myapp
```

---

## 🐧 Linux Installation (Ubuntu/Debian)

### Step 1: Install Python & pipx
```bash
# Update repositories
sudo apt update

# Install Python 3.11+, venv, and pip
sudo apt install -y python3 python3-venv python3-pip pipx

# Ensure pipx path is configured
pipx ensurepath
source ~/.bashrc
```

### Step 2: Install Ollama
```bash
curl -fsSL https://ollama.ai/install.sh | sh
```
Start or verify Ollama service:
```bash
systemctl status ollama
# Or run manually in a terminal if not installed as service:
ollama serve
```

### Step 3: Download a Model
```bash
ollama pull qwen3:1.7b
```

### Step 4: Install LocAi
```bash
pipx install https://github.com/ilhanakd-max/Local_Ajan/archive/refs/heads/main.zip
```

### Step 5: Start LocAi
```bash
locai --model qwen3:1.7b --workdir ~/projects/myapp
```

---

## 📋 Supported & Recommended Models

LocAi is specially engineered and optimized for small and medium local models:

| Model | Parameter Size | Recommendation | Profile & Characteristics |
| :--- | :--- | :--- | :--- |
| **qwen3:0.6b** | ~400MB | ✅ Ultra Lightweight | Fastest, minimal RAM, ideal for rapid exploration |
| **qwen3:1.7b** | ~1.1GB | ⭐ **Recommended** | Perfect balance of low latency, agent reasoning & accuracy |
| **qwen3:4b** | ~2.6GB | ⭐ **Recommended** | Enhanced multi-step reasoning, highly capable |
| **qwen3:8b** | ~5.2GB | ⚠️ Moderate | Great for deep code analysis; requires 8GB+ RAM |
| **qwen3:14b / 32b** | 9GB - 20GB | 🚀 High Performance | Enterprise/desktop workstation grade |
| **llama3 / deepseek-r1** | Variable | ✅ Supported | Multi-provider and standard Ollama compatibility |

---

## 💾 Configuration

LocAi stores user preferences under `~/.lokal_ajan/` or system config path.

Example configuration (`~/.lokal_ajan/config.json` or command flags):
```json
{
  "default_model": "qwen3:1.7b",
  "ollama_host": "http://127.0.0.1:11434",
  "max_steps": 25,
  "shell_timeout": 30
}
```

You can view or update settings directly inside the interactive CLI:
```text
/model        - Switch model or provider
/profile      - View active model profile & optimizations
/session save - Save current session
/help         - List all commands
```

---

## 🔧 Troubleshooting

### Issue: `locai` or `pipx` command not found
**Solution:** Ensure the local bin folder is in your `$PATH`:
```bash
# Linux/macOS
export PATH="$HOME/.local/bin:$PATH"
source ~/.bashrc # or ~/.zshrc

# Windows
python -m pipx ensurepath
```

### Issue: Ollama connection refused (`Failed to connect to 127.0.0.1:11434`)
**Solution:**
1. Check if Ollama is running:
   ```bash
   curl http://127.0.0.1:11434/api/tags
   ```
2. Start Ollama:
   - **Linux / macOS:** Run `ollama serve` or check `systemctl status ollama`.
   - **Windows:** Search for "Ollama" in the Start Menu and launch the application.

### Issue: Model pull is slow or interrupted
**Solution:**
```bash
ollama pull -v qwen3:1.7b
```

---

## 🚀 Next Steps

- Explore usage examples in [README.md](README.md)
- Learn how to contribute in [CONTRIBUTING.md](CONTRIBUTING.md)
- Report issues on [GitHub Issues](https://github.com/ilhanakd-max/Local_Ajan/issues)
- Join discussions on [GitHub Discussions](https://github.com/ilhanakd-max/Local_Ajan/discussions)
