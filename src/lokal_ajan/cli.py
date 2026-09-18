import typer
from rich.prompt import Prompt
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.formatted_text import HTML
import os
from lokal_ajan.config import load_config
from lokal_ajan.llm.model_profiles import get_profile_for_model, PROFILES
from lokal_ajan.agent.loop import AgentLoop
from lokal_ajan.ui.console import console

app = typer.Typer(help="Ollama tabanlı lokal agentic CLI aracı")

def switch_model(agent: AgentLoop, config):
    """Ollama ve Harici API modellerini listele ve kullanıcının seçtiği modele geç."""
    from lokal_ajan.llm.ollama_client import list_ollama_models
    
    external_models = [
        "openrouter/free",
    ]
    
    ollama_models = list_ollama_models(config.ollama_host) or []
    all_models = external_models + ollama_models

    console.print("\n[bold green]Mevcut Modeller:[/bold green]")
    for i, m in enumerate(all_models, 1):
        marker = " [yellow]◄ aktif[/yellow]" if m == agent.model_name else ""
        category = "[blue][Groq/Cloud][/blue] " if m in external_models else "[cyan][Ollama][/cyan] "
        console.print(f"  [cyan]{i}[/cyan]. {category}{m}{marker}")
    
    choice = Prompt.ask("\nModel numarası veya adı seçin (iptal için boş bırakın)")
    
    if not choice.strip():
        console.print("[dim]İptal edildi.[/dim]")
        return
    
    val = choice.strip()
    if val.isdigit():
        idx = int(val) - 1
        if 0 <= idx < len(all_models):
            new_model = all_models[idx]
        else:
            console.print("[bold red]Geçersiz seçim numarası.[/bold red]")
            return
    else:
        new_model = val
    
    if new_model == agent.model_name:
        console.print(f"[dim]Zaten [green]{new_model}[/green] kullanılıyor.[/dim]")
        return
    
    if new_model.startswith("openrouter/"):
        ensure_openrouter_key(config)
        agent.config.openrouter_api_key = config.openrouter_api_key
        
    new_profile = get_profile_for_model(new_model, ollama_host=config.ollama_host)
    agent.update_model(new_model, new_profile)
    
    from lokal_ajan.llm.ollama_client import free_unused_models, preload_model
    free_unused_models(new_model, agent.worker_model, config.ollama_host)
    
    # Yerel Ollama modellerinde ilk istekte 'cold-start' ve timeout yaşanmaması için
    # modeli arka planda önceden RAM'e yüklüyoruz (warmup).
    if not (new_model.startswith("openrouter/") or new_model.startswith("groq/") or new_model.startswith("ninerouter/")):
        import threading
        threading.Thread(
            target=preload_model,
            args=(new_model, config.ollama_host),
            daemon=True
        ).start()

    try:
        from lokal_ajan.config import save_state
        save_state({"model": new_model})
    except Exception:
        pass
    
    console.print(f"\n[bold green]✓[/bold green] Model değiştirildi: [green]{new_model}[/green] (Context: {new_profile.num_ctx}, Temp: {new_profile.temperature})")
    console.print("[dim]Sistem promptu yeni profile göre güncellendi, sohbete devam edebilirsiniz.[/dim]\n")

_prompt_session = None

def get_user_prompt(prompt_label: str = "Sen") -> str:
    """
    Prompts user for input. Uses prompt_toolkit to natively handle
    multiline pasting without truncation, while providing arrow key history.
    """
    global _prompt_session
    if _prompt_session is None:
        history = FileHistory(os.path.expanduser("~/.lokal_ajan_history"))
        _prompt_session = PromptSession(history=history)
    
    try:
        # Use HTML for styling similar to rich
        formatted_prompt = HTML(f"<ansimagenta><b>{prompt_label}</b></ansimagenta>: ")
        # prompt_toolkit automatically handles pasted multiline text gracefully
        text = _prompt_session.prompt(formatted_prompt)
        return text.strip()
    except (EOFError, KeyboardInterrupt):
        raise

