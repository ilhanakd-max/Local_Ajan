import subprocess
from pathlib import Path
from pydantic import BaseModel, Field
from .base import BaseTool
from .registry import registry


class GitStatusArgs(BaseModel):
    path: str | None = Field(default=".", description="Path to git repository directory")


class GitStatusTool(BaseTool):
    name = "git_status"
    description = "Shows the working tree status using git status --short"
    args_schema = GitStatusArgs
    requires_confirm = False

    def run(self, path: str = ".") -> str:
        try:
            target_dir = Path(path).resolve()
            res = subprocess.run(
                ["git", "status", "--short", "--branch"],
                cwd=str(target_dir),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if res.returncode != 0:
                return f"Git error ({res.returncode}): {res.stderr.strip() or 'Not a git repository'}"
            out = res.stdout.strip()
            return out if out else "Working tree clean (no changes)."
        except Exception as e:
            return f"Error running git status: {e}"


class GitDiffArgs(BaseModel):
    staged: bool | None = Field(default=False, description="Show staged changes if True, otherwise working tree diff")
    path: str | None = Field(default=".", description="Path to git repository directory or specific file")


class GitDiffTool(BaseTool):
    name = "git_diff"
    description = "Shows changes in the git repository (git diff)"
    args_schema = GitDiffArgs
    requires_confirm = False

    def run(self, staged: bool = False, path: str = ".") -> str:
        try:
            target_dir = Path(path).resolve()
            cwd = target_dir if target_dir.is_dir() else target_dir.parent
            file_arg = [str(target_dir)] if target_dir.is_file() else []

            cmd = ["git", "diff"]
            if staged:
                cmd.append("--staged")
            cmd.extend(file_arg)

            res = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=15,
            )
            if res.returncode != 0:
                return f"Git error ({res.returncode}): {res.stderr.strip() or 'Not a git repository'}"
            out = res.stdout.strip()
            return out if out else "No changes found in diff."
        except Exception as e:
            return f"Error running git diff: {e}"


# Register tools
registry.register(GitStatusTool())
registry.register(GitDiffTool())
