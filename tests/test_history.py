import sys
sys.path.insert(0, "src")

from lokal_ajan.agent.history import ChatHistory

def test_chat_history_clear():
    history = ChatHistory()
    history.add_message("system", "sys prompt")
    history.add_message("user", "hello")
    history.add_message("assistant", "hi")
    
    assert len(history.get_messages()) == 3
    history.clear()
    assert len(history.get_messages()) == 0

if __name__ == "__main__":
    test_chat_history_clear()
    print("✓ test_chat_history_clear geçti.")
