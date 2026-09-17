from typing import Dict, Optional, List
from .base import BaseTool

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        
    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool
        
    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)
        
    def get_all_tools(self) -> List[BaseTool]:
        return list(self._tools.values())
        
    def get_all_schemas(self) -> List[Dict]:
        return [tool.get_schema() for tool in self._tools.values()]

registry = ToolRegistry()
