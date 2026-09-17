import os
from pathlib import Path

def is_safe_path(target_path: str, workdir: str) -> bool:
    """
    Check if the target_path is within the workdir.
    Prevents path traversal attacks like ../../../etc/passwd.
    """
    try:
        workdir_path = Path(workdir).resolve()
        target_resolved = Path(workdir_path, target_path).resolve()
        return workdir_path in target_resolved.parents or target_resolved == workdir_path
    except Exception:
        return False

def get_safe_path(target_path: str, workdir: str) -> str:
    """
    Returns the resolved path if safe, otherwise raises ValueError.
    """
    if not is_safe_path(target_path, workdir):
        raise ValueError(f"Path is outside of workspace directory: {target_path}")
    return str(Path(workdir, target_path).resolve())
