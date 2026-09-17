import subprocess
from pydantic import BaseModel, Field
from lokal_ajan.tools.base import BaseTool
from lokal_ajan.tools.registry import registry

class RunShellArgs(BaseModel):
    command: str = Field(..., description="Bash command to run")

class RunShellTool(BaseTool):
    name = "run_shell"
    description = "Runs a bash command in the workspace directory"
    args_schema = RunShellArgs
    requires_confirm = True
    
    def __init__(self, workdir: str = "."):
        self.workdir = workdir
        
    def run(self, command: str) -> str:
        try:
            # We enforce timeout to prevent hanging commands
            result = subprocess.run(
                command,
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
