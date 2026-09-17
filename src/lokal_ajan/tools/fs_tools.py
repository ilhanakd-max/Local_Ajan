import os
import glob
from pathlib import Path
from pydantic import BaseModel, Field
from .base import BaseTool
from .registry import registry

class ReadFileArgs(BaseModel):
    path: str = Field(..., description="Path to the file to read")
    start_line: int | None = Field(None, description="Starting line number (1-indexed)")
    end_line: int | None = Field(None, description="Ending line number (1-indexed)")

class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Reads content from a file"
    args_schema = ReadFileArgs
    requires_confirm = False
    
    def run(self, path: str, start_line: int | None = None, end_line: int | None = None) -> str:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            if start_line is not None and end_line is not None:
                lines = lines[start_line-1:end_line]
            elif start_line is not None:
                lines = lines[start_line-1:]
            elif end_line is not None:
                lines = lines[:end_line]
                
            result = "".join(lines)
            if not result:
                return f"File '{path}' is empty."
            return result
        except Exception as e:
            return f"Error reading file: {e}"

class WriteFileArgs(BaseModel):
    path: str = Field(..., description="Path to the file to write")
    content: str = Field(..., description="Content to write to the file")

class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Creates a new file or overwrites an existing one"
    args_schema = WriteFileArgs
    requires_confirm = True
    
    def run(self, path: str, content: str) -> str:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"Successfully wrote to {path}"
        except Exception as e:
            return f"Error writing file: {e}"

class EditFileArgs(BaseModel):
    path: str = Field(..., description="Path to the file to edit")
    old_str: str = Field(..., description="Exact string in the file to replace")
    new_str: str = Field(..., description="New string to replace old_str with")

class EditFileTool(BaseTool):
    name = "edit_file"
    description = "Replaces exact occurrences of old_str with new_str in a file"
    args_schema = EditFileArgs
    requires_confirm = True
    
    def run(self, path: str, old_str: str, new_str: str) -> str:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 1. Exact match
            if old_str in content:
                new_content = content.replace(old_str, new_str, 1)
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                return f"Successfully edited {path}"

            # 2. Line endings normalization (\r\n vs \n)
            c_norm = content.replace('\r\n', '\n')
            o_norm = old_str.replace('\r\n', '\n')
            if o_norm in c_norm:
                new_content = c_norm.replace(o_norm, new_str.replace('\r\n', '\n'), 1)
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                return f"Successfully edited {path}"

            # 3. Trailing-whitespace tolerant matching
            c_lines = c_norm.split('\n')
            o_lines = [l.rstrip() for l in o_norm.split('\n')]
            n_o = len(o_lines)
            for i in range(len(c_lines) - n_o + 1):
                window = [c_lines[i + j].rstrip() for j in range(n_o)]
                if window == o_lines:
                    new_lines = new_str.replace('\r\n', '\n').split('\n')
                    res_lines = c_lines[:i] + new_lines + c_lines[i + n_o:]
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(res_lines))
                    return f"Successfully edited {path}"
                
            return f"Error: Could not find target string in {path}"
        except Exception as e:
            return f"Error editing file: {e}"


class ListDirArgs(BaseModel):
    path: str = Field(..., description="Directory path to list")

class ListDirTool(BaseTool):
    name = "list_dir"
    description = "Lists files and directories in a given path"
    args_schema = ListDirArgs
    requires_confirm = False
    
    def run(self, path: str) -> str:
        try:
            items = os.listdir(path)
            if not items:
                return f"Directory '{path}' is empty."
            return "\n".join(items)
        except Exception as e:
            return f"Error listing directory: {e}"

class GlobArgs(BaseModel):
    pattern: str = Field(..., description="Glob pattern to search for (e.g. '*.py', 'src/**/*.js')")
    path: str | None = Field(default=".", description="Base directory to search in")

class GlobTool(BaseTool):
    name = "glob"
    description = "Finds files and directories matching a glob pattern"
    args_schema = GlobArgs
    requires_confirm = False

    def run(self, pattern: str, path: str = ".") -> str:
        try:
            base = Path(path)
            if not base.exists():
                return f"Error: Path '{path}' does not exist."
            
            # Use glob/rglob depending on pattern
            matches = []
            for p in base.glob(pattern):
                # Skip hidden/venv/git directories unless pattern explicitly requests
                parts = p.parts
                if any(part in (".git", ".venv", "__pycache__", ".egg-info") for part in parts):
                    continue
                matches.append(str(p))
                if len(matches) >= 100:
                    break

            if not matches:
                return f"No files matched pattern '{pattern}' in '{path}'."
            
            out = "\n".join(sorted(matches))
            if len(matches) >= 100:
                out += "\n... (ilk 100 sonuç gösterildi)"
            return out
        except Exception as e:
            return f"Error running glob: {e}"

class GrepArgs(BaseModel):
    pattern: str = Field(..., description="Text or regex pattern to search for")
    path: str | None = Field(default=".", description="Directory or file path to search inside")
    case_sensitive: bool | None = Field(default=False, description="Whether search is case-sensitive")

class GrepTool(BaseTool):
    name = "grep"
    description = "Searches for text or regex pattern inside files"
    args_schema = GrepArgs
    requires_confirm = False

    def run(self, pattern: str, path: str = ".", case_sensitive: bool = False) -> str:
        import shutil
        import subprocess
        import re

        try:
            target_path = Path(path)
            if not target_path.exists():
                return f"Error: Path '{path}' does not exist."

            # If ripgrep (rg) is installed, use it for best performance
            rg_bin = shutil.which("rg")
            if rg_bin:
                cmd = [rg_bin, "-n", "--max-count", "100", "--glob", "!.git", "--glob", "!.venv", "--glob", "!__pycache__"]
                if not case_sensitive:
                    cmd.append("-i")
                cmd.extend([pattern, str(target_path)])
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                output = res.stdout.strip()
                if not output:
                    return f"No matches found for '{pattern}' in '{path}'."
                return output

            # Python fallback if rg is not installed
            flags = 0 if case_sensitive else re.IGNORECASE
            regex = re.compile(pattern, flags)
            results = []
            
            files_to_search = []
            if target_path.is_file():
                files_to_search.append(target_path)
            else:
                for root, dirs, files in os.walk(target_path):
                    dirs[:] = [d for d in dirs if d not in (".git", ".venv", "__pycache__", "node_modules")]
                    for file in files:
                        files_to_search.append(Path(root, file))

            for fpath in files_to_search:
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        for lineno, line in enumerate(f, 1):
                            if regex.search(line):
                                results.append(f"{fpath}:{lineno}: {line.rstrip()}")
                                if len(results) >= 100:
                                    break
                except Exception:
                    continue
                if len(results) >= 100:
                    break

            if not results:
                return f"No matches found for '{pattern}' in '{path}'."
            
            out = "\n".join(results)
            if len(results) >= 100:
                out += "\n... (ilk 100 sonuç gösterildi)"
            return out
        except Exception as e:
            return f"Error searching with grep: {e}"

# Register tools
registry.register(ReadFileTool())
registry.register(WriteFileTool())
registry.register(EditFileTool())
registry.register(ListDirTool())
registry.register(GlobTool())
registry.register(GrepTool())