def ensure_openrouter_key(config):
    if not config.openrouter_api_key:
        console.print("\n[bold yellow]OpenRouter API Anahtarı Gerekli![/bold yellow]")
        console.print("İlk kullanımınız olduğu için ücretsiz modelleri kullanabilmek adına API anahtarı gereklidir.")
        console.print("Anahtarınızı ücretsiz olarak şu adresten alabilirsiniz: [cyan]https://openrouter.ai/keys[/cyan]")
        key = Prompt.ask("Lütfen OpenRouter API anahtarınızı yapıştırın")
        if key.strip():
            config.openrouter_api_key = key.strip()
            from lokal_ajan.config import CONFIG_PATH
            try:
                CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(CONFIG_PATH, "a", encoding="utf-8") as f:
                    f.write(f'\nopenrouter_api_key = "{key.strip()}"\n')
                console.print("[green]API anahtarı config dosyasına başarıyla kaydedildi![/green]\n")
            except Exception as e:
                console.print(f"[red]Anahtar kaydedilemedi: {e}[/red]\n")
        else:
            console.print("[red]Anahtar girilmedi. İşlem başarısız olabilir.[/red]\n")

def check_for_updates():
    import importlib.metadata
    import httpx
    import re
    try:
        current_version = importlib.metadata.version("lokal-ajan")
        resp = httpx.get("https://raw.githubusercontent.com/ilhanakd-max/Local_Ajan/main/pyproject.toml", timeout=1.5)
        if resp.status_code == 200:
            match = re.search(r'version\s*=\s*"([^"]+)"', resp.text)
            if match:
                remote_version = match.group(1)
                
                def parse_v(v):
                    return tuple(map(int, v.split(".")))
                
                if parse_v(remote_version) > parse_v(current_version):
                    return remote_version
    except Exception:
        pass
    return None


def normalize_cmd(text: str) -> str:
    """Strips leading and trailing slashes and lowercases command for flexible input."""
    t = text.strip()
    while t.startswith("/"):
        t = t[1:].strip()
    while t.endswith("/"):
        t = t[:-1].strip()
    return t.lower()


def show_help():
    """Displays a beautifully formatted cheat sheet of all commands and shortcuts."""
    from rich.table import Table
    from rich.panel import Panel

    table = Table(show_header=True, header_style="bold magenta", expand=True)
    table.add_column("Komut / Kısayol", style="bold cyan", width=30)
    table.add_column("Açıklama", style="white")

    table.add_row("help/  veya  /help", "Bu yardım tablosunu ve tüm kısayolları listeler.")
    table.add_row("session save/  veya  /session save", "Oturumu otomatik isimle (veya /session save <ad>) kaydeder.")
    table.add_row("session load/  veya  /session load", "Kayıtlı oturumları ok tuşlarıyla (↑ / ↓) seçip yükler.")
    table.add_row("session list/  veya  /session list", "Projedeki tüm kayıtlı oturumları listeler.")
    table.add_row("model/  veya  /model", "Modeli değiştirir (sohbet geçmişi korunarak aktarılır).")
    table.add_row("new/  veya  /new", "Mevcut sohbeti ve oturumu sıfırlayıp temiz sayfa açar.")
    table.add_row("ponytail/  veya  /ponytail", "Tembel Kıdemli Yazılımcı (minimalist kod) modunu açar/kapatır.")
    table.add_row("exit  veya  quit,  /q", "Uygulamadan çıkar.")
    
    console.print()
    console.print(Panel(table, title="[bold green]Lokal Ajan Kısayolları ve Fonksiyonları[/bold green]", border_style="cyan"))
    
    cli_table = Table(show_header=True, header_style="bold yellow", expand=True)
    cli_table.add_column("Terminal Parametresi", style="bold yellow", width=30)
    cli_table.add_column("İşlev", style="white")
    cli_table.add_row("localajan", "Normal başlatma (varsa önceki oturumu otomatik devam ettirir)")
    cli_table.add_row("localajan --new (-n)", "Önceki oturumu yok sayarak sıfırdan başlar")
    cli_table.add_row("localajan --session <ad>", "Belirli bir oturumu yükler")
    cli_table.add_row("localajan --model <model>", "Belirli bir model ile başlatır")
    cli_table.add_row("localajan --gpu-mode (-g)", "Küçük modellerde %100 GPU hızlandırmasını açar (8K Context)")
    cli_table.add_row("localajan update", "Uygulamayı GitHub'dan en son sürüme günceller")
    console.print(Panel(cli_table, title="[bold yellow]Terminal Başlatma Parametreleri[/bold yellow]", border_style="yellow"))
    console.print()


