import sys
import os
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, "src")

from lokal_ajan.tools.registry import registry
from lokal_ajan.tools.fs_tools import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool, GlobTool, GrepTool
from lokal_ajan.tools.git_tools import GitStatusTool, GitDiffTool
from lokal_ajan.tools.shell_tool import RunShellTool
from lokal_ajan.safety.confirm import request_confirmation
from lokal_ajan.llm.model_profiles import get_profile_for_model
from lokal_ajan.agent.loop import AgentLoop
from lokal_ajan.config import Config


def test_fs_tools_crud():
    with tempfile.TemporaryDirectory() as tmpdir:
        w_tool = WriteFileTool()
        r_tool = ReadFileTool()
        e_tool = EditFileTool()
        l_tool = ListDirTool()

        test_file = os.path.join(tmpdir, "test.txt")
        
        # Write
        res = w_tool.run(path=test_file, content="line 1\nline 2\nline 3\n")
        assert "Successfully" in res
        
        # Read full
        content = r_tool.run(path=test_file)
        assert "line 1" in content and "line 3" in content
        
        # Read slices
        slice_content = r_tool.run(path=test_file, start_line=2, end_line=2)
        assert slice_content.strip() == "line 2"

        # Edit
        edit_res = e_tool.run(path=test_file, old_str="line 2", new_str="line TWO")
        assert "Successfully" in edit_res
        assert "line TWO" in r_tool.run(path=test_file)

        # List dir
        list_res = l_tool.run(path=tmpdir)
        assert "test.txt" in list_res


def test_glob_tool():
    with tempfile.TemporaryDirectory() as tmpdir:
        g_tool = GlobTool()
        
        # Create dummy structure
        f1 = Path(tmpdir, "main.py")
        f2 = Path(tmpdir, "util.py")
        f3 = Path(tmpdir, "index.html")
        f1.write_text("print('hi')")
        f2.write_text("def fn(): pass")
        f3.write_text("<h1>Hi</h1>")

        # Test *.py glob
        res = g_tool.run(pattern="*.py", path=tmpdir)
        assert "main.py" in res
        assert "util.py" in res
        assert "index.html" not in res

        # Test non-matching pattern
        no_match = g_tool.run(pattern="*.cpp", path=tmpdir)
        assert "No files matched" in no_match


def test_grep_tool():
    with tempfile.TemporaryDirectory() as tmpdir:
        grep_tool = GrepTool()
        
        f1 = Path(tmpdir, "app.py")
        f2 = Path(tmpdir, "test.txt")
        f1.write_text("def find_me_function():\n    return 42\n")
        f2.write_text("Some random text\n")

        res = grep_tool.run(pattern="find_me_function", path=tmpdir)
        assert "find_me_function" in res
        assert "app.py" in res


def test_git_tools():
    git_status = GitStatusTool()
    git_diff = GitDiffTool()
    
    # We test in the current repo which is a git repo
    status_out = git_status.run(path=".")
    assert isinstance(status_out, str)
    
    diff_out = git_diff.run(path=".")
    assert isinstance(diff_out, str)


def test_run_shell_tool():
    with tempfile.TemporaryDirectory() as tmpdir:
        shell = RunShellTool(workdir=tmpdir)
        res = shell.run(command="echo 'LOKAL_AJAN_SHELL_TEST'")
        assert "LOKAL_AJAN_SHELL_TEST" in res


def test_auto_confirm():
    assert request_confirmation("write_file", {"path": "test.txt"}, auto_confirm=True) is True


def test_agent_loop_update_model():
    cfg = Config()
    prof_7b = get_profile_for_model("qwen2.5-coder:7b")
    agent = AgentLoop(model_name="qwen2.5-coder:7b", profile=prof_7b, host=cfg.ollama_host, workdir=".", config=cfg)
    
    # Check initial system prompt
    assert len(agent.history.get_messages()) >= 1
    initial_sys = agent.history.get_messages()[0]["content"]
    assert "CRITICAL RULES:" in initial_sys
    
    # Switch to 0.6B minimal model
    prof_06b = get_profile_for_model("qwen3:0.6b")
    agent.update_model("qwen3:0.6b", prof_06b)
    
    assert agent.model_name == "qwen3:0.6b"
    assert agent.profile.prompt_level == "minimal"
    updated_sys = agent.history.get_messages()[0]["content"]
    assert "You act, you don't just talk." in updated_sys


def test_edit_file_smart_whitespace_tolerance():
    with tempfile.TemporaryDirectory() as tmpdir:
        e_tool = EditFileTool()
        r_tool = ReadFileTool()
        test_file = os.path.join(tmpdir, "code.py")

        initial_content = "def test():\n    x = 10  \n    y = 20\n    return x + y\n"
        with open(test_file, "w") as f:
            f.write(initial_content)

        # Edit with slight trailing whitespace difference and multiline
        old_block = "    x = 10\n    y = 20"
        new_block = "    x = 100\n    y = 200"
        res = e_tool.run(path=test_file, old_str=old_block, new_str=new_block)
        assert "Successfully" in res
        updated = r_tool.run(path=test_file)
        assert "x = 100" in updated
        assert "y = 200" in updated


if __name__ == "__main__":
    tests = [
        test_fs_tools_crud,
        test_glob_tool,
        test_grep_tool,
        test_git_tools,
        test_run_shell_tool,
        test_auto_confirm,
        test_agent_loop_update_model,
        test_edit_file_smart_whitespace_tolerance,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {t.__name__}: {type(e).__name__}: {e}")
    print(f"\nSonuç: {passed}/{len(tests)} test başarıyla geçti.")

