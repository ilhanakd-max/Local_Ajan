from typing import List, Dict, Any

class ChatHistory:
    def __init__(self, max_size: int = 500):
        self.messages: List[Dict[str, Any]] = []
        self.max_size = max_size
        
    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        if len(self.messages) > self.max_size:
            # Sistem mesajını koruyup en eski 1 mesajı silerek kaydır (pop(1))
            system_msg = None
            if self.messages and self.messages[0].get("role") == "system":
                system_msg = self.messages[0]
            
            # Eğer ilk mesaj system değilse normal şekilde baştan kırp
            # Eğer system ise 2. mesajı (index 1) sil
            if system_msg:
                self.messages.pop(1)
            else:
                self.messages.pop(0)
        
    def get_messages(self) -> List[Dict[str, Any]]:
        return self.messages
        
    def clear(self):
        self.messages.clear()
        
    def pop_last(self):
        if self.messages:
            self.messages.pop()
