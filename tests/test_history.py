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

def test_chat_history_truncation():
    # Test that history does not grow unbounded and preserves system prompt
    history = ChatHistory(max_size=5)
    history.add_message("system", "sys prompt")
    for i in range(10):
        history.add_message("user", f"msg {i}")
        
    messages = history.get_messages()
    assert len(messages) == 5
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "sys prompt"
    # The last message should be the latest added message
    assert messages[-1]["content"] == "msg 9"

if __name__ == "__main__":
    test_chat_history_clear()
    test_chat_history_truncation()
    print("✓ Tüm test_history testleri geçti.")
