import os
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

LEGACY_SESSIONS_DIR = Path.home() / ".config" / "lokal-ajan" / "sessions"


def _get_project_key(workdir: str) -> str:
    """Returns a unique identifier for legacy sessions lookup."""
    abs_path = os.path.abspath(workdir)
    dir_name = Path(abs_path).name or "root"
    safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in dir_name)
    path_hash = hashlib.sha256(abs_path.encode("utf-8")).hexdigest()[:8]
    return f"{safe_name}_{path_hash}"


def _get_sessions_dir(workdir: str) -> Path:
    """
    Returns the sessions directory for the project.
    Prioritizes LOKAL_AJAN_SESSIONS environment variable (e.g. for testing),
    otherwise stores sessions directly inside the project directory: <workdir>/.lokal_ajan/sessions/
    """
    env_dir = os.environ.get("LOKAL_AJAN_SESSIONS")
    if env_dir:
        return Path(env_dir)
    return Path(workdir) / ".lokal_ajan" / "sessions"


def _ensure_gitignore(workdir: str):
    """Ensures .lokal_ajan is ignored if a .gitignore file exists in the workspace."""
    try:
        gitignore_path = Path(workdir) / ".gitignore"
        if gitignore_path.is_file():
            content = gitignore_path.read_text(encoding="utf-8")
            if ".lokal_ajan" not in content:
                with open(gitignore_path, "a", encoding="utf-8") as f:
                    f.write("\n# LocAi oturum verileri\n.lokal_ajan/\n")
    except Exception:
        pass


def generate_session_name() -> str:
    """Generates a readable timestamp-based automatic session name."""
    return datetime.now().strftime("oturum_%Y%m%d_%H%M%S")


def _get_session_path(workdir: str, session_name: str = "default") -> Path:
    safe_session = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in session_name)
    return _get_sessions_dir(workdir) / f"{safe_session}.json"


def save_session(
    workdir: str,
    messages: List[Dict[str, Any]],
    model_name: str,
    session_name: str = "default"
) -> Path:
    """
    Saves conversation history directly into the project directory (.lokal_ajan/sessions/).
    Excludes 'system' messages so changing models will regenerate appropriate prompts.
    """
    sessions_dir = _get_sessions_dir(workdir)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    _ensure_gitignore(workdir)

    session_path = _get_session_path(workdir, session_name)
    
    # Filter out system prompt so that changing models regenerates the appropriate prompt
    filtered_messages = [m for m in messages if m.get("role") != "system"]
    
    created_at = datetime.now().isoformat()
    if session_path.exists():
        try:
            with open(session_path, "r", encoding="utf-8") as f:
                old_data = json.load(f)
                created_at = old_data.get("created_at", created_at)
        except Exception:
            pass

    data = {
        "workdir": os.path.abspath(workdir),
        "session_name": session_name,
        "model_name": model_name,
        "created_at": created_at,
        "updated_at": datetime.now().isoformat(),
        "messages": filtered_messages,
    }
    
    with open(session_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        
    return session_path


def load_session(workdir: str, session_name: str = "default") -> Optional[Dict[str, Any]]:
    """
    Loads session data if it exists for the given workdir and session name.
    First checks project folder, then falls back to legacy config directory.
    """
    session_path = _get_session_path(workdir, session_name)
    if session_path.is_file():
        try:
            with open(session_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    # Fallback: check legacy session location
    if LEGACY_SESSIONS_DIR.is_dir():
        key = _get_project_key(workdir)
        safe_session = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in session_name)
        legacy_file = LEGACY_SESSIONS_DIR / f"{key}_{safe_session}.json"
        if legacy_file.is_file():
            try:
                with open(legacy_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None

    return None


def delete_session(workdir: str, session_name: str = "default") -> bool:
    """Deletes a session file from project directory or legacy directory."""
    deleted = False
    session_path = _get_session_path(workdir, session_name)
    if session_path.is_file():
        try:
            session_path.unlink()
            deleted = True
        except Exception:
            pass

    # Also clean legacy if present
    if LEGACY_SESSIONS_DIR.is_dir():
        key = _get_project_key(workdir)
        safe_session = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in session_name)
        legacy_file = LEGACY_SESSIONS_DIR / f"{key}_{safe_session}.json"
        if legacy_file.is_file():
            try:
                legacy_file.unlink()
                deleted = True
            except Exception:
                pass

    return deleted


def list_sessions(workdir: str) -> List[Dict[str, Any]]:
    """Lists all saved sessions for the project directory."""
    sessions_dir = _get_sessions_dir(workdir)
    results_map = {}
    
    # 1. Project folder sessions
    if sessions_dir.is_dir():
        for item in sessions_dir.glob("*.json"):
            try:
                with open(item, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    name = data.get("session_name", item.stem)
                    results_map[name] = {
                        "name": name,
                        "updated_at": data.get("updated_at", ""),
                        "model_name": data.get("model_name", ""),
                        "message_count": len(data.get("messages", [])),
                        "path": str(item)
                    }
            except Exception:
                continue

    # 2. Legacy sessions (if not already found in project)
    if LEGACY_SESSIONS_DIR.is_dir():
        key = _get_project_key(workdir)
        prefix = f"{key}_"
        for item in LEGACY_SESSIONS_DIR.glob(f"{prefix}*.json"):
            try:
                with open(item, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    name = data.get("session_name", item.stem[len(prefix):])
                    if name not in results_map:
                        results_map[name] = {
                            "name": name,
                            "updated_at": data.get("updated_at", ""),
                            "model_name": data.get("model_name", ""),
                            "message_count": len(data.get("messages", [])),
                            "path": str(item)
                        }
            except Exception:
                continue

    results = list(results_map.values())
    results.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return results
