import json
import re
import ast
from typing import Dict, Any, Tuple, Optional, Set, List
from lokal_ajan.tools.registry import registry
from lokal_ajan.agent.thinking import strip_thinking


def _normalize_broken_tags(text: str) -> str:
    """Fix broken XML-like tags produced by small/quantized models.

    Common breakages seen in the wild:
      - ``<tool_ca\\n\\nll>``  (whitespace inserted mid-tag)
      - ``</tool_call >``    (trailing space before ``>``)
      - ``</ tool_call>``    (space after ``/``)
      - ``</tool_call}``     (stray ``}`` instead of ``>``)

    This normaliser collapses all whitespace inside ``<…>`` tokens that
    look like they *should* be ``<tool_call>`` or ``</tool_call>`` and
    replaces them with the canonical form.
    """
    # Opening tag: allow arbitrary whitespace between the characters of "tool_call"
    text = re.sub(
        r'<\s*t\s*o\s*o\s*l\s*[_\s]*c\s*a\s*l\s*l?\s*>',
        '<tool_call>',
        text,
        flags=re.IGNORECASE,
    )
    # Closing tag: same, but with optional "/" prefix
    text = re.sub(
        r'<\s*/\s*t\s*o\s*o\s*l\s*[_\s]*c\s*a\s*l\s*l?\s*>',
        '</tool_call>',
        text,
        flags=re.IGNORECASE,
    )
    return text


def _build_valid_names(extra_valid_names: Optional[Set[str]] = None) -> Set[str]:
    """Get set of registered tool names, merged with any caller-supplied extras."""
    valid: Set[str] = {tool.name for tool in registry.get_all_tools()}
    if extra_valid_names:
        valid = valid | extra_valid_names
    return valid


