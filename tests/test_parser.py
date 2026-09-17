import sys
sys.path.insert(0, "src")

# Ensure fs_tools are registered
import lokal_ajan.tools.fs_tools

from lokal_ajan.agent.parser import extract_tool_call, _cleanup_json, _extract_balanced_json, _try_parse_function_call

def test_extract_tag_format():
    text = '<tool_call>{"tool": "read_file", "args": {"path": "test.txt"}}</tool_call>'
    result = extract_tool_call(text)
    assert result is not None
    tool, args = result
    assert tool == "read_file"
    assert args == {"path": "test.txt"}

def test_extract_lfm_function_format():
    text = '<|tool_call_start|>[write_file(path="saat.html", content="<html></html>")]<|tool_call_end|>I created the clock.'
    result = extract_tool_call(text)
    assert result is not None, f"Failed on: {text}"
    tool, args = result
    assert tool == "write_file"
    assert args == {"path": "saat.html", "content": "<html></html>"}

def test_extract_raw_function_call():
    text = 'Sure, here: [write_file(path="saat.html", content="hello")]'
    result = extract_tool_call(text)
    assert result is not None, f"Failed on: {result}"
    tool, args = result
    assert tool == "write_file"
    assert args["path"] == "saat.html"

def test_ignore_js_functions_in_html_codeblock():
    text = """Here is the code:
```html
<script>
  document.getElementById('clock').textContent = new Date().toLocaleTimeString();
</script>
```
Please review it."""
    result = extract_tool_call(text)
    assert result is None, f"Should NOT detect getElementById as a tool call, got: {result}"

def test_strategy_6_conversational_code_saving():
    text = """I will create the digital clock file for you. Here is the code:

```html
<!DOCTYPE html>
<html>
<head>
<title>Clock</title>
</head>
<body>
<h1 id="clock"></h1>
</body>
</html>
```

Please save this code as `saat.html`."""
    result = extract_tool_call(text)
    assert result is not None, f"Failed on strategy 6: {text}"
    tool, args = result
    assert tool == "write_file"
    assert args["path"] == "saat.html"
    assert "<title>Clock</title>" in args["content"]

def test_ignore_already_created_summary_text():
    """When the model replies after executing write_file, it summaries the code created. This should NOT trigger write_file again."""
    text = """The file "merhaba.html" has been successfully created with the greeting message. Here's the content:

```html
<!DOCTYPE html>
<html>
<head>
 <title>Merhaba Dünya</title>
</head>
<body>
 <h1 id="greeting">Merhaba Dünya</h1>
</body>
</html>
```

Let me know if you'd like to add interactivity!"""
    result = extract_tool_call(text)
    assert result is None, f"Should NOT trigger write_file again on summary text, got: {result}"

def test_extract_markdown_json_simple():
    text = 'Here is the tool call:\n```json\n{"tool": "write_file", "args": {"path": "a.txt", "content": "hi"}}\n```'
    result = extract_tool_call(text)
    assert result is not None
    tool, args = result
    assert tool == "write_file"
    assert args == {"path": "a.txt", "content": "hi"}

def test_extract_markdown_json_with_nested_braces():
    content = '<!DOCTYPE html>\\n<style>\\n  body {\\n    color: red;\\n  }\\n</style>'
    text = f'I will create it.\n```json\n{{"tool": "write_file", "args": {{"path": "saat.html", "content": "{content}"}}}}\n```'
    result = extract_tool_call(text)
    assert result is not None, f"Failed to parse tool call from: {text}"
    tool, args = result
    assert tool == "write_file"
    assert args["path"] == "saat.html"
    assert "body" in args["content"]

def test_extract_raw_json():
    text = 'Sure, let me do that. {"tool": "list_dir", "args": {"path": "."}}'
    result = extract_tool_call(text)
    assert result is not None
    tool, args = result
    assert tool == "list_dir"

def test_balanced_json_extraction():
    text = 'prefix {"a": {"b": "c"}} suffix'
    result = _extract_balanced_json(text)
    assert result == '{"a": {"b": "c"}}'

def test_braces_inside_strings_ignored():
    text = '{"key": "value with { and } inside"}'
    result = _extract_balanced_json(text)
    assert result == text

