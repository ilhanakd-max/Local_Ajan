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
        "groq/openai/gpt-oss-120b",
        "groq/openai/gpt-oss-20b",
        "groq/qwen/qwen3.8-27b",
        "openrouter/free",
        "ninerouter/free-model",
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
    
    new_profile = get_profile_for_model(new_model)
    agent.update_model(new_model, new_profile)
    
    from lokal_ajan.llm.ollama_client import free_unused_models
    free_unused_models(new_model, agent.worker_model, config.ollama_host)
    
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

def start_interactive_session(model: str, workdir: str, worker_model: str = None, gpu_mode: bool = False):
    config = load_config()
    target_model = model or config.default_model
    profile = get_profile_for_model(target_model)
    
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
    console.print(f"[bold blue]Lokal Ajan[/bold blue] başlatılıyor...")
    if gpu_mode:
        console.print("[bold yellow]⚡ Hızlı GPU Modu Aktif (8K Context / %100 GPU Hızlandırma)[/bold yellow]")
        
    if worker_model:
        console.print(f"Mod (Orkestratör): Beyin=[green]{target_model}[/green], İşçi=[green]{worker_model}[/green]")
    else:
        console.print(f"Model: [green]{target_model}[/green] (Context: {profile.num_ctx}, Temp: {profile.temperature})")
    
    console.print(f"Çalışma Dizini: [yellow]{workdir}[/yellow]")
    console.print("Çıkmak için 'exit' veya 'quit' yazın.")
    console.print("Model değiştirmek için '/model' yazın.")
    console.print("Yeni oturum başlatmak için '/new' yazın.")
    console.print("Ponytail (Lazy Dev) modunu değiştirmek için '/ponytail', '/ponytail on' veya '/ponytail off' yazın.\n")
    
    # Arka planda kullanılmayan diğer Ollama modellerini bellekten boşalt
    from lokal_ajan.llm.ollama_client import free_unused_models
    free_unused_models(target_model, worker_model, config.ollama_host)
    
    # Son kullanılan ayarları kaydet
    try:
        from lokal_ajan.config import load_state, save_state
        saved = load_state()
        ponytail_enabled = saved.get("ponytail", False)
        
        abs_workdir = os.path.abspath(workdir)
        state_data = {"workdir": abs_workdir, "model": target_model, "gpu_mode": gpu_mode, "ponytail": ponytail_enabled}
        if worker_model:
            state_data["worker_model"] = worker_model
            state_data["orchestrator"] = True
        save_state(state_data)
    except Exception:
        ponytail_enabled = False
    
    agent = AgentLoop(model_name=target_model, profile=profile, host=config.ollama_host, workdir=workdir, config=config, worker_model=worker_model, auto_confirm=True, gpu_mode=gpu_mode, ponytail_enabled=ponytail_enabled)
    
    if ponytail_enabled:
        console.print("[dim italic]Ponytail (Lazy Senior Dev) mod aktif.[/dim italic]")

    while True:
        try:
            user_input = get_user_prompt("Sen")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Çıkılıyor...[/yellow]")
            break
            
        cmd = user_input.strip().lower()

        
        if not cmd:
            continue

        if cmd in ("exit", "quit", "/exit", "/quit", "q", "/q"):
            console.print("[yellow]Çıkılıyor...[/yellow]")
            break
        
        if cmd in ("/new", "/clear", "/reset"):
            agent.reset_session()
            console.print("\n[bold green]✓[/bold green] Yeni oturum başlatıldı. Sohbet geçmişi temizlendi.\n")
            continue
            
        if cmd in ("/ponytail", "/ponytail on", "/ponytail off"):
            if cmd == "/ponytail on":
                new_state = True
            elif cmd == "/ponytail off":
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
        
        if cmd in ("/model", "/models"):
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
    config = load_config()
    target_model = model or config.default_model
    profile = get_profile_for_model(target_model)
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

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    model: str = typer.Option(None, "--model", "-m", help="Kullanılacak Ollama modeli"),
    worker_model: str = typer.Option(None, "--worker-model", "-wm", help="Orkestratör modu için işçi modeli"),
    workdir: str = typer.Option(".", "--workdir", "-w", help="Çalışma dizini"),
    gpu_mode: bool = typer.Option(False, "--gpu-mode", "-g", help="Küçük modeller için context boyutunu 8K'ya çekerek %100 GPU hızlandırmasını aktif et")
):
    if ctx.invoked_subcommand is None:
        start_interactive_session(model, workdir, worker_model, gpu_mode=gpu_mode)


if __name__ == "__main__":
    app()