def start_interactive_session(model: str, workdir: str, worker_model: str = None, gpu_mode: bool = False, session_name: str = "default", new_session: bool = False):
    workdir = os.path.abspath(workdir)
    config = load_config()
    
    from lokal_ajan.config import load_state, save_state
    saved = load_state()
    saved_model = saved.get("model")
    target_model = model or saved_model or config.default_model

    # If target_model is an Ollama model, check if it exists or fallback to an installed one
    if not target_model.startswith("openrouter/") and not target_model.startswith("groq/"):
        from lokal_ajan.llm.ollama_client import list_ollama_models
        installed_ollama = list_ollama_models(config.ollama_host)
        if installed_ollama and target_model not in installed_ollama:
            old_model = target_model
            if saved_model and saved_model in installed_ollama:
                target_model = saved_model
            else:
                target_model = installed_ollama[0]
            console.print(f"[dim yellow]ℹ '{old_model}' sistemde bulunamadı, yüklü model seçildi: [bold green]{target_model}[/bold green][/dim yellow]")
    
    if target_model.startswith("openrouter/") or (worker_model and worker_model.startswith("openrouter/")):
        ensure_openrouter_key(config)
        
    profile = get_profile_for_model(target_model, ollama_host=config.ollama_host)
    
    if gpu_mode and profile.num_ctx > 8192:
        profile = profile.model_copy(update={"num_ctx": 8192})
    
    LOGO = r"""
    __          __          __   ___    _           
   / /   ____  / /______ _ / /  /   |  (_)___ _____ 
  / /   / __ \/ //_/ __ `/ /   / /| | / / __ `/ __ \
 / /___/ /_/ / ,< / /_/ / /   / ___ |/ / /_/ / / / /
/_____/\____/_/|_|\__,_/_/   /_/  |_/ /\__,_/_/ /_/ 
                                 /___/              
"""
    console.print(f"[bold cyan]{LOGO}[/bold cyan]")
    
    # Check for updates
    import threading
    def update_checker_thread():
        new_v = check_for_updates()
        if new_v:
            console.print(f"\n[bold yellow]🎉 Yeni bir sürüm ({new_v}) mevcut![/bold yellow]")
            console.print("[yellow]Yüklemek için terminalden çıkıp şunu çalıştırın: [bold white]localajan update[/bold white][/yellow]\n")
            
    t = threading.Thread(target=update_checker_thread)
    t.daemon = True
    t.start()
    
    console.print(f"[bold blue]Lokal Ajan[/bold blue] başlatılıyor...")
    if gpu_mode:
        console.print("[bold yellow]⚡ Hızlı GPU Modu Aktif (8K Context / %100 GPU Hızlandırma)[/bold yellow]")
        
    if worker_model:
        console.print(f"Mod (Orkestratör): Beyin=[green]{target_model}[/green], İşçi=[green]{worker_model}[/green]")
    else:
        console.print(f"Model: [green]{target_model}[/green] (Context: {profile.num_ctx}, Temp: {profile.temperature})")
    
    console.print(f"Çalışma Dizini: [yellow]{workdir}[/yellow]")
    console.print("Yardım ve kısayol listesi: [bold cyan]help/[/bold cyan]")
    console.print("Oturumu kaydet: [bold cyan]session save/[/bold cyan]  |  Yükle (ok tuşlarıyla): [bold cyan]session load/[/bold cyan]")
    console.print("Model değiştir: [bold cyan]model/[/bold cyan]  |  Sıfırla: [bold cyan]new/[/bold cyan]  |  Çıkış: [bold cyan]exit[/bold cyan]\n")
    
    # Arka planda kullanılmayan diğer Ollama modellerini bellekten boşalt
    from lokal_ajan.llm.ollama_client import free_unused_models
    free_unused_models(target_model, worker_model, config.ollama_host)
    
    # Son kullanılan ayarları kaydet
    try:
        from lokal_ajan.config import load_state, save_state
        saved = load_state()
        ponytail_enabled = saved.get("ponytail", False)
        
        state_data = {"workdir": workdir, "model": target_model, "gpu_mode": gpu_mode, "ponytail": ponytail_enabled}
        if worker_model:
            state_data["worker_model"] = worker_model
            state_data["orchestrator"] = True
        save_state(state_data)
    except Exception:
        ponytail_enabled = False
    
    agent = AgentLoop(
        model_name=target_model,
        profile=profile,
        host=config.ollama_host,
        workdir=workdir,
        config=config,
        worker_model=worker_model,
        auto_confirm=True,
        gpu_mode=gpu_mode,
        ponytail_enabled=ponytail_enabled,
        session_name=session_name
    )
    
    from lokal_ajan.agent.session import load_session, save_session, list_sessions, delete_session
    if not new_session:
        saved_session = load_session(workdir, session_name)
        if saved_session and saved_session.get("messages"):
            agent.load_session_data(saved_session["messages"])
            msg_count = len([m for m in saved_session["messages"] if m.get("role") != "system"])
            prev_model = saved_session.get("model_name", "bilinmeyen")
            if prev_model != target_model:
                console.print(f"[bold green]✓[/bold green] Önceki oturum yüklendi: [cyan]{msg_count} mesaj[/cyan] (Önceki model: [dim]{prev_model}[/dim] ➔ Şimdiki model: [green]{target_model}[/green])")
            else:
                console.print(f"[bold green]✓[/bold green] Önceki oturum yüklendi: [cyan]{msg_count} mesaj[/cyan]")
            console.print("[dim]Kaldığınız yerden devam ediyorsunuz. Sıfırdan başlamak için '/new' yazın.[/dim]\n")
    
    if ponytail_enabled:
        console.print("[dim italic]Ponytail (Lazy Senior Dev) mod aktif.[/dim italic]")

    while True:
        try:
            user_input = get_user_prompt("Sen")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Çıkılıyor...[/yellow]")
            break
            
        cmd = user_input.strip()
        if not cmd:
            continue

        norm = normalize_cmd(cmd)

        if norm in ("exit", "quit", "q"):
            console.print("[yellow]Çıkılıyor...[/yellow]")
            break

        if norm in ("help", "yardim", "?", "h"):
            show_help()
            continue
        
        if norm in ("new", "clear", "reset"):
            agent.reset_session()
            console.print("\n[bold green]✓[/bold green] Yeni oturum başlatıldı. Sohbet geçmişi ve oturum temizlendi.\n")
            continue

        if norm.startswith("session save"):
            raw_tokens = cmd.split()
            clean_tokens = [tok.strip("/") for tok in raw_tokens if tok.strip("/")]
            from lokal_ajan.agent.session import generate_session_name
            if len(clean_tokens) > 2:
                s_name = clean_tokens[2]
            else:
                s_name = generate_session_name()
            
            agent.session_name = s_name
            agent.save_current_session()
            console.print(f"\n[bold green]✓[/bold green] Oturum kaydedildi: [bold cyan]{s_name}[/bold cyan]")
            console.print(f"[dim]Kayıt yeri: {workdir}/.lokal_ajan/sessions/{s_name}.json[/dim]\n")
            continue

        if norm.startswith("session load"):
            raw_tokens = cmd.split()
            clean_tokens = [tok.strip("/") for tok in raw_tokens if tok.strip("/")]
            from lokal_ajan.agent.session import list_sessions, load_session
            
            # If a specific name was given: e.g. session load/ test
            if len(clean_tokens) > 2:
                s_name = clean_tokens[2]
                loaded = load_session(workdir, s_name)
                if not loaded:
                    console.print(f"\n[red]'{s_name}' adlı oturum bulunamadı.[/red]\n")
                else:
                    agent.session_name = s_name
                    agent.load_session_data(loaded.get("messages", []))
                    prev_m = loaded.get("model_name", "bilinmeyen")
                    console.print(f"\n[bold green]✓[/bold green] '[green]{s_name}[/green]' oturumu yüklendi ({len(loaded.get('messages', []))} mesaj, model: {agent.model_name}).\n")
                continue
                
            # No name given: Show interactive UP/DOWN arrow menu!
            sessions = list_sessions(workdir)
            if not sessions:
                console.print("\n[dim]Bu projede kayıtlı oturum bulunamadı.[/dim]\n")
                continue
                
            selected = None
            try:
                from prompt_toolkit.shortcuts import choice
                options = []
                for s in sessions:
                    is_curr = " [aktif]" if s["name"] == agent.session_name else ""
                    date_str = s['updated_at'][:19].replace("T", " ") if s.get('updated_at') else ""
                    label = f"{s['name']}{is_curr} ({s['message_count']} mesaj | model: {s['model_name']} | {date_str})"
                    options.append((s["name"], label))
                options.append(("__cancel__", "❌ [İptal / Vazgeç]"))
                
                selected = choice(
                    message="Yüklenecek oturumu seçin (Yukarı/Aşağı ok tuşları ve Enter):",
                    options=options,
                    default=options[0][0]
                )
            except Exception:
                console.print("\n[bold green]Kaydedilmiş Oturumlar:[/bold green]")
                for i, s in enumerate(sessions, 1):
                    console.print(f"  {i}. {s['name']} ({s['message_count']} mesaj)")
                c = Prompt.ask("\nOturum numarası veya adı seçin (iptal için boş bırakın)")
                if c.strip():
                    if c.isdigit() and 1 <= int(c) <= len(sessions):
                        selected = sessions[int(c)-1]["name"]
                    else:
                        selected = c.strip()

            if selected and selected != "__cancel__":
                loaded = load_session(workdir, selected)
                if loaded:
                    agent.session_name = selected
                    agent.load_session_data(loaded.get("messages", []))
                    prev_m = loaded.get("model_name", "bilinmeyen")
                    console.print(f"\n[bold green]✓[/bold green] '[green]{selected}[/green]' oturumu yüklendi ({len(loaded.get('messages', []))} mesaj, model: {agent.model_name}).\n")
            else:
                console.print("[dim]Oturum seçimi iptal edildi.[/dim]\n")
            continue

        if norm in ("session list", "sessions list", "sessions", "session"):
            sessions = list_sessions(workdir)
            if not sessions:
                console.print("\n[dim]Bu proje için kaydedilmiş başka oturum bulunmuyor.[/dim]\n")
            else:
                console.print("\n[bold green]Kaydedilmiş Oturumlar:[/bold green]")
                for s in sessions:
                    is_curr = " [cyan](aktif)[/cyan]" if s["name"] == agent.session_name else ""
                    date_str = s['updated_at'][:19].replace("T", " ") if s.get('updated_at') else ""
                    console.print(f"- [bold]{s['name']}[/bold]{is_curr} ({s['message_count']} mesaj, model: {s['model_name']}, son: {date_str})")
                console.print("[dim]Yüklemek için: session load/ veya /session load[/dim]\n")
            continue
            
        if norm.startswith("ponytail"):
            if norm in ("ponytail on", "ponytail/ on"):
                new_state = True
            elif norm in ("ponytail off", "ponytail/ off"):
                new_state = False
            else:
                new_state = not agent.ponytail_enabled
                
            agent.toggle_ponytail(new_state)
            state_str = "AÇIK" if new_state else "KAPALI"
            console.print(f"\n[bold green]✓[/bold green] Ponytail (Lazy Senior Dev) modu: [bold]{state_str}[/bold]\n")
            
            try:
                state_data["ponytail"] = new_state
                save_state(state_data)
            except Exception:
                pass
            continue
        
        if norm in ("model", "models"):
            switch_model(agent, config)
            continue
        
        if not agent.run_step(user_input):
            console.print("[yellow]Çıkılıyor...[/yellow]")
            break