def extract_tool_call(text: str, extra_valid_names: Optional[Set[str]] = None) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Extracts a tool call from the model's text output.
    Supports both JSON format and Function-call format (e.g. LFM/Llama style).

    Parameters
    ----------
    text : str
        Raw model output to parse.
    extra_valid_names : set[str], optional
        Additional tool names (beyond the global registry) that should be
        considered valid.  Use this to inject locally-held tools such as
        ``delegate_task`` that are NOT registered in the global registry.

    Strategies in order:
      0. Strip <think>...</think> blocks (Qwen3-style hybrid thinking). A
         tool call inside a thinking block should never be executed, and
         letting it leak in confuses every strategy below.
      0.5. Normalize broken tags (<tool_ca\\nll> → <tool_call>).
      1. <|tool_call_start|>...<|tool_call_end|> (LFM/Llama special tokens)
      2. <tool_call>...</tool_call> tags
      3. ```json ... ``` markdown blocks
      4. Function call regex / AST parsing: [tool_name(args...)] or tool_name(args...)
         (Must match a registered tool in registry)
      5. Raw JSON block with brace matching
      6. Fallback for weak models: If model outputs a code block and specifies a filename
         like "save this code as `saat.html`", infer write_file(path, content).
    """
    text = strip_thinking(text)

    # Normalize broken tags before any strategy runs
    text = _normalize_broken_tags(text)

    # Get set of registered tool names to filter false positives.
    # Merge with any caller-supplied extra names (e.g. delegate_task which lives
    # only on the AgentLoop instance and is not in the global registry).
    valid_tool_names: Set[str] = _build_valid_names(extra_valid_names)

    # Strategy 1: <|tool_call_start|>...<|tool_call_end|>
    lfm_match = re.search(r"<\|tool_call_start\|>(.*?)<\|tool_call_end\|>", text, re.DOTALL)
    if lfm_match:
        inner = lfm_match.group(1).strip()
        result = _try_parse_tool_json(inner) or _try_parse_function_call(inner) or _try_parse_xml_tool_call(inner)
        if result and result[0] in valid_tool_names:
            return result

    # Strategy 2: Explicit <tool_call> tags
    # Try with proper closing tag first, then fall back to unclosed <tool_call>
    tag_match = re.search(r"<tool_call>(.*?)</tool_call>", text, re.DOTALL)
    if not tag_match:
        # Fallback: <tool_call> without closing tag — grab everything after it
        tag_match = re.search(r"<tool_call>(.*)", text, re.DOTALL)
    if tag_match:
        inner = tag_match.group(1).strip()
        result = _try_parse_tool_json(inner) or _try_parse_function_call(inner) or _try_parse_xml_tool_call(inner)
        # If direct parse failed, try extracting balanced JSON from the inner text
        if not result:
            balanced = _extract_balanced_json(inner)
            if balanced:
                result = _try_parse_tool_json(balanced)
        if result and result[0] in valid_tool_names:
            return result

    # Strategy 2.5: XML-based tool calls (Nemotron, Hermes, Mistral, Qwen XML tags)
    # e.g. <function=delegate_task><parameter=task>...</parameter></function>
    xml_result = _try_parse_xml_tool_call(text)
    if xml_result and (not valid_tool_names or xml_result[0] in valid_tool_names):
        return xml_result

    # Strategy 3: Markdown code block (```json ... ```)
    md_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if md_match:
        block = md_match.group(1).strip()
        json_str = _extract_balanced_json(block)
        if json_str:
            result = _try_parse_tool_json(json_str)
            if result and result[0] in valid_tool_names:
                return result


    # Strategy 4: Bracketed or raw function call syntax e.g. [write_file(path="...")] or write_file(path="...")
    # Strip non-tool markdown code blocks (```html...```, ```js...``` etc.) to avoid matching JS inside code examples
    text_no_codeblocks = re.sub(r"```(?:(?!json)[a-zA-Z0-9_-]+)?\s*\n?.*?\n?\s*```", "", text, flags=re.DOTALL)

    fn_candidates = re.findall(r"\[?\b[a-zA-Z_][a-zA-Z0-9_]*\s*\([\s\S]*?\)\s*\]?", text_no_codeblocks)
    for cand in fn_candidates:
        result = _try_parse_function_call(cand)
        if result and (not valid_tool_names or result[0] in valid_tool_names):
            return result

    # Strategy 5: Find any balanced { ... } that looks like a tool call
    json_str = _extract_balanced_json(text)
    if json_str:
        result = _try_parse_tool_json(json_str)
        if result and (not valid_tool_names or result[0] in valid_tool_names):
            return result

    # Strategy 6: Fallback for weak/conversational models that output code blocks
    # (with a filename hint in the surrounding text like "**2. HTML (index.html)**"
    # or "save this code as `saat.html`") but never emit a proper tool call.
    # Saves the code blocks to files instead of just displaying them.
    if "write_file" in valid_tool_names:
        # Ignore if the model is just summarizing an already created file
        already_done_pattern = r"(?:has been|was)\s+(?:successfully\s+)?(?:created|saved|written)|successfully\s+(?:created|saved|written)|başa?r[ıi]yla\s+(?:olu[şs]turuldu|kaydedildi)|here's the content|here is the content"
        if not re.search(already_done_pattern, text, re.IGNORECASE):
            pairs = _extract_code_files_with_names(text)
            if pairs:
                if len(pairs) == 1:
                    path, content = pairs[0]
                    return "write_file", {"path": path, "content": content}
                # Multiple files (e.g. index.html + style.css + script.js):
                # return a batch pseudo-tool handled by the agent loop.
                return "_write_multiple", {"files": pairs}

    # Strategy 7: Fallback for shell commands
    if "run_shell" in valid_tool_names:
        bash_match = re.search(r"```(?:bash|sh)\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if bash_match:
            cmd = bash_match.group(1).strip()
            if cmd:
                return "run_shell", {"command": cmd}

    return None


def extract_all_tool_calls(text: str, extra_valid_names: Optional[Set[str]] = None) -> List[Tuple[str, Dict[str, Any]]]:
    """Extract ALL tool calls from a single model response.

    When a model produces multiple ``<tool_call>`` blocks in one turn (e.g.
    saat.html + style.css + script.js), this function returns them all as a
    list so the agent loop can execute them sequentially without re-querying
    the LLM.

    Falls back to :func:`extract_tool_call` when no multi-block pattern is
    found (i.e. single tool call or non-tag formats).
    """
    text = strip_thinking(text)
    text = _normalize_broken_tags(text)
    valid_tool_names = _build_valid_names(extra_valid_names)

    results: List[Tuple[str, Dict[str, Any]]] = []

    # Find all <tool_call>...</tool_call> blocks
    tag_blocks = list(re.finditer(r"<tool_call>(.*?)</tool_call>", text, re.DOTALL))

    if tag_blocks:
        for m in tag_blocks:
            inner = m.group(1).strip()
            result = _try_parse_tool_json(inner) or _try_parse_function_call(inner) or _try_parse_xml_tool_call(inner)
            if not result:
                balanced = _extract_balanced_json(inner)
                if balanced:
                    result = _try_parse_tool_json(balanced)
            if result and result[0] in valid_tool_names:
                results.append(result)
        if results:
            return results

    # Also check for unclosed <tool_call> blocks (model stops mid-tag)
    # Split on <tool_call> and try to parse each segment
    if "<tool_call>" in text:
        segments = text.split("<tool_call>")[1:]  # skip text before first tag
        for seg in segments:
            # Strip closing tag if present
            seg = re.sub(r"</tool_call>.*", "", seg, count=1, flags=re.DOTALL).strip()
            result = _try_parse_tool_json(seg) or _try_parse_function_call(seg) or _try_parse_xml_tool_call(seg)
            if not result:
                balanced = _extract_balanced_json(seg)
                if balanced:
                    result = _try_parse_tool_json(balanced)
            if result and result[0] in valid_tool_names:
                results.append(result)
        if results:
            return results

    # Fallback: delegate to single-call extractor
    single = extract_tool_call(text, extra_valid_names)
    if single:
        return [single]
    return []

_FILENAME_RE = r"[a-zA-Z0-9_\-]+(?:\.[a-zA-Z0-9_\-]+)*\.(?:html?|css|js|py|txt|json|toml|ya?ml|md|sh|ts|tsx|jsx|go|rs|java|cpp|c|h|sql)"

def _extract_code_files_with_names(text: str) -> list:
    """
    Extracts (filename, code) pairs from markdown code blocks that have a
    filename hint nearby (section heading, "save as X", backtick names, etc.).
    Returns an empty list when no block has a usable filename.
    """
    blocks = list(re.finditer(r"```([a-zA-Z0-9_+.-]*)\s*\n?(.*?)```", text, re.DOTALL))
    pairs = []
    seen = set()
    for m in blocks:
        lang = (m.group(1) or "").strip().lower()
        code = m.group(2).strip("\n")
        if lang == "json" or not code.strip():
            continue
        start, end = m.start(), m.end()
        # Look at text just before the block (headings usually live there) ...
        prefix = text[max(0, start - 1000):start]
        # ... and after it (for "save this as `x.html`" or "Dosyayı `x.html` olarak kaydedin"),
        # stopping at the next code fence so we don't grab the next section's filename.
        next_fence = text.find("```", end + 3)
        suffix = text[end:next_fence] if next_fence != -1 else text[end:]
        filename = _nearest_filename(prefix, suffix)
        if filename and filename not in seen:
            seen.add(filename)
            pairs.append((filename, code))
    return pairs

def _nearest_filename(prefix: str, suffix: str) -> Optional[str]:
    """Find the filename closest to a code block: the last one before it,
    falling back to the first one after it."""
    # 1. Last filename in the prefix (closest to the block start)
    match = None
    for match in re.finditer(r"[`'\"( ](" + _FILENAME_RE + r")[`'\")\s]?", prefix, re.IGNORECASE):
        pass
    if match:
        return match.group(1)
    # 2. First filename in the suffix (e.g. "save this code as `saat.html`" or "Dosyayı `ajanda.html` olarak kaydedin")
    match = re.search(r"[`'\"( ](" + _FILENAME_RE + r")[`'\")\s]?", suffix, re.IGNORECASE)
    if match:
        return match.group(1)
    return None

def _find_filename_in_text(context: str) -> Optional[str]:
    """Find a plausible code filename (index.html, style.css, app.js...) in text."""
    # Preferred: filename preceded by a delimiter (backtick, quote, paren, space)
    m = re.search(r"[`'\"( ](" + _FILENAME_RE + r")[`'\")\s]?", context, re.IGNORECASE)
    if m:
        return m.group(1)
    return None
def _try_parse_function_call(expr_str: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Parses function call syntax like `write_file(path="saat.html", content="...")`
    or `[write_file(path="saat.html", content="...")]`.
    """
    expr_str = expr_str.strip()
    if expr_str.startswith("[") and expr_str.endswith("]"):
        expr_str = expr_str[1:-1].strip()

    try:
        parsed = ast.parse(expr_str, mode='eval')
        if isinstance(parsed.body, ast.Call):
            call_node = parsed.body
            if isinstance(call_node.func, ast.Name):
                tool_name = call_node.func.id
                args = {}
                for kw in call_node.keywords:
                    if kw.arg:
                        try:
                            args[kw.arg] = ast.literal_eval(kw.value)
                        except Exception:
                            pass
                return tool_name, args
    except Exception:
        pass
    return None

