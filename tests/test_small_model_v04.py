import json
import os
import sys
import tempfile

sys.path.insert(0, "src")

from lokal_ajan.agent.context import (
    compact_history,
    prepare_context,
    truncate_tool_output,
)
from lokal_ajan.agent.parser import extract_all_tool_calls, extract_tool_call
from lokal_ajan.agent.prompt import CORE_TOOLS, get_system_prompt, tools_for_request
from lokal_ajan.agent.repair import (
    explain_validation_error,
    format_tool_usage,
    repair_args,
    resolve_tool_name,
    unknown_tool_message,
)
from lokal_ajan.llm.model_profiles import get_profile_for_model
from lokal_ajan.llm.ollama_client import tool_call_format_schema
from lokal_ajan.tools import fs_tools, git_tools, office_tools, claim_tools, semantic_search_tool  # noqa: F401
from lokal_ajan.tools.fs_tools import EditFileTool
from lokal_ajan.tools.registry import registry
from lokal_ajan.tools.shell_tool import RunShellTool

# run_shell normalde AgentLoop başlatılınca kaydedilir; testte elle kaydet.
if not registry.get_tool("run_shell"):
    registry.register(RunShellTool(workdir="."))

VALID = {t.name for t in registry.get_all_tools()}


# --- repair: araç adı ----------------------------------------------------

def test_resolve_tool_name_aliases_and_fuzzy():
    assert resolve_tool_name("write_file", VALID) == "write_file"
    assert resolve_tool_name("create_file", VALID) == "write_file"
    assert resolve_tool_name("readfile", VALID) == "read_file"
    assert resolve_tool_name("Read-File", VALID) == "read_file"
    assert resolve_tool_name("bash", VALID) == "run_shell"
    assert resolve_tool_name("list_files", VALID) == "list_dir"
    assert resolve_tool_name("totally_unknown_tool", VALID) is None
    assert resolve_tool_name(None, VALID) is None


# --- repair: parametreler -------------------------------------------------

def _schema(name):
    return registry.get_tool(name).get_schema()


def test_repair_args_aliases_and_types():
    fixed = repair_args({"file_path": "a.txt", "text": "hi"}, _schema("write_file"))
    assert fixed == {"path": "a.txt", "content": "hi"}

    fixed = repair_args({"path": "a.py", "start_line": "3", "end_line": "7"}, _schema("read_file"))
    assert fixed["start_line"] == 3 and fixed["end_line"] == 7


def test_repair_args_keeps_correct_args_untouched():
    args = {"path": "x", "old_str": "a", "new_str": "b"}
    assert repair_args(dict(args), _schema("edit_file")) == args


def test_repair_args_single_required_param_mapping():
    # tek zorunlu parametre + tek bilinmeyen anahtar -> eşlenir
    assert repair_args({"whatever": "src"}, _schema("list_dir")) == {"path": "src"}
    # düz string argüman
    assert repair_args("src", _schema("list_dir")) == {"path": "src"}


def test_explain_validation_error_is_actionable():
    from pydantic import ValidationError

    schema = _schema("edit_file")
    try:
        registry.get_tool("edit_file").args_schema(path="a")
    except ValidationError as e:
        msg = explain_validation_error(schema, e)
    assert "missing required argument 'old_str'" in msg
    assert "<tool_call>" in msg and "edit_file" in msg


def test_format_tool_usage_contains_example():
    usage = format_tool_usage(_schema("write_file"))
    assert usage.startswith("write_file(path:string, content:string)")
    assert '"name": "write_file"' in usage


def test_unknown_tool_message_suggests_close_name():
    msg = unknown_tool_message("read_fil", ["read_file", "write_file"])
    assert "read_file" in msg and "unknown tool" in msg


# --- parser entegrasyonu ---------------------------------------------------

def test_parser_resolves_alias_name_and_args():
    text = '<tool_call>\n{"name": "create_file", "arguments": {"file_path": "a.txt", "text": "hi"}}\n</tool_call>'
    assert extract_all_tool_calls(text) == [("write_file", {"path": "a.txt", "content": "hi"})]
    assert extract_tool_call(text) == ("write_file", {"path": "a.txt", "content": "hi"})


def test_parser_prose_function_call_is_strict():
    # düz metindeki "run(...)" bir araç çağrısı sayılmamalı
    assert extract_tool_call("You can call run(x) to start it.") is None


def test_parser_unknown_tool_still_rejected():
    text = '<tool_call>{"name": "launch_missiles", "arguments": {}}</tool_call>'
    assert extract_all_tool_calls(text) == []


# --- context -----------------------------------------------------------------

def test_truncate_keep_tail_preserves_end_of_output():
    out = "A" * 1000 + "TRACEBACK_END"
    res = truncate_tool_output(out, 200, keep_tail=50)
    assert res.startswith("A" * 150)
    assert res.endswith("A" * 37 + "TRACEBACK_END")
    assert "atlandı" in res