@app.command(name="run")
def run_cmd(
    prompt: str = typer.Argument(..., help="Ajana verilecek görev"),
    model: str = typer.Option(None, "--model", "-m", help="Kullanılacak Ollama modeli"),
    worker_model: str = typer.Option(None, "--worker-model", "-wm", help="Orkestratör modu için işçi modeli"),
    workdir: str = typer.Option(".", "--workdir", "-w", help="Çalışma dizini"),
    yes: bool = typer.Option(True, "--yes", "-y", help="Tüm araç onaylarını otomatik onayla (non-interactive)"),
    gpu_mode: bool = typer.Option(False, "--gpu-mode", "-g", help="Küçük modeller için context boyutunu 8K'ya çekerek %100 GPU hızlandırmasını aktif et"),
    ponytail: bool = typer.Option(False, "--ponytail", "-p", help="Ponytail (Lazy Senior Dev) modunu aktif et")
):
    """
    Tek seferlik (non-interactive) görev çalıştır.
    """
    workdir = os.path.abspath(workdir)
    config = load_config()
    target_model = model or config.default_model
    
    if target_model.startswith("openrouter/") or (worker_model and worker_model.startswith("openrouter/")):
        ensure_openrouter_key(config)
        
    profile = get_profile_for_model(target_model, ollama_host=config.ollama_host)
    if gpu_mode and profile.num_ctx > 8192:
        profile = profile.model_copy(update={"num_ctx": 8192})
    
    LOGO = r"""
    __          __          __   ___    _           
   / /   ____  / /______ _ / /  /   |  (_)___ _____ 
  / /   / __ \/ //_/ __ `/ /   / /| | / / __ `/ __ \
 / /___/ /_/ / ,< / /_/ / /   / ___ |/ / /_/ / / / /
/_____/\____/_/|_|\__,_/_/   /_/  |_/ /\__,_/_/ /_/ 
                                 /___/              
"""
    console.print(f"[bold cyan]{LOGO}[/bold cyan]")
    console.print(f"[bold blue]Görev Başlatılıyor:[/bold blue] {prompt}")
    if gpu_mode:
        console.print("[bold yellow]⚡ Hızlı GPU Modu Aktif (8K Context / %100 GPU)[/bold yellow]")
        
    from lokal_ajan.llm.ollama_client import free_unused_models
    free_unused_models(target_model, worker_model, config.ollama_host)
        
    agent = AgentLoop(model_name=target_model, profile=profile, host=config.ollama_host, workdir=workdir, config=config, worker_model=worker_model, auto_confirm=yes, gpu_mode=gpu_mode, ponytail_enabled=ponytail)
    agent.run_step(prompt)

