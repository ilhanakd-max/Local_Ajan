"""Tests for the parser fixes: broken tags, JSON cleanup, and multi-tool-call support."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from lokal_ajan.agent.parser import (
    extract_tool_call,
    extract_all_tool_calls,
    _normalize_broken_tags,
    _cleanup_json,
)


def test_normalize_broken_tags():
    """Broken <tool_call> tags should be normalized."""
    broken = "<tool_ca\n\n\nll>"
    assert _normalize_broken_tags(broken) == "<tool_call>"

    broken_close = "</tool_ca\nll>"
    assert _normalize_broken_tags(broken_close) == "</tool_call>"

    assert _normalize_broken_tags("< tool_call >") == "<tool_call>"
    assert _normalize_broken_tags("</ tool_call >") == "</tool_call>"

    assert _normalize_broken_tags("<tool_call>") == "<tool_call>"
    assert _normalize_broken_tags("</tool_call>") == "</tool_call>"

    assert _normalize_broken_tags("Hello world") == "Hello world"
    print("✓ test_normalize_broken_tags passed")


def test_cleanup_json_trailing_gt():
    """JSON cleanup should remove stray '>' after closing brace."""
    import json
    bad_json = '{"name": "write_file", "arguments": {"path": "style.css", "content": "body {}"}}'
    bad_json_with_gt = bad_json + '>'
    cleaned = _cleanup_json(bad_json_with_gt)
    parsed = json.loads(cleaned)
    assert parsed["name"] == "write_file"
    print("✓ test_cleanup_json_trailing_gt passed")


def test_extract_tool_call_broken_tag():
    """extract_tool_call should work with broken <tool_call> tags."""
    model_output = '<tool_ca\n\n\nll>\n{"name": "write_file", "arguments": {"path": "saat.html", "content": "<!DOCTYPE html><html></html>"}}\n</tool_call>'
    result = extract_tool_call(model_output)
    assert result is not None, "Failed to extract tool call from broken tag"
    tool_name, args = result
    assert tool_name == "write_file", f"Expected 'write_file', got '{tool_name}'"
    assert args["path"] == "saat.html", f"Expected 'saat.html', got '{args.get('path')}'"
    print("✓ test_extract_tool_call_broken_tag passed")


def test_extract_tool_call_no_closing_tag():
    """extract_tool_call should work when closing tag is missing."""
    model_output = '<tool_call>\n{"name": "write_file", "arguments": {"path": "test.js", "content": "console.log(42);"}}\n'
    result = extract_tool_call(model_output)
    assert result is not None, "Failed to extract tool call without closing tag"
    tool_name, args = result
    assert tool_name == "write_file"
    assert args["path"] == "test.js"
    print("✓ test_extract_tool_call_no_closing_tag passed")


def test_extract_tool_call_json_with_trailing_gt():
    """extract_tool_call should handle JSON with trailing '>'."""
    model_output = '<tool_call>\n{"name": "write_file", "arguments": {"path": "style.css", "content": ".body { color: red; }"}}>\n</tool_call>'
    result = extract_tool_call(model_output)
    assert result is not None, "Failed to extract tool call with trailing '>'"
    tool_name, args = result
    assert tool_name == "write_file"
    assert args["path"] == "style.css"
    print("✓ test_extract_tool_call_json_with_trailing_gt passed")


def test_extract_all_tool_calls_multiple():
    """extract_all_tool_calls should find all tool calls in one response."""
    model_output = (
        '<tool_call>\n{"name": "write_file", "arguments": {"path": "saat.html", "content": "<!DOCTYPE html>"}}\n</tool_call>\n'
        '<tool_call>\n{"name": "write_file", "arguments": {"path": "style.css", "content": "body { color: red; }"}}\n</tool_call>\n'
        '<tool_call>\n{"name": "write_file", "arguments": {"path": "script.js", "content": "console.log(42);"}}\n</tool_call>\n'
        'I have created the files.'
    )
    results = extract_all_tool_calls(model_output)
    assert len(results) == 3, f"Expected 3 tool calls, got {len(results)}"
    assert results[0][1]["path"] == "saat.html"
    assert results[1][1]["path"] == "style.css"
    assert results[2][1]["path"] == "script.js"
    print("✓ test_extract_all_tool_calls_multiple passed")


def test_extract_all_broken_tags_multiple():
    """extract_all_tool_calls should handle broken tags in multi-call output."""
    model_output = (
        '<tool_ca\n\n\nll>\n{"name": "write_file", "arguments": {"path": "saat.html", "content": "<!DOCTYPE html>"}}\n</tool_call>\n'
        '<tool_call>\n{"name": "write_file", "arguments": {"path": "style.css", "content": "body {}"}}\n</tool_call>\n'
        '<tool_call>\n{"name": "write_file", "arguments": {"path": "script.js", "content": "console.log(42);"}}\n</tool_call>\n'
        'I have created the necessary files.'
    )
    results = extract_all_tool_calls(model_output)
    assert len(results) >= 2, f"Expected at least 2 tool calls, got {len(results)}: {results}"
    paths = [r[1]["path"] for r in results]
    assert "saat.html" in paths, f"saat.html not found in {paths}"
    assert "script.js" in paths, f"script.js not found in {paths}"
    print(f"✓ test_extract_all_broken_tags_multiple passed ({len(results)} calls found: {paths})")


def test_extract_all_single_call_fallback():
    """extract_all_tool_calls should fall back to single-call extraction."""
    model_output = '<tool_call>\n{"name": "read_file", "arguments": {"path": "test.txt"}}\n</tool_call>'
    results = extract_all_tool_calls(model_output)
    assert len(results) == 1, f"Expected 1 tool call, got {len(results)}"
    assert results[0][0] == "read_file"
    print("✓ test_extract_all_single_call_fallback passed")


def test_user_log_exact_raw_unescaped_quotes():
    """Exact log from user: broken tag, unescaped HTML quotes in content, 3 files."""
    user_log_output = """<tool_ca


