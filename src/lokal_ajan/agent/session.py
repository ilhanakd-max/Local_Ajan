import os
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

SESSIONS_DIR = Path(os.environ.get(
    "LOKAL_AJAN_SESSIONS",
    Path.home() / ".config" / "lokal-ajan" / "sessions",
))


def _get_project_key(workdir: str) -> str:
    """Returns a unique, filesystem-safe identifier for the workspace directory."""
    abs_path = os.path.abspath(workdir)
    dir_name = Path(abs_path).name or "root"
    safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in dir_name)
    path_hash = hashlib.sha256(abs_path.encode("utf-8")).hexdigest()[:8]
    return f"{safe_name}_{path_hash}"


def _get_session_path(workdir: str, session_name: str = "default") -> Path:
    safe_session = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in session_name)
    key = _get_project_key(workdir)
    return SESSIONS_DIR / f"{key}_{safe_session}.json"


def save_session(
    workdir: str,
    messages: List[Dict[str, Any]],
    model_name: str,
    session_name: str = "default"
) -> Path:
    """
    Saves conversation history for the given workdir and session name.
    Excludes 'system' messages so changing models will regenerate appropriate prompts.
    """
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
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
    """
    session_path = _get_session_path(workdir, session_name)
    if not session_path.is_file():
        return None
    try:
        with open(session_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception:
        return None


def delete_session(workdir: str, session_name: str = "default") -> bool:
    """Deletes a session file."""
    session_path = _get_session_path(workdir, session_name)
    if session_path.is_file():
        try:
            session_path.unlink()
            return True
        except Exception:
            pass
    return False


def list_sessions(workdir: str) -> List[Dict[str, Any]]:
    """Lists all saved sessions for the given workspace directory."""
    if not SESSIONS_DIR.is_dir():
        return []
    
    key = _get_project_key(workdir)
    results = []
    prefix = f"{key}_"
    
    for item in SESSIONS_DIR.glob(f"{prefix}*.json"):
        try:
            with open(item, "r", encoding="utf-8") as f:
                data = json.load(f)
                results.append({
                    "name": data.get("session_name", item.stem[len(prefix):]),
                    "updated_at": data.get("updated_at", ""),
                    "model_name": data.get("model_name", ""),
                    "message_count": len(data.get("messages", [])),
                    "path": str(item)
                })
        except Exception:
            continue
            
    results.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return results
