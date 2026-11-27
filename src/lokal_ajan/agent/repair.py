"""Küçük modellerin araç çağrılarındaki tipik hataları onarır.

0.6B-4B modeller araç adını ve parametre adlarını sık sık "yaklaşık" yazar:
``create_file`` (write_file yerine), ``file_path`` / ``filename`` (path yerine),
``text`` / ``code`` (content yerine), ``"3"`` (3 yerine). Eski davranışta bu
çağrılar sessizce atılıyor ve model boş yere bir "bozuk çağrı" turu harcıyordu.

Bu modül üç şey yapar:
- `resolve_tool_name`: takma ad tablosu + bulanık eşleşme ile gerçek araç adını bulur.
- `repair_args`: parametre adlarını/tiplerini aracın şemasına göre düzeltir.
- `format_tool_usage` / `explain_validation_error`: model hata yaptığında ona
  KISA ve uygulanabilir bir düzeltme ipucu üretir (örnek çağrı dahil).
"""

import difflib
import json
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Modellerin sık uydurduğu araç adları -> gerçek ad
TOOL_ALIASES: Dict[str, str] = {
    "create_file": "write_file",
    "createfile": "write_file",
    "save_file": "write_file",
    "writefile": "write_file",
    "write": "write_file",
    "new_file": "write_file",
    "make_file": "write_file",
    "update_file": "edit_file",
    "modify_file": "edit_file",
    "replace_in_file": "edit_file",
    "str_replace": "edit_file",
    "editfile": "edit_file",
    "edit": "edit_file",
    "open_file": "read_file",
    "cat": "read_file",
    "view_file": "read_file",
    "readfile": "read_file",
    "read": "read_file",
    "ls": "list_dir",
    "list_files": "list_dir",
    "list_directory": "list_dir",
    "listdir": "list_dir",
    "dir": "list_dir",
    "find_files": "glob",
    "search_files": "glob",
    "search": "grep",
    "find_text": "grep",
    "search_code": "semantic_code_search",
    "code_search": "semantic_code_search",
    "shell": "run_shell",
    "bash": "run_shell",
    "run_command": "run_shell",
    "execute": "run_shell",
    "exec": "run_shell",
    "terminal": "run_shell",
    "cmd": "run_shell",
    "run": "run_shell",
    "delegate": "delegate_task",
}

# Parametre takma adları (aracın gerçek parametresi -> modelin yazabilecekleri)
ARG_ALIASES: Dict[str, Tuple[str, ...]] = {
    "path": ("file_path", "filepath", "filename", "file_name", "file", "dir", "directory", "folder", "dir_path", "name"),
    "content": ("text", "code", "contents", "data", "body", "file_content", "file_contents", "source"),
    "old_str": ("old", "old_string", "old_text", "search", "find", "original", "target", "before"),
    "new_str": ("new", "new_string", "new_text", "replace", "replacement", "replace_with", "after"),
    "command": ("cmd", "shell_command", "bash", "script", "commands"),
    "pattern": ("query", "regex", "glob_pattern", "search", "text", "keyword"),
    "task": ("description", "instruction", "prompt", "goal", "request"),
    "query": ("q", "search", "text", "question", "pattern"),
}


def _norm(name: str) -> str:
    return "".join(ch for ch in name.strip().lower().replace("-", "_").replace(" ", "_") if ch.isalnum() or ch == "_")


def resolve_tool_name(name: Any, valid_names: Iterable[str]) -> Optional[str]:
    """Modelin yazdığı araç adını gerçek bir araç adına eşler; bulamazsa None."""
    if not isinstance(name, str) or not name.strip():
        return None
    valid = list(valid_names)
    if name in valid:
        return name
    n = _norm(name)
    for v in valid:
        if _norm(v) == n:
            return v
    alias = TOOL_ALIASES.get(n)
    if alias and alias in valid:
        return alias
    # alt çizgisiz karşılaştırma: "readfile" -> read_file
    squashed = n.replace("_", "")
    for v in valid:
        if v.replace("_", "") == squashed:
            return v
    close = difflib.get_close_matches(n, [_norm(v) for v in valid], n=1, cutoff=0.82)
    if close:
        for v in valid:
            if _norm(v) == close[0]:
                return v
    return None


def _coerce(value: Any, annotation_type: str) -> Any:
    """JSON şemasındaki tipe göre basit tür dönüşümü ("3" -> 3, "true" -> True)."""
    try:
        if annotation_type == "integer" and isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value.strip())
        if annotation_type == "integer" and isinstance(value, float) and value.is_integer():
            return int(value)
        if annotation_type == "number" and isinstance(value, str):
            return float(value.strip())
        if annotation_type == "boolean" and isinstance(value, str):
            low = value.strip().lower()
            if low in ("true", "evet", "yes", "1"):
                return True
            if low in ("false", "hayır", "hayir", "no", "0"):
                return False
        if annotation_type == "string" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
        if annotation_type == "string" and isinstance(value, list) and all(isinstance(v, str) for v in value):
            return "\n".join(value)
        if annotation_type in ("array", "object") and isinstance(value, str):
            parsed = json.loads(value)
            return parsed
    except (ValueError, TypeError, json.JSONDecodeError):
        pass
    return value


