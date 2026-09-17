from typing import List, Dict, Any

class ChatHistory:
    def __init__(self):
        self.messages: List[Dict[str, Any]] = []
        
    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        
    def get_messages(self) -> List[Dict[str, Any]]:
        return self.messages
        
    def clear(self):
        self.messages.clear()
        
    def pop_last(self):
        if self.messages:
            self.messages.pop()
