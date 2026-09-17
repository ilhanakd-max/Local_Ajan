import re
from rich.prompt import Prompt
from rich.console import Console

console = Console()

# Yıkıcı olduğu bilinen komut kalıpları; run_shell zaten her zaman onay
# istiyor, ama bunlar için ekstra görsel bir uyarı gösteriyoruz ki
# kullanıcı "e" tuşuna otomatik basmadan önce bir kez daha düşünsün.
_DANGEROUS_SHELL_PATTERNS = [
    r"rm\s+-rf\s+/(?:\s|$)",
    r"rm\s+-rf\s+~",
    r"rm\s+-rf\s+\*",
    r":\(\)\s*{\s*:\|:&\s*};",  # fork bomb
    r"\bdd\s+if=.*of=/dev/",
    r"\bmkfs(\.\w+)?\b",
    r">\s*/dev/sd[a-z]",
    r"\bchmod\s+-R\s+777\s+/",
    r"\bchown\s+-R\s+.*\s+/",
    r"\bshutdown\b|\breboot\b|\bhalt\b",
    r"curl[^|]*\|\s*(sudo\s+)?(bash|sh)\b",
    r"wget[^|]*\|\s*(sudo\s+)?(bash|sh)\b",
]


def _looks_dangerous(command: str) -> bool:
    return any(re.search(p, command, re.IGNORECASE) for p in _DANGEROUS_SHELL_PATTERNS)


def _flush_stdin():
    """Clear any leftover characters in stdin buffer."""
    try:
        import termios, sys
        termios.tcflush(sys.stdin, termios.TCIFLUSH)
    except Exception:
        pass

def request_confirmation(tool_name: str, args: dict, auto_confirm: bool = False) -> bool:
    """
    Asks the user for confirmation before executing a tool.
    Accepts e, evet, y, yes, Enter (default=e).
    If auto_confirm is True, automatically returns True.
    """
    if auto_confirm:
        path_info = args.get("path") or args.get("command") or ""
        console.print(f"\n[bold yellow]Otomatik Onay:[/bold yellow] [bold cyan]{tool_name}[/bold cyan] {path_info}")
        return True

    console.print(f"\n[bold yellow]Uyarı:[/bold yellow] Ajan [bold cyan]{tool_name}[/bold cyan] aracını çalıştırmak istiyor.")
    
    # Print clean formatted arguments
    path_info = args.get("path") or args.get("command") or ""
    if path_info:
        console.print(f"[dim]Hedef: {path_info}[/dim]")

    command = args.get("command")
    if command and _looks_dangerous(command):
        console.print(
            "[bold red]⚠ DİKKAT:[/bold red] Bu komut sistemde kalıcı/yıkıcı hasara "
            "yol açabilecek bilinen bir kalıpla eşleşiyor. Lütfen dikkatlice kontrol edin."
        )

    _flush_stdin()
    response = Prompt.ask("Bu işleme izin veriyor musunuz? [E/h]", default="e")
    cleaned = response.strip().lower()
    
    # Accept e, evet, y, yes, or empty Enter
    if cleaned in ("e", "evet", "y", "yes", "1", ""):
        return True
        
    console.print("[yellow]İşlem kullanıcı tarafından reddedildi.[/yellow]")
    return False

