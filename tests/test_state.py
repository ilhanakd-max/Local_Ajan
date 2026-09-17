import os
import sys
import json
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, "src")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lokal_ajan.config import load_state, save_state
from launcher.launcher import load_launcher_state, save_launcher_state


class TestStatePersistence(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.state_file = Path(self.tmp_dir.name) / "test_state.json"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_load_state_non_existent(self):
        state = load_state(self.state_file)
        self.assertEqual(state, {})

    def test_save_and_load_state(self):
        save_state({"workdir": "/tmp", "model": "groq/openai/gpt-oss-120b"}, self.state_file)
        state = load_state(self.state_file)
        self.assertEqual(state.get("workdir"), "/tmp")
        self.assertEqual(state.get("model"), "groq/openai/gpt-oss-120b")

    def test_update_existing_state(self):
        save_state({"workdir": "/tmp"}, self.state_file)
        save_state({"model": "groq/qwen/qwen3.8-27b"}, self.state_file)
        state = load_state(self.state_file)
        self.assertEqual(state.get("workdir"), "/tmp")
        self.assertEqual(state.get("model"), "groq/qwen/qwen3.8-27b")

    def test_launcher_state_functions(self):
        save_launcher_state({"workdir": "/home/user/project", "orchestrator": True}, self.state_file)
        state = load_launcher_state(self.state_file)
        self.assertEqual(state.get("workdir"), "/home/user/project")
        self.assertTrue(state.get("orchestrator"))


if __name__ == "__main__":
    unittest.main()
