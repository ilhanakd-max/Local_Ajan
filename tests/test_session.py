import tempfile
import unittest
from pathlib import Path
from lokal_ajan.agent.session import (
    save_session,
    load_session,
    list_sessions,
    delete_session,
)


class TestSession(unittest.TestCase):
    def setUp(self):
        import os
        import lokal_ajan.agent.session as session_module
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.workdir = self.tmp_dir.name
        self.sessions_path = Path(self.tmp_dir.name) / "sessions"
        session_module.SESSIONS_DIR = self.sessions_path

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_save_and_load_session(self):
        messages = [
            {"role": "system", "content": "system prompt here"},
            {"role": "user", "content": "hello agent"},
            {"role": "assistant", "content": "hello user"},
        ]
        save_session(self.workdir, messages, "qwen3:1.7b", "test_session")
        
        loaded = load_session(self.workdir, "test_session")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["session_name"], "test_session")
        self.assertEqual(loaded["model_name"], "qwen3:1.7b")
        
        # System prompt should be filtered out to allow cross-model resumption
        self.assertEqual(len(loaded["messages"]), 2)
        self.assertEqual(loaded["messages"][0]["role"], "user")
        self.assertEqual(loaded["messages"][1]["role"], "assistant")

    def test_list_and_delete_session(self):
        save_session(self.workdir, [{"role": "user", "content": "hi"}], "model1", "s1")
        save_session(self.workdir, [{"role": "user", "content": "hi2"}], "model2", "s2")
        
        sessions = list_sessions(self.workdir)
        names = [s["name"] for s in sessions]
        self.assertIn("s1", names)
        self.assertIn("s2", names)
        
        # Delete s1
        res = delete_session(self.workdir, "s1")
        self.assertTrue(res)
        
        sessions_after = list_sessions(self.workdir)
        names_after = [s["name"] for s in sessions_after]
        self.assertNotIn("s1", names_after)
        self.assertIn("s2", names_after)


if __name__ == "__main__":
    unittest.main()