def test_truncate_default_behaviour_unchanged():
    res = truncate_tool_output("x" * 5000, 100)
    assert res.startswith("x" * 100) and len(res) < 5000


def _tool_output_msg(name, body):
    return {"role": "user", "content": f"Araç(lar) çalıştırıldı ve şu sonuçları döndürdü:\n<tool_output>\n'{name}' → {body}\n</tool_output>\n(reminder)"}


def test_compact_history_shrinks_old_outputs_not_recent_and_does_not_mutate():
    big = "L" * 5000
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "task"},
        {"role": "assistant", "content": '<tool_call>{"name": "read_file", "arguments": {"path": "a.py"}}</tool_call>'},
        _tool_output_msg("read_file", big),
        {"role": "assistant", "content": "x"},
        {"role": "user", "content": "y"},
        {"role": "assistant", "content": "z"},
        _tool_output_msg("read_file", big),
    ]
    original = json.dumps(msgs)
    out = compact_history(msgs, keep_recent=2)
    assert json.dumps(msgs) == original  # girdi değişmedi
    assert len(out[3]["content"]) < 500  # eski çıktı küçüldü
    assert "özetlendi" in out[3]["content"]
    assert out[-1]["content"] == msgs[-1]["content"]  # son mesaj dokunulmadı


def test_compact_history_shrinks_old_written_file_bodies():
    body = "<html>" + "x" * 4000 + "</html>"
    call = json.dumps({"name": "write_file", "arguments": {"path": "index.html", "content": body}})
    msgs = [
        {"role": "assistant", "content": f"<tool_call>\n{call}\n</tool_call>"},
        {"role": "user", "content": "a"}, {"role": "user", "content": "b"},
        {"role": "user", "content": "c"}, {"role": "user", "content": "d"},
    ]
    out = compact_history(msgs, keep_recent=4)
    assert "index.html" in out[0]["content"]
    assert len(out[0]["content"]) < 400


def test_prepare_context_compacts_before_dropping_conversation():
    big = "L" * 6000
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "first task"}]
    for _ in range(3):
        msgs.append({"role": "assistant", "content": '<tool_call>{"name": "read_file", "arguments": {"path": "a"}}</tool_call>'})
        msgs.append(_tool_output_msg("read_file", big))
    result = prepare_context(msgs, max_context=4096)
    # eski çıktılar özetlendiği için "first task" mesajı atılmadan sığmalı
    assert any(m["content"] == "first task" for m in result)
    assert sum(len(m["content"]) for m in result) < 4096 * 3.5


# --- prompt / profil ---------------------------------------------------------------

def test_tiny_prompt_is_much_shorter_and_filters_tools():
    schemas = registry.get_all_schemas()
    tiny = get_system_prompt("minimal", schemas, workdir=".", tiny=True)
    normal = get_system_prompt("minimal", schemas, workdir=".")
    assert len(tiny) < len(normal) * 0.6
    assert "write_file is blocked on existing files" in tiny
    assert "You act, you don't just talk." in tiny
    for name in CORE_TOOLS:
        assert f"- {name}(" in tiny
    assert "- read_excel(" not in tiny and "- git_diff(" not in tiny


def test_tiny_prompt_adds_requested_tool_groups():
    schemas = registry.get_all_schemas()
    extra = tools_for_request("excel dosyasını oku, sonra pdf üret")
    prompt = get_system_prompt("minimal", schemas, workdir=".", tiny=True, extra_tools=extra)
    assert "- read_excel(" in prompt and "- write_pdf(" in prompt
    assert tools_for_request("hello") == set()


def test_profiles_tiny_flags():
    for name in ("qwen3:0.6b", "qwen3:1.7b", "qwen3.5:0.8b", "qwen2.5:0.5b"):
        p = get_profile_for_model(name)
        assert p.tiny and p.constrained_fallback and p.num_predict >= 3072
        assert p.top_k > 0 and 0 < p.top_p <= 1
    big = get_profile_for_model("qwen3:8b")
    assert not big.tiny and not big.constrained_fallback


def test_tool_call_format_schema():
    schema = tool_call_format_schema(["read_file", "write_file"])
    assert schema["properties"]["name"]["enum"] == ["read_file", "write_file"]
    assert schema["required"] == ["name", "arguments"]


# --- edit_file ipucu -------------------------------------------------------------------

def test_edit_file_not_found_shows_closest_lines():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "style.css")
        with open(path, "w", encoding="utf-8") as f:
            f.write("body {\n    background-color: #f4f4f4;\n    margin: 0;\n}\n")
        res = EditFileTool().run(path=path, old_str="background-colour: #f4f4f4;", new_str="x")
        assert res.startswith("Error")
        assert "Closest lines" in res
        assert "line 2" in res and "background-color" in res


def test_edit_file_not_found_without_close_match():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "a.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("hello\n")
        res = EditFileTool().run(path=path, old_str="zzzzzzzzzzzzzzzz qqqqqqqq", new_str="x")
        assert res.startswith("Error") and "read_file" in res