def test_cleanup_trailing_comma():
    dirty_json = '{"tool": "test", "args": {"a": 1,},}'
    clean = _cleanup_json(dirty_json)
    import json
    data = json.loads(clean)
    assert data["tool"] == "test"
    assert data["args"]["a"] == 1

def test_no_tool_call():
    text = "Hello! How can I help you?"
    result = extract_tool_call(text)
    assert result is None

def test_strategy_6_single_file_with_heading():
    text = """**2. HTML (index.html)**
```html
<!DOCTYPE html>
<html><body><h1>Test</h1></body></html>
```
"""
    result = extract_tool_call(text)
    assert result is not None, f"Failed on heading + single block: {text}"
    tool, args = result
    assert tool == "write_file"
    assert args["path"] == "index.html"
    assert "<h1>Test</h1>" in args["content"]

def test_strategy_6_multi_file_with_headings():
    """Brain model replies with a plan + 3 code blocks, never a tool call.
    The parser should save all blocks as files (batch write)."""
    text = """**1. HTML (index.html)**
```html
<!DOCTYPE html>
<html><body><h1>Test</h1></body></html>
```

**2. CSS (style.css)**
```css
body { color: red; }
```

**3. JS (script.js)**
```js
console.log("hi");
```
"""
    result = extract_tool_call(text)
    assert result is not None, f"Failed on multi-file output: {text}"
    tool, args = result
    assert tool == "_write_multiple"
    files = args["files"]
    assert len(files) == 3
    names = [f[0] for f in files]
    assert "index.html" in names
    assert "style.css" in names
    assert "script.js" in names
    by_name = {f[0]: f[1] for f in files}
    assert "color: red" in by_name["style.css"]
    assert 'console.log("hi")' in by_name["script.js"]

def test_strategy_6_code_block_without_filename_no_save():
    text = """Here is some example code:
```python
def hello():
    print("hi")
```
That's just an illustration, no file needed."""
    result = extract_tool_call(text)
    assert result is None, f"Should not save without a filename hint, got: {result}"

def test_extract_xml_tool_call_nemotron():
    text = """<tool_call>
<function=delegate_task>
<parameter=task>
Create a blog site with admin panel
</parameter>
</function>
</tool_call>"""
    result = extract_tool_call(text, extra_valid_names={"delegate_task"})
    assert result is not None, f"Failed to extract XML tool call: {text}"
    tool, args = result
    assert tool == "delegate_task"
    assert args["task"] == "Create a blog site with admin panel"

def test_extract_xml_tool_call_attributes():
    text = """<function name="write_file">
<parameter name="path">blog.html</parameter>
<parameter name="content"><h1>Blog</h1></parameter>
</function>"""
    result = extract_tool_call(text)
    assert result is not None
    tool, args = result
    assert tool == "write_file"
    assert args["path"] == "blog.html"
    assert args["content"] == "<h1>Blog</h1>"

def test_extract_xml_tool_call_direct():
    text = """<write_file>
<path>app.js</path>
<content>console.log("ready")</content>
</write_file>"""
    result = extract_tool_call(text)
    assert result is not None
    tool, args = result
    assert tool == "write_file"
    assert args["path"] == "app.js"
    assert args["content"] == 'console.log("ready")'

if __name__ == "__main__":
    tests = [
        test_extract_tag_format,
        test_extract_lfm_function_format,
        test_extract_raw_function_call,
        test_ignore_js_functions_in_html_codeblock,
        test_strategy_6_conversational_code_saving,
        test_ignore_already_created_summary_text,
        test_extract_markdown_json_simple,
        test_extract_markdown_json_with_nested_braces,
        test_extract_raw_json,
        test_balanced_json_extraction,
        test_braces_inside_strings_ignored,
        test_cleanup_trailing_comma,
        test_no_tool_call,
        test_strategy_6_single_file_with_heading,
        test_strategy_6_multi_file_with_headings,
        test_strategy_6_code_block_without_filename_no_save,
        test_extract_xml_tool_call_nemotron,
        test_extract_xml_tool_call_attributes,
        test_extract_xml_tool_call_direct,
    ]
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
        except AssertionError as e:
            print(f"  ✗ {t.__name__}: {e}")
        except Exception as e:
            print(f"  ✗ {t.__name__}: {type(e).__name__}: {e}")
    print("Tüm testler tamamlandı.")