@app.command(name="models")
def list_models():
    """
    Desteklenen model profillerini listele.
    """
    console.print("[bold green]Desteklenen Model Profilleri:[/bold green]")
    for p in PROFILES:
        console.print(f"- [cyan]{p.name_pattern}[/cyan] (Context: {p.num_ctx}, Native Tool: {p.native_tool_call})")

@app.command(name="update")
def update_app():
    """
    Lokal Ajan'ı en son sürüme günceller.
    """
    import sys
    import subprocess
    console.print("[bold cyan]Lokal Ajan GitHub'dan güncelleniyor...[/bold cyan]")
    try:
        url = "https://github.com/ilhanakd-max/Local_Ajan/archive/refs/heads/main.zip"
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", url])
        console.print("[bold green]✅ Güncelleme başarıyla tamamlandı![/bold green]")
    except Exception as e:
        console.print(f"[bold red]❌ Güncelleme başarısız oldu: {e}[/bold red]")

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    model: str = typer.Option(None, "--model", "-m", help="Kullanılacak Ollama modeli"),
    worker_model: str = typer.Option(None, "--worker-model", "-wm", help="Orkestratör modu için işçi modeli"),
    workdir: str = typer.Option(".", "--workdir", "-w", help="Çalışma dizini"),
    gpu_mode: bool = typer.Option(False, "--gpu-mode", "-g", help="Küçük modeller için context boyutunu 8K'ya çekerek %100 GPU hızlandırmasını aktif et"),
    session: str = typer.Option("default", "--session", "-s", help="Kullanılacak oturum adı (varsayılan: default)"),
    new_session: bool = typer.Option(False, "--new", "-n", help="Önceki oturumu yüklemeden sıfırdan başla")
):
    if ctx.invoked_subcommand is None:
        start_interactive_session(model, workdir, worker_model, gpu_mode=gpu_mode, session_name=session, new_session=new_session)


if __name__ == "__main__":
    app()


