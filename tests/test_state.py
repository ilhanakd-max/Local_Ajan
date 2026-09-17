import os
import sys
import json
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, "src")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lokal_ajan.config import load_state, save_state


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
        save_state({"workdir": "/tmp", "model": "openrouter/free"}, self.state_file)
        state = load_state(self.state_file)
        self.assertEqual(state.get("workdir"), "/tmp")
        self.assertEqual(state.get("model"), "openrouter/free")

    def test_update_existing_state(self):
        save_state({"workdir": "/tmp"}, self.state_file)
        save_state({"model": "openrouter/free"}, self.state_file)
        state = load_state(self.state_file)
        self.assertEqual(state.get("workdir"), "/tmp")
        self.assertEqual(state.get("model"), "openrouter/free")


if __name__ == "__main__":
    unittest.main()