# --- uçtan uca: sahte Ollama ile ajan döngüsü ---------------------------------

def _make_agent(tmpdir, model="qwen3:0.6b"):
    from lokal_ajan.agent.loop import AgentLoop
    from lokal_ajan.config import Config

    cfg = Config()
    return AgentLoop(
        model_name=model,
        profile=get_profile_for_model(model),
        host=cfg.ollama_host,
        workdir=tmpdir,
        config=cfg,
        auto_confirm=True,
        session_name="",
    )


def test_loop_alias_tool_call_executes_and_options_forwarded(monkeypatch):
    import lokal_ajan.agent.loop as loop_mod

    seen_options = []
    replies = iter([
        # alias ad + alias parametreler -> write_file(path, content) olmalı
        ['<tool_call>\n{"name": "create_file", "arguments": {"file_path": "hello.txt", "text": "hi"}}\n</tool_call>'],
        ["hello.txt oluşturuldu."],
    ])

    def fake_stream(messages, model, host, options, think=None, timeout=None, **kw):
        seen_options.append(dict(options))
        yield from next(replies)

    monkeypatch.setattr(loop_mod, "ollama_chat_stream", fake_stream)
    with tempfile.TemporaryDirectory() as tmpdir:
        agent = _make_agent(tmpdir)
        agent.run_step("hello.txt dosyasını oluştur")
        with open(os.path.join(tmpdir, "hello.txt"), encoding="utf-8") as f:
            assert f.read() == "hi"
    assert seen_options[0]["num_predict"] >= 3072
    assert seen_options[0]["top_k"] == 20


def test_loop_validation_error_gives_usage_hint(monkeypatch):
    import lokal_ajan.agent.loop as loop_mod

    replies = iter([
        ['<tool_call>{"name": "edit_file", "arguments": {"path": "a.txt"}}</tool_call>'],
        ["tamam"],
    ])
    monkeypatch.setattr(loop_mod, "ollama_chat_stream",
                        lambda *a, **k: iter(next(replies)))
    with tempfile.TemporaryDirectory() as tmpdir:
        agent = _make_agent(tmpdir)
        agent.run_step("a.txt düzenle")
        tool_msgs = [m["content"] for m in agent.history.get_messages() if "<tool_output>" in m["content"]]
        assert tool_msgs and "missing required argument" in tool_msgs[0]
        assert "Correct usage" in tool_msgs[0]


def test_loop_constrained_recovery_of_broken_call(monkeypatch):
    import lokal_ajan.agent.loop as loop_mod
    import lokal_ajan.llm.ollama_client as oc

    replies = iter([
        ['<tool_call>\n{"name": "write_file", "arguments": {path: oops\n</tool_call>'],  # geçersiz
        ["bitti"],
    ])
    monkeypatch.setattr(loop_mod, "ollama_chat_stream", lambda *a, **k: iter(next(replies)))
    captured = {}

    def fake_chat_once(messages, model, host, options=None, think=None, timeout=None, format=None):
        captured["format"] = format
        return json.dumps({"name": "write_file", "arguments": {"path": "r.txt", "content": "ok"}})

    monkeypatch.setattr(oc, "chat_once", fake_chat_once)
    with tempfile.TemporaryDirectory() as tmpdir:
        agent = _make_agent(tmpdir)
        agent.run_step("r.txt yaz")
        assert os.path.exists(os.path.join(tmpdir, "r.txt"))
        # history'deki bozuk metin kanonik çağrıyla değiştirilmiş olmalı
        asst = [m["content"] for m in agent.history.get_messages() if m["role"] == "assistant"][0]
        assert asst.startswith("<tool_call>") and "oops" not in asst
    assert captured["format"]["properties"]["name"]["enum"]


def test_loop_tiny_profile_adds_office_tools_on_keyword(monkeypatch):
    import lokal_ajan.agent.loop as loop_mod

    monkeypatch.setattr(loop_mod, "ollama_chat_stream", lambda *a, **k: iter(["tamam"]))
    with tempfile.TemporaryDirectory() as tmpdir:
        agent = _make_agent(tmpdir)
        assert "- read_excel(" not in agent.history.get_messages()[0]["content"]
        agent.run_step("rapor.xlsx excel dosyasını oku")
        assert "- read_excel(" in agent.history.get_messages()[0]["content"]


def test_loop_non_tiny_model_unchanged_prompt(monkeypatch):
    import lokal_ajan.agent.loop as loop_mod

    monkeypatch.setattr(loop_mod, "ollama_chat_stream", lambda *a, **k: iter(["tamam"]))
    with tempfile.TemporaryDirectory() as tmpdir:
        agent = _make_agent(tmpdir, model="qwen3:8b")
        sys_before = agent.history.get_messages()[0]["content"]
        assert "CRITICAL RULES:" in sys_before
        agent.run_step("excel oku")
        assert agent.history.get_messages()[0]["content"] == sys_before