ll>
{"name": "write_file", "arguments": {"path": "saat.html", "content": "<!DOCTYPE 
html>\n<html>\n<head>\n    <title>Digital Clock</title>\n    <link 
rel=\"stylesheet\" href=\"style.css\">\n</head>\n<body>\n    <div 
id=\"clock-container\">\n        <div id=\"digital-clock\">00:00</div>\n    
</div>\n    <script src=\"script.js\"></script>\n</body>\n</html>"}
</tool_call>
<tool_call>
{"name": "write_file", "arguments": {"path": "style.css", "content": 
".digital-clock { font-size: 4em; margin: 50px auto; display: block; text-align:
center; border: 2px solid #333; padding: 10px; background-color: #f0f8ff; 
border-radius: 10px; box-shadow: 5px 5px 15px rgba(0,0,0,0.2);}"}
</tool_call>
<tool_call>
{"name": "write_file", "arguments": {"path": "script.js", "content": "function 
updateClock() {\n    const now = new Date();\n    const hours = 
now.getHours().toString().padStart(2, '0');\n    const minutes = 
now.getMinutes().toString().padStart(2, '0');\n    
document.getElementById('digital-clock').innerText = 
`${hours}:${minutes}`;\n}\n\n// Update the clock every 
second\nsetInterval(updateClock, 1000);\n\n// Initialize the clock 
immediately\nupdateClock();"}
</tool_call>
print("I have created the necessary files: index.html (for structure), style.css
(for styling), and script.js (for functionality).")
"""
    calls = extract_all_tool_calls(user_log_output)
    assert len(calls) == 3
    paths = [c[1]["path"] for c in calls]
    assert paths == ["saat.html", "style.css", "script.js"]
    print("✓ test_user_log_exact_raw_unescaped_quotes passed")


if __name__ == "__main__":
    test_normalize_broken_tags()
    test_cleanup_json_trailing_gt()
    test_extract_tool_call_broken_tag()
    test_extract_tool_call_no_closing_tag()
    test_extract_tool_call_json_with_trailing_gt()
    test_extract_all_tool_calls_multiple()
    test_extract_all_broken_tags_multiple()
    test_extract_all_single_call_fallback()
    test_user_log_exact_raw_unescaped_quotes()
    print("\n🎉 Tüm testler başarılı!")
