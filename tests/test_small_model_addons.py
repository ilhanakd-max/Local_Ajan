import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "src")

from lokal_ajan.agent.prompt import get_system_prompt
from lokal_ajan.safety.guards import (
    RepetitionLoopGuard,
    clear_deleted_paths,
    detect_text_repetition,
    is_mutating_call,
)
from lokal_ajan.tools.claim_tools import (
    ReportFindingTool,
    format_claim_memory_for_prompt,
)
from lokal_ajan.tools.fs_tools import ReadFileTool, WriteFileTool
from lokal_ajan.tools.semantic_search_tool import SemanticCodeSearchTool
from lokal_ajan.tools.shell_tool import RunShellTool


def test_read_dir_redirect():
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "alpha.py").write_text("x = 1\n", encoding="utf-8")
        Path(tmpdir, "sub").mkdir()

        r_tool = ReadFileTool(workdir=tmpdir)
        res = r_tool.run(path=".")
        assert "is a directory" in res
        assert "list_dir" in res
        assert "alpha.py" in res
        assert "sub/" in res


def test_write_vs_edit_guard_blocks_existing_and_rm_bypass():
    clear_deleted_paths()
    with tempfile.TemporaryDirectory() as tmpdir:
        w_tool = WriteFileTool(workdir=tmpdir)
        shell = RunShellTool(workdir=tmpdir)

        # New file succeeds
        res1 = w_tool.run(path="app.py", content="print('v1')\n")
        assert "Successfully" in res1

        # Existing file is blocked
        res2 = w_tool.run(path="app.py", content="print('v2')\n")
        assert "write_file blocked" in res2
        assert "edit_file" in res2

        # Protected directory is blocked
        res_git = w_tool.run(path=".git/config", content="bad")
        assert "protected directory" in res_git

        # rm && write bypass is blocked
        shell.run(command="rm app.py")
        res3 = w_tool.run(path="app.py", content="print('v3')\n")
        assert "write_file blocked" in res3
        assert "deleted or moved" in res3


def test_repetition_loop_guard_and_cycles():
    guard = RepetitionLoopGuard(threshold=3, stop_after=3)

    # Identical read_file 3 times -> 3rd blocks
    for _ in range(2):
        blocked, abort, _ = guard.check("read_file", {"path": "a.py"})
        assert not blocked and not abort
        guard.record("read_file", {"path": "a.py"}, is_error=False)

    blocked, abort, reason = guard.check("read_file", {"path": "a.py"})
    assert blocked and not abort
    assert "tekrarlandı" in reason

    # Mutating call clears window & block count
    guard.record("edit_file", {"path": "a.py", "old_str": "1", "new_str": "2"}, is_error=False)
    blocked, abort, _ = guard.check("read_file", {"path": "a.py"})
    assert not blocked and not abort

    # Cycle A -> B -> A -> B
    guard.record("read_file", {"path": "a.py"})
    guard.record("list_dir", {"path": "."})
    guard.record("read_file", {"path": "a.py"})
    blocked, _, reason = guard.check("list_dir", {"path": "."})
    assert blocked
    assert "döngüsü" in reason


def test_is_mutating_call_and_text_repetition():
    assert is_mutating_call("edit_file", {"path": "x.py"})
    assert is_mutating_call("run_shell", {"command": "sed -i 's/a/b/' x.py"})
    assert not is_mutating_call("run_shell", {"command": "echo 'a > b' 2>/dev/null"})
    assert not is_mutating_call("read_file", {"path": "x.py"})

    repeated_line = "This is a degenerate repeated line from a small model."
    assert detect_text_repetition("\n".join([repeated_line] * 4))
    assert not detect_text_repetition("Normal short response.")


def test_report_finding_and_claim_memory(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        mem_file = Path(tmpdir) / "claim_memory.json"
        monkeypatch.setenv("LOCAI_CLAIM_MEMORY", str(mem_file))

        src = Path(tmpdir) / "calc.py"
        src.write_text("def div(a, b):\n    if b == 0:\n        return 0\n    return a / b\n", encoding="utf-8")

        tool = ReportFindingTool(workdir=tmpdir)

        # Wrong quote rejected
        bad_quote = tool.run(
            title="Zero division",
            file_path="calc.py",
            line_start=1,
            quoted_source="return a // b",
            failure_scenario="Calling div(1, 0) crashes with ZeroDivisionError.",
            refutation_attempt="Checked div implementation in calc.py.",
            confidence="confirmed",
            severity="high",
        )
        assert "Error: quoted_source" in bad_quote

        # Unverified with severity rejected
        bad_sev = tool.run(
            title="Zero division",
            file_path="calc.py",
            line_start=1,
            quoted_source="return a / b",
            failure_scenario="Calling div(1, 0) might crash.",
            refutation_attempt="Checked div implementation in calc.py.",
            confidence="unverified",
            severity="high",
        )
        assert "Error: unverified" in bad_sev

        # Refuted finding persists to claim memory
        disproved = tool.run(
            title="Zero division",
            file_path="calc.py",
            line_start=1,
            quoted_source="if b == 0:\n        return 0",
            failure_scenario="Calling div(1, 0) crashes with ZeroDivisionError.",
            refutation_attempt="Checked lines 2-3 of calc.py for zero guard.",
            refuted_by="Lines 2-3 explicitly guard b == 0 and return 0.",
            confidence="likely",
            severity="none",
        )
        assert "DISPROVED" in disproved
        assert "Zero division" in format_claim_memory_for_prompt()


def test_semantic_code_search():
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "auth.py").write_text(
            "def verify_jwt_token(token: str) -> bool:\n    return token.startswith('jwt_')\n",
            encoding="utf-8",
        )
        Path(tmpdir, "math_utils.py").write_text(
            "def add_numbers(a: int, b: int) -> int:\n    return a + b\n",
            encoding="utf-8",
        )

        search = SemanticCodeSearchTool(workdir=tmpdir)
        res = search.run(query="validate authentication jwt token", path=".")
        assert "auth.py" in res


def test_prompt_includes_small_model_disciplines():
    prompt_full = get_system_prompt("full", [], workdir=".")
    assert "Workspace discovery" in prompt_full
    assert "Claim verification" in prompt_full
    assert "write_file is blocked on existing files" in prompt_full

    prompt_min = get_system_prompt("minimal", [], workdir=".")
    assert "write_file is blocked on existing files" in prompt_min