def _extract_balanced_json(text: str) -> Optional[str]:
    """
    Find the first balanced JSON object in text using brace counting.
    Respects string literals (won't count braces inside quotes).
    """
    start = text.find('{')
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        ch = text[i]

        if escape_next:
            escape_next = False
            continue

        if ch == '\\' and in_string:
            escape_next = True
            continue

        if ch == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]

    return None

def _try_parse_malformed_tool_call(text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Recovers tool calls when small models generate invalid JSON, such as:
    - Unescaped double quotes inside "content" (e.g. HTML attributes rel="stylesheet")
    - Unescaped raw newlines or control characters
    - Truncated closing braces or stray markdown artifacts
    """
    # 1. Recovery for write_file
    if "write_file" in text:
        path_m = re.search(r'["\']path["\']\s*:\s*["\']([^"\']+)["\']', text)
        content_m = re.search(r'["\']content["\']\s*:\s*["\']', text)
        if path_m and content_m:
            path = path_m.group(1).strip()
            rest = text[content_m.end():]
            end_m = re.search(r'["\']\s*\}[\s\}]*$', rest)
            if end_m:
                content = rest[:end_m.start()]
            else:
                content = re.sub(r'[\s"\}\]]*(?:</tool_call>)?$', '', rest)
            if "\\n" in content and "\n" not in content:
                content = content.replace("\\n", "\n").replace('\\"', '"').replace("\\t", "\t")
            return "write_file", {"path": path, "content": content}

    # 2. Recovery for edit_file
    if "edit_file" in text:
        path_m = re.search(r'["\']path["\']\s*:\s*["\']([^"\']+)["\']', text)
        old_m = re.search(r'["\']old_str["\']\s*:\s*["\']', text)
        new_m = re.search(r'["\']new_str["\']\s*:\s*["\']', text)
        if path_m and old_m and new_m:
            path = path_m.group(1).strip()
            old_start = old_m.end()
            before_new = text[old_start:new_m.start()]
            end_old = re.search(r'["\']\s*,\s*["\']new_str["\']\s*:\s*["\']', before_new)
            if end_old:
                old_str = before_new[:end_old.start()]
                rest = text[old_start + end_old.end():]
                end_new = re.search(r'["\']\s*\}[\s\}]*$', rest)
                new_str = rest[:end_new.start()] if end_new else rest.rstrip('}" \t\n')
                return "edit_file", {"path": path, "old_str": old_str, "new_str": new_str}

    # 3. Recovery for run_shell
    if "run_shell" in text:
        cmd_m = re.search(r'["\']command["\']\s*:\s*["\']', text)
        if cmd_m:
            rest = text[cmd_m.end():]
            end_m = re.search(r'["\']\s*\}[\s\}]*$', rest)
            cmd = rest[:end_m.start()] if end_m else rest.rstrip('}" \t\n')
            return "run_shell", {"command": cmd}

    return None


def _try_parse_tool_json(json_str: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Try to parse a JSON string as a tool call.
    Handles common malformed JSON from small models (unescaped quotes, newlines, etc.).
    """
    json_str = _cleanup_json(json_str)

    try:
        data = json.loads(json_str, strict=False)
    except json.JSONDecodeError:
        return _try_parse_malformed_tool_call(json_str)

    if not isinstance(data, dict):
        return _try_parse_malformed_tool_call(json_str)

    # Format: {"tool": "name", "args": {...}}
    if "tool" in data and "args" in data:
        return data["tool"], data["args"]

    # OpenAI format: {"name": "...", "arguments": {...}}
    if "name" in data and "arguments" in data:
        return data["name"], data["arguments"]

    return _try_parse_malformed_tool_call(json_str)

def _cleanup_json(json_str: str) -> str:
    """Attempt basic cleanup of malformed JSON common in small models."""
    # Remove trailing commas before closing braces/brackets
    json_str = re.sub(r",(\s*[}\]])", r"\1", json_str)
    # Remove stray ">" after closing brace — e.g. "}>" produced by some models
    json_str = re.sub(r"\}\s*>", "}", json_str)
    # Strip any trailing garbage after the last balanced "}"
    # (e.g. "</tool_call>" remnants appended to the JSON)
    last_brace = json_str.rfind("}")
    if last_brace != -1:
        json_str = json_str[:last_brace + 1]
    return json_str

def _try_parse_xml_tool_call(text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Parse XML-style tool calls used by Nemotron, Hermes, Mistral, and Qwen models.
    Supports formats:
      1. <function=name><parameter=key>val</parameter></function>
      2. <function name="name"><parameter name="key">val</parameter></function>
      3. <function=name><key>val</key></function>
      4. <tool_call><name>name</name><arguments>...</arguments></tool_call>
      5. <tool_name><param>val</param></tool_name>
    """
    if not text or not ('<' in text and '>' in text):
        return None

    # Format 1 & 2: <function=name>...</function> or <function name="name">...</function>
    func_pattern = re.compile(
        r'<function(?:=|\s+name=|\s+)[\"\'\']?([a-zA-Z0-9_]+)[\"\'\']?>(.*?)(?:</function>|$)',
        re.DOTALL | re.IGNORECASE
    )
    m = func_pattern.search(text)
    if m:
        func_name = m.group(1).strip()
        body = m.group(2)
        
        param_pattern = re.compile(
            r'<parameter(?:=|\s+name=|\s+)[\"\'\']?([a-zA-Z0-9_]+)[\"\'\']?>(.*?)(?:</parameter>|$)',
            re.DOTALL | re.IGNORECASE
        )
        params = param_pattern.findall(body)
        if params:
            args = {pname.strip(): pval.strip() for pname, pval in params}
            return func_name, args
        else:
            tag_params = re.findall(r'<([a-zA-Z0-9_]+)>(.*?)</\1>', body, re.DOTALL)
            if tag_params:
                args = {pname.strip(): pval.strip() for pname, pval in tag_params if pname.lower() not in ('function', 'parameter', 'tool_call')}
                if args:
                    return func_name, args

    # Format 4: <tool_call><name>name</name><arguments>...</arguments></tool_call>
    name_pattern = re.compile(r'<(?:tool_name|name)>([a-zA-Z0-9_]+)</(?:tool_name|name)>', re.IGNORECASE)
    nm = name_pattern.search(text)
    if nm:
        func_name = nm.group(1).strip()
        arg_block = re.search(r'<(?:arguments|parameters|args)>(.*?)(?:</(?:arguments|parameters|args)>|$)', text, re.DOTALL | re.IGNORECASE)
        if arg_block:
            body = arg_block.group(1).strip()
            try:
                args = json.loads(body)
                if isinstance(args, dict):
                    return func_name, args
            except Exception:
                pass
            tag_params = re.findall(r'<([a-zA-Z0-9_]+)>(.*?)</\1>', body, re.DOTALL)
            if tag_params:
                args = {pname.strip(): pval.strip() for pname, pval in tag_params}
                return func_name, args

    # Format 5: <tool_name><param>val</param></tool_name>
    direct_tool = re.search(r'<([a-zA-Z_][a-zA-Z0-9_]*)>(.*?)</\1>', text, re.DOTALL)
    if direct_tool:
        tname = direct_tool.group(1).strip()
        if tname.lower() not in ('think', 'tool_call', 'tool_response'):
            body = direct_tool.group(2).strip()
            tag_params = re.findall(r'<([a-zA-Z0-9_]+)>(.*?)</\1>', body, re.DOTALL)
            if tag_params:
                args = {pname.strip(): pval.strip() for pname, pval in tag_params}
                return tname, args

    return None

