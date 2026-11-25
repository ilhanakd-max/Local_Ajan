"""Session-scoped safety guards for small local models."""

import json
import os
import re
from pathlib import Path
from typing import Any

_PROTECTED_SEGMENTS = (".git/", "node_modules/", ".venv/")
_RM_PATTERN = re.compile(r"\brm\s+(?:-[a-zA-Z]+\s+)*([^\s;&|<>]+)")
_MV_SRC_PATTERN = re.compile(r"\bmv\s+(?:-[a-zA-Z]+\s+)*([^\s;&|<>]+)\s+[^\s;&|<>]+")

_MUTATING_TOOLS = frozenset({
    "write_file",
    "edit_file",
    "write_excel",
    "append_excel",
    "edit_excel_cells",
    "write_pdf",
    "_write_multiple",
})

_MUTATING_SHELL_PATTERNS = (
    re.compile(r"\b(rm|mv|cp|mkdir|rmdir|touch|chmod|chown|ln|install)\b"),
    re.compile(r"\bsed\s+[^|;&]*-i\b"),
    re.compile(r"\bgit\s+(add|commit|checkout|switch|reset|merge|rebase|cherry-pick|apply|stash)\b"),
    re.compile(r"\b(pip|pip3|uv|npm|pnpm|yarn|cargo)\s+(install|uninstall|add|remove|update)\b"),
    re.compile(r"(?<![2&])>{1,2}(?!\s*&|\s*/dev/null)"),
)

_deleted_paths: set[str] = set()


def _normalize_abs(path: str, workdir: str = ".") -> str:
    p = Path(path)
    if not p.is_absolute():
        p = Path(workdir) / p
    return str(p.resolve())


def clear_deleted_paths() -> None:
    """Clear tracked deleted/moved paths (e.g., on new session)."""
    _deleted_paths.clear()


def track_shell_deletions(command: str, workdir: str = ".") -> None:
    """Record paths deleted or moved via shell commands to block rm && write bypasses."""
    if not command:
        return
    for match in _RM_PATTERN.finditer(command):
        target = match.group(1).strip("\"'")
        if target and not target.startswith("-"):
            _deleted_paths.add(_normalize_abs(target, workdir))
    for match in _MV_SRC_PATTERN.finditer(command):
        target = match.group(1).strip("\"'")
        if target and not target.startswith("-"):
            _deleted_paths.add(_normalize_abs(target, workdir))


def is_deleted_path(path: str, workdir: str = ".") -> bool:
    """Return True if the path was deleted/moved via shell in this session."""
    return _normalize_abs(path, workdir) in _deleted_paths


def is_protected_path(path: str) -> str | None:
    """Return the matched protected segment if path is inside a protected directory."""
    norm = os.path.abspath(path).replace("\\", "/")
    for seg in _PROTECTED_SEGMENTS:
        if f"/{seg}" in norm or norm.endswith(f"/{seg.rstrip('/')}"):
            return seg.rstrip("/")
    return None


def is_mutating_call(tool_name: str, args: dict[str, Any] | None = None) -> bool:
    """Return True if a tool call mutates the workspace."""
    if tool_name in _MUTATING_TOOLS:
        return True
    if tool_name == "run_shell" and isinstance(args, dict):
        cmd = str(args.get("command", ""))
        # Strip quoted strings before checking redirections
        unquoted = re.sub(r'"[^"]*"|\'[^\']*\'', "", cmd)
        return any(p.search(unquoted) for p in _MUTATING_SHELL_PATTERNS)
    return False


def _stable_signature(tool_name: str, args: dict[str, Any] | None) -> str:
    try:
        serialized = json.dumps(args or {}, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        serialized = str(args)[:300]
    return f"{tool_name}:{serialized}"


class RepetitionLoopGuard:
    """Detects identical tool-call repetitions and periodic cycles (A-B-A-B)."""

    def __init__(
        self,
        threshold: int | None = None,
        window_size: int | None = None,
        stop_after: int | None = None,
    ):
        env_thresh = os.environ.get("LOCAI_LOOP_THRESHOLD", "3")
        default_thresh = int(env_thresh) if env_thresh.isdigit() and int(env_thresh) >= 2 else 3
        self.threshold = max(2, threshold if threshold is not None else default_thresh)

        env_win = os.environ.get("LOCAI_LOOP_WINDOW", "")
        default_win = int(env_win) if env_win.isdigit() and int(env_win) >= self.threshold else 4 * self.threshold
        self.window_size = window_size if window_size is not None else default_win

        env_stop = os.environ.get("LOCAI_LOOP_STOP_AFTER", "3")
        default_stop = int(env_stop) if env_stop.isdigit() else 3
        self.stop_after = stop_after if stop_after is not None else default_stop

        self._window: list[str] = []
        self._block_count: int = 0

    def check(self, tool_name: str, args: dict[str, Any] | None) -> tuple[bool, bool, str]:
        """Check if incoming tool call is a repetition or cycle.

        Returns:
            (blocked, should_abort, reason)
        """
        sig = _stable_signature(tool_name, args)

        # Rule 1: Repetition (appears >= threshold - 1 times in window)
        count = self._window.count(sig)
        if count >= self.threshold - 1:
            return self._record_block(
                f"UYARI: '{tool_name}' aynı parametrelerle {count + 1} kez tekrarlandı (değişiklik yapılmadan). "
                "Farklı bir yaklaşım dene veya işlem tamamlandıysa dur."
            )

        # Rule 2: Periodic cycle (period 2..4)
        candidate = self._window + [sig]
        for period in range(2, 5):
            if len(candidate) >= 2 * period:
                if candidate[-2 * period : -period] == candidate[-period:]:
                    return self._record_block(
                        f"UYARI: {period} adımlı tekrarlayan bir araç döngüsü tespit edildi ('{tool_name}'). "
                        "Aynı döngüyü sürdürme; farklı bir adım at veya görevi tamamla."
                    )

        return False, False, ""

    def _record_block(self, reason: str) -> tuple[bool, bool, str]:
        self._block_count += 1
        should_abort = self.stop_after > 0 and self._block_count >= self.stop_after
        return True, should_abort, reason

    def record(self, tool_name: str, args: dict[str, Any] | None, is_error: bool = False) -> None:
        """Record an executed tool call; reset window if it mutated the workspace."""
        if not is_error and is_mutating_call(tool_name, args):
            self._window.clear()
            self._block_count = 0
            return
        sig = _stable_signature(tool_name, args)
        self._window.append(sig)
        if len(self._window) > self.window_size:
            self._window = self._window[-self.window_size :]


def detect_text_repetition(text: str, min_chunk: int = 40, repeats: int = 4) -> bool:
    """Detect if streamed text has degenerated into verbatim repetition at the tail."""
    if not text or len(text) < min_chunk * repeats:
        return False
    lines = [ln.strip() for ln in text.splitlines() if len(ln.strip()) >= min_chunk]
    if len(lines) >= repeats and len(set(lines[-repeats:])) == 1:
        return True
    return False

