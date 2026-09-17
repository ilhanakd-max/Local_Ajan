import subprocess
from pydantic import BaseModel, Field
from lokal_ajan.tools.base import BaseTool
from lokal_ajan.tools.registry import registry

import platform

os_name = platform.system()
cmd_type = "Windows CMD/PowerShell" if os_name == "Windows" else "Bash"

class RunShellArgs(BaseModel):
    command: str = Field(..., description=f"{cmd_type} command to run")

class RunShellTool(BaseTool):
    name = "run_shell"
    description = f"Runs a shell command in the workspace directory. Note: The operating system is {os_name}."
    args_schema = RunShellArgs
    requires_confirm = True
    
    def __init__(self, workdir: str = "."):
        self.workdir = workdir
        
    def run(self, command: str) -> str:
        try:
            # Filter out comments and blank lines that models often inject
            cleaned_lines = []
            for line in command.splitlines():
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("//") or stripped.upper().startswith("REM "):
                    continue
                cleaned_lines.append(line)
            
            cleaned_cmd = "\n".join(cleaned_lines).strip()
            if not cleaned_cmd:
                return "Command contained only comments and was skipped."

            # Guard against interactive editors/pagers that hang non-interactive shells
            first_words = {w.lower() for w in cleaned_cmd.replace("|", " ").replace(";", " ").replace("&", " ").split()}
            interactive_tools = {"nano", "vim", "vi", "less", "more"}
            blocked = first_words.intersection(interactive_tools)
            if blocked:
                tool_blocked = next(iter(blocked))
                return (
                    f"Error: Interactive editor/pager '{tool_blocked}' cannot be run in this environment. "
                    "Use 'read_file' to view files or 'edit_file'/'write_file' to modify files."
                )

            if platform.system() == "Windows":
                # On Windows, run via PowerShell so that commands like 'curl', 'cat', 'ls', 'rm',
                # and multiline expressions work without CMD syntax errors.
                try:
                    result = subprocess.run(
                        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", cleaned_cmd],
                        cwd=self.workdir,
                        text=True,
                        capture_output=True,
                        timeout=60
                    )
                except FileNotFoundError:
                    # Fallback to CMD if powershell binary is somehow not found
                    result = subprocess.run(
                        cleaned_cmd,
                        shell=True,
                        cwd=self.workdir,
                        text=True,
                        capture_output=True,
                        timeout=60
                    )
            else:
                result = subprocess.run(
                    cleaned_cmd,
                    shell=True,
                    cwd=self.workdir,
                    text=True,
                    capture_output=True,
                    timeout=60
                )
            
            output = ""
            if result.stdout:
                output += f"STDOUT:\n{result.stdout}\n"
            if result.stderr:
                output += f"STDERR:\n{result.stderr}\n"
                
            if not output:
                output = "Command executed successfully with no output."
                
            return output
        except subprocess.TimeoutExpired:
            return "Error: Command timed out after 60 seconds."
        except Exception as e:
            return f"Error running command: {e}"

# We'll instantiate this with the actual workdir during initialization
