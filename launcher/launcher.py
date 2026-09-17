import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import urllib.request
import json
import subprocess
import os
import sys

from pathlib import Path

STATE_FILE = Path(os.environ.get(
    "LOKAL_AJAN_STATE",
    Path.home() / ".config" / "lokal-ajan" / "state.json",
))

def load_launcher_state(path=None):
    state_file = path or STATE_FILE
    if not os.path.isfile(state_file):
        return {}
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_launcher_state(state: dict, path=None):
    state_file = path or STATE_FILE
    try:
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        current = load_launcher_state(state_file)
        current.update(state)
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def get_ollama_models(host="http://localhost:11434"):
    models = []
    try:
        req = urllib.request.Request(f"{host}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode())
            models = [m["name"] for m in data.get("models", [])]
    except Exception as e:
        pass
    
    external_models = [
        "groq/openai/gpt-oss-120b",
        "groq/openai/gpt-oss-20b",
        "groq/qwen/qwen3.8-27b",
        "openrouter/free",
        "ninerouter/free-model",
    ]
    return external_models + models

class LauncherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Lokal Ajan Başlatıcı")
        self.root.geometry("440x390")
        self.root.minsize(420, 370)
        self.root.resizable(True, True)
        
        self.models = get_ollama_models()
        self.saved_state = load_launcher_state()
        
        # Orchestrator Mode Toggle
        saved_orchestrator = self.saved_state.get("orchestrator", False)
        self.orchestrator_var = tk.BooleanVar(value=saved_orchestrator)
        self.chk_orchestrator = ttk.Checkbutton(
            root, text="Orkestratör Modu (Beyin + İşçi)", 
            variable=self.orchestrator_var, 
            command=self.toggle_orchestrator
        )
        self.chk_orchestrator.pack(pady=(12, 3))

        # Fast GPU Mode Toggle (%100 GPU - 8K context for small models)
        saved_gpu_mode = self.saved_state.get("gpu_mode", False)
        self.gpu_mode_var = tk.BooleanVar(value=saved_gpu_mode)
        self.chk_gpu_mode = ttk.Checkbutton(
            root, text="⚡ Hızlı GPU Modu (Küçük Modeller %100 GPU - 8K)", 
            variable=self.gpu_mode_var
        )
        self.chk_gpu_mode.pack(pady=(2, 2))
        
        # Ponytail Mode Toggle
        saved_ponytail = self.saved_state.get("ponytail", False)
        self.ponytail_var = tk.BooleanVar(value=saved_ponytail)
        self.chk_ponytail = ttk.Checkbutton(
            root, text="Ponytail (Lazy Senior Dev) Modu", 
            variable=self.ponytail_var
        )
        self.chk_ponytail.pack(pady=(2, 6))
        
        # Main Model (Brain)
        self.lbl_model = tk.Label(root, text="Ollama Modeli (Beyin):")
        self.lbl_model.pack(pady=(5, 0))
        self.model_var = tk.StringVar()
        saved_model = self.saved_state.get("model")
        if self.models:
            initial_model = saved_model if (saved_model and saved_model in self.models) else self.models[0]
            self.model_var.set(initial_model)
            self.model_dropdown = ttk.Combobox(root, textvariable=self.model_var, values=self.models, state="readonly")
        else:
            self.model_var.set(saved_model or "Modeller alınamadı. Manuel yazın:")
            self.model_dropdown = ttk.Entry(root, textvariable=self.model_var)
        self.model_dropdown.pack(pady=5, fill=tk.X, padx=20)
        
        # Worker Model
        self.lbl_worker = tk.Label(root, text="İşçi Modeli (Kodlama):")
        self.worker_var = tk.StringVar()
        saved_worker = self.saved_state.get("worker_model")
        if self.models:
            initial_worker = saved_worker if (saved_worker and saved_worker in self.models) else self.models[0]
            self.worker_var.set(initial_worker)
            self.worker_dropdown = ttk.Combobox(root, textvariable=self.worker_var, values=self.models, state="readonly")
        else:
            self.worker_var.set(saved_worker or "Modeller alınamadı. Manuel yazın:")
            self.worker_dropdown = ttk.Entry(root, textvariable=self.worker_var)
            
        # Workdir (önceki açılışta kaydedilmiş çalışma klasörü varsa onu kullan)
        tk.Label(root, text="Çalışma Klasörü:").pack(pady=(10, 0))
        saved_workdir = self.saved_state.get("workdir")
        default_workdir = saved_workdir if (saved_workdir and os.path.isdir(saved_workdir)) else os.path.expanduser("~")
        self.workdir_var = tk.StringVar(value=default_workdir)
        
        frame = tk.Frame(root)
        frame.pack(fill=tk.X, padx=20, pady=5)
        
        self.workdir_entry = ttk.Entry(frame, textvariable=self.workdir_var)
        self.workdir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.btn_browse = ttk.Button(frame, text="Seç...", command=self.browse_dir)
        self.btn_browse.pack(side=tk.RIGHT, padx=(5, 0))
        
        # Start
        self.btn_start = ttk.Button(root, text="Başlat", command=self.start_agent)
        self.btn_start.pack(pady=15)
        
        self.toggle_orchestrator() # initial state
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def persist_current_state(self):
        state = {
            "workdir": self.workdir_var.get().strip(),
            "model": self.model_var.get().strip(),
            "worker_model": self.worker_var.get().strip(),
            "orchestrator": bool(self.orchestrator_var.get()),
            "gpu_mode": bool(self.gpu_mode_var.get()),
            "ponytail": bool(self.ponytail_var.get()),
        }
        save_launcher_state(state)

    def on_close(self):
        self.persist_current_state()
        self.root.destroy()
        
    def toggle_orchestrator(self):
        if self.orchestrator_var.get():
            self.lbl_worker.pack(after=self.model_dropdown, pady=(5, 0))
            self.worker_dropdown.pack(after=self.lbl_worker, pady=5, fill=tk.X, padx=20)
            self.lbl_model.config(text="Ollama Modeli (Beyin):")
            self.root.geometry("450x480")
            self.root.minsize(430, 460)
        else:
            self.lbl_worker.pack_forget()
            self.worker_dropdown.pack_forget()
            self.lbl_model.config(text="Ollama Modeli:")
            self.root.geometry("450x420")
            self.root.minsize(430, 400)

    def browse_dir(self):
        initial = self.workdir_var.get().strip()
        if not os.path.isdir(initial):
            initial = os.path.expanduser("~")
        dir_selected = filedialog.askdirectory(initialdir=initial)
        if dir_selected:
            self.workdir_var.set(dir_selected)
            self.persist_current_state()
            
    def get_terminal_emulator(self):
        terms = ["x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal", "xterm"]
        for t in terms:
            if subprocess.run(["which", t], capture_output=True).returncode == 0:
                return t
        return None

    def _show_install_dialog(self, project_dir: str):
        """'.venv' yoksa kullanıcıya kurulum seçeneği sunan özel diyalog."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Kurulum Gerekli")
        dlg.resizable(False, False)
        dlg.grab_set()  # modal

        # İkon + başlık
        tk.Label(dlg, text="⚠  Kurulum Gerekli",
                 font=("Helvetica", 12, "bold"), fg="#c0392b").pack(pady=(18, 4), padx=24)

        tk.Label(
            dlg,
            text="Bağımlılıklar henüz yüklenmemiş.\n"
                 "'Şimdi Kur' butonuna basarak kurulumu\n"
                 "otomatik olarak başlatabilirsiniz.",
            justify="center",
        ).pack(pady=(0, 12), padx=24)

        # Komut önizleme
        frame = tk.Frame(dlg, bg="#2d2d2d", bd=1, relief="solid")
        frame.pack(fill="x", padx=20, pady=(0, 16))
        tk.Label(
            frame,
            text=f"cd {project_dir}\nbash scripts/install.sh",
            bg="#2d2d2d", fg="#a8ff78",
            font=("Monospace", 9),
            justify="left",
        ).pack(padx=10, pady=8, anchor="w")

        btn_frame = tk.Frame(dlg)
        btn_frame.pack(pady=(0, 16))

        def run_install():
            term = self.get_terminal_emulator()
            if not term:
                messagebox.showerror("Hata", "Terminale emulator bulunamadı.\n"
                                             "Lütfen terminali kendiniz açıp\n"
                                             "scripts/install.sh çalıştırın.",
                                     parent=dlg)
                return
            install_cmd = f'cd "{project_dir}" && bash scripts/install.sh'
            try:
                if term == "gnome-terminal":
                    subprocess.Popen([term, "--", "bash", "-c", f"{install_cmd}; exec bash"])
                else:
                    subprocess.Popen([term, "-e", f'bash -c \'{install_cmd}; exec bash\''])
                dlg.destroy()
            except Exception as e:
                messagebox.showerror("Hata", f"Terminal açılamadı: {e}", parent=dlg)

        ttk.Button(btn_frame, text="✔  Şimdi Kur", command=run_install).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="İptal", command=dlg.destroy).pack(side="left", padx=6)

    def start_agent(self):
        model = self.model_var.get().strip()
        workdir = self.workdir_var.get().strip()
        
        if not model or "Modeller alınamadı" in model:
            messagebox.showerror("Hata", "Lütfen bir model seçin veya yazın.")
            return

        if not workdir:
            workdir = os.path.expanduser("~")
            self.workdir_var.set(workdir)

        if not os.path.isdir(workdir):
            messagebox.showerror("Hata", f"Seçilen çalışma klasörü bulunamadı:\n{workdir}")
            return
            
        self.persist_current_state()
            
        term = self.get_terminal_emulator()
        if not term:
            messagebox.showerror("Hata", "Sistemde desteklenen bir terminal bulunamadı.")
            return
            
        # Proje dizini ve Python yollarını hesapla
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        src_dir = os.path.join(project_dir, "src")
        venv_python = os.path.join(project_dir, ".venv", "bin", "python3")
        
        # .venv varsa onun python'unu kullan; yoksa kurulum yapılmamış demektir.
        if os.path.exists(venv_python):
            python_bin = venv_python
        else:
            self._show_install_dialog(project_dir)
            return
        
        # PYTHONPATH ile src/ dizinini ekleyerek doğrudan modülü çalıştır.
        # Tırnak işaretleri: model ve workdir'de boşluk olabilir.
        cmd = f'PYTHONPATH="{src_dir}" "{python_bin}" -m lokal_ajan.cli --model "{model}" --workdir "{workdir}"'

        if self.orchestrator_var.get():
            worker = self.worker_var.get()
            if worker and "Modeller alınamadı" not in worker:
                cmd += f' --worker-model "{worker}"'

        if self.gpu_mode_var.get():
            cmd += ' --gpu-mode'

        
        try:
            if term == "gnome-terminal":
                subprocess.Popen([term, "--", "bash", "-c", f"{cmd}; exec bash"])
            elif term == "xfce4-terminal":
                subprocess.Popen([term, "-e", f'bash -c \'{cmd}; exec bash\''])
            else:
                subprocess.Popen([term, "-e", f'bash -c \'{cmd}; exec bash\''])
            self.root.destroy()
        except Exception as e:
            messagebox.showerror("Hata", f"Başlatılamadı: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = LauncherApp(root)
    root.mainloop()