def _prop_type(schema: Dict[str, Any]) -> str:
    if "type" in schema:
        return schema["type"]
    for sub in schema.get("anyOf", []) or []:
        t = sub.get("type")
        if t and t != "null":
            return t
    return "any"


def repair_args(args: Any, tool_schema: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Parametre adlarını ve tiplerini aracın şemasına göre düzeltir.

    - Bilinen takma adları gerçek ada çevirir (yalnızca gerçek ad eksikse).
    - Tek zorunlu parametreli araçta, tek bilinmeyen anahtarı o parametreye atar.
    - Tipleri şemaya göre dönüştürür.
    - Şemada olmayan fazlalık anahtarları atar (pydantic zaten yok sayardı ama
      model "extra" yüzünden hata almasın).
    """
    if not isinstance(args, dict):
        if isinstance(args, str) and tool_schema:
            required = (tool_schema.get("parameters", {}) or {}).get("required", []) or []
            if len(required) == 1:
                return {required[0]: args}
        return {} if not isinstance(args, dict) else args
    if not tool_schema:
        return args

    params = tool_schema.get("parameters", {}) or {}
    props: Dict[str, Any] = params.get("properties", {}) or {}
    required: List[str] = list(params.get("required", []) or [])
    if not props:
        return args

    fixed: Dict[str, Any] = {}
    leftovers: Dict[str, Any] = {}
    for key, value in args.items():
        if key in props:
            fixed[key] = value
        else:
            leftovers[key] = value

    # takma ad eşlemesi
    for real in list(props.keys()):
        if real in fixed:
            continue
        for alias in ARG_ALIASES.get(real, ()):
            if alias in leftovers:
                fixed[real] = leftovers.pop(alias)
                break
        else:
            norm_map = {_norm(k): k for k in leftovers}
            if _norm(real) in norm_map:
                fixed[real] = leftovers.pop(norm_map[_norm(real)])

    # tek eksik zorunlu parametre + tek bilinmeyen anahtar -> eşle
    missing = [r for r in required if r not in fixed]
    if len(missing) == 1 and len(leftovers) == 1:
        (_, val), = leftovers.items()
        fixed[missing[0]] = val
        leftovers.clear()

    for key, value in list(fixed.items()):
        fixed[key] = _coerce(value, _prop_type(props.get(key, {})))
    return fixed


_EXAMPLE_VALUES = {
    "path": "file.txt",
    "content": "...",
    "old_str": "old text",
    "new_str": "new text",
    "command": "ls",
    "pattern": "*.py",
    "task": "...",
    "query": "...",
}


def format_tool_usage(tool_schema: Dict[str, Any]) -> str:
    """Tek satırlık kullanım + örnek: `edit_file(path:string, old_str:string, new_str:string)` + <tool_call> örneği."""
    params = tool_schema.get("parameters", {}) or {}
    props = params.get("properties", {}) or {}
    required = set(params.get("required", []) or [])
    sig = ", ".join(f"{k}{'' if k in required else '?'}:{_prop_type(v)}" for k, v in props.items())
    example_args = {
        k: _EXAMPLE_VALUES.get(k, "...")
        for k in props
        if k in required
    }
    example = json.dumps({"name": tool_schema["name"], "arguments": example_args}, ensure_ascii=False)
    return f"{tool_schema['name']}({sig})\n<tool_call>\n{example}\n</tool_call>"


def explain_validation_error(tool_schema: Optional[Dict[str, Any]], error: Exception) -> str:
    """Pydantic doğrulama hatasını modelin anlayacağı kısa bir ipucuna çevirir."""
    lines: List[str] = []
    try:
        errors = error.errors()  # type: ignore[attr-defined]
    except Exception:
        errors = []
    for err in errors[:3]:
        loc = ".".join(str(p) for p in err.get("loc", ()))
        kind = err.get("type", "")
        if kind == "missing":
            lines.append(f"missing required argument '{loc}'")
        else:
            lines.append(f"argument '{loc}': {err.get('msg', 'invalid')}")
    if not lines:
        lines.append(str(error)[:160])
    msg = "Error: invalid arguments: " + "; ".join(lines) + "."
    if tool_schema:
        msg += "\nCorrect usage:\n" + format_tool_usage(tool_schema)
    return msg


def unknown_tool_message(name: str, valid_names: Iterable[str], limit: int = 12) -> str:
    valid = sorted(valid_names)[:limit]
    close = difflib.get_close_matches(_norm(str(name)), [_norm(v) for v in valid], n=2, cutoff=0.5)
    hint = f" Did you mean: {', '.join(close)}?" if close else ""
    return f"Error: unknown tool '{name}'.{hint} Available tools: {', '.join(valid)}."
