import sys
sys.path.insert(0, "src")

import lokal_ajan.tools.fs_tools  # noqa: F401  (register tools)

from lokal_ajan.agent.thinking import strip_thinking, filter_thinking_stream
from lokal_ajan.agent.parser import extract_tool_call
from lokal_ajan.agent.context import prepare_context, truncate_tool_output
from lokal_ajan.llm.model_profiles import get_profile_for_model


# --- strip_thinking ---------------------------------------------------

def test_strip_thinking_basic():
    text = "<think>hmm let me think about this</think>Hello there!"
    assert strip_thinking(text) == "Hello there!"


def test_strip_thinking_no_tags_passthrough():
    text = "Just a normal reply."
    assert strip_thinking(text) == text


def test_strip_thinking_unclosed_tag_drops_rest():
    text = "<think>still reasoning and never finished"
    assert strip_thinking(text) == ""


def test_strip_thinking_tool_call_after_think():
    text = (
        '<think>I should call write_file</think>\n'
        '<tool_call>\n{"name": "write_file", "arguments": {"path": "a.txt", "content": "hi"}}\n</tool_call>'
    )
    cleaned = strip_thinking(text)
    assert "<think>" not in cleaned
    result = extract_tool_call(text)
    assert result is not None
    tool, args = result
    assert tool == "write_file"
    assert args == {"path": "a.txt", "content": "hi"}


def test_tool_call_hidden_inside_think_is_ignored_if_no_real_call_after():
    text = '<think>{"name": "write_file", "arguments": {"path": "x", "content": "y"}}</think>Hello!'
    result = extract_tool_call(text)
    assert result is None, "A tool call fully inside <think> must never execute"


# --- filter_thinking_stream (chunked / split across boundaries) ------

def test_filter_thinking_stream_simple():
    chunks = ["<thi", "nk>reasoning here</thi", "nk>Hello", " world!"]
    out = "".join(filter_thinking_stream(iter(chunks)))
    assert out == "Hello world!"


def test_filter_thinking_stream_no_think_tags():
    chunks = ["Hello", " ", "there", "!"]
    out = "".join(filter_thinking_stream(iter(chunks)))
    assert out == "Hello there!"


def test_filter_thinking_stream_unclosed_think_drops_tail():
    chunks = ["Visible part. ", "<think>never closes"]
    out = "".join(filter_thinking_stream(iter(chunks)))
    assert out == "Visible part. "


# --- Qwen-native name/arguments tool call format ----------------------

def test_extract_qwen_native_name_arguments_format():
    text = '<tool_call>\n{"name": "read_file", "arguments": {"path": "main.py"}}\n</tool_call>'
    result = extract_tool_call(text)
    assert result is not None
    tool, args = result
    assert tool == "read_file"
    assert args == {"path": "main.py"}


# --- model_profiles ----------------------------------------------------

def test_profile_qwen3_0_6b_is_minimal_and_disables_thinking():
    p = get_profile_for_model("qwen3:0.6b")
    assert p.prompt_level == "minimal"
    assert p.supports_think_control is True
    assert p.disable_thinking is True
    assert p.native_tool_call is False


def test_profile_qwen3_1_7b():
    p = get_profile_for_model("qwen3:1.7b")
    assert p.prompt_level == "minimal"
    assert p.supports_think_control is True


def test_profile_unknown_qwen3_variant_size_fallback():
    # Not explicitly listed, but should still get a sane small-model profile
    # via the size-based fallback (extracts "0.8b" from the name).
    p = get_profile_for_model("qwen3.5:0.8b")
    assert p.prompt_level == "minimal"
    assert p.num_ctx <= 8192


def test_profile_large_model_gets_standard_prompt():
    p = get_profile_for_model("qwen2.5-coder:7b")
    assert p.prompt_level == "standard"
    assert p.native_tool_call is True


# --- context truncation --------------------------------------------------

def test_prepare_context_keeps_system_and_recent_when_over_budget():
    system = {"role": "system", "content": "SYS " * 10}
    old_msgs = [{"role": "user", "content": "x" * 500} for _ in range(20)]
    recent = {"role": "user", "content": "most recent message"}
    messages = [system] + old_msgs + [recent]

    result = prepare_context(messages, max_context=200)  # tiny budget
    assert result[0] == system
    assert result[-1] == recent
    assert len(result) < len(messages)


def test_prepare_context_returns_all_when_small():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    result = prepare_context(messages, max_context=4096)
    assert result == messages


def test_truncate_tool_output_short_passthrough():
    assert truncate_tool_output("short", 100) == "short"


def test_truncate_tool_output_long_gets_cut():
    out = truncate_tool_output("x" * 5000, 100)
    assert len(out) < 5000
    assert out.startswith("x" * 100)


if __name__ == "__main__":
    import inspect
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_") and inspect.isfunction(obj)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  ✗ {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ✗ {t.__name__}: {type(e).__name__}: {e}")
    print(f"Tamamlandı. {len(tests) - failed}/{len(tests)} geçti.")
