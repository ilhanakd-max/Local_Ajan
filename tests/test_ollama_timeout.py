import sys
import os
import unittest
from unittest.mock import patch, MagicMock
import httpx

sys.path.insert(0, "src")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lokal_ajan.llm.model_profiles import get_profile_for_model
from lokal_ajan.config import Config, load_config
from lokal_ajan.llm.ollama_client import (
    chat_stream,
    preload_model,
    OllamaConnectionError,
)


class TestOllamaTimeoutAndProfiles(unittest.TestCase):
    def test_lfm_model_profile(self):
        # LFM 8B modelinin profili
        model_name = "hf.co/mradermacher/LFM2.5-8B-A1B-Coder-i1-GGUF:Q4_K_M"
        profile = get_profile_for_model(model_name)
        self.assertEqual(profile.num_ctx, 8192)
        self.assertTrue(profile.native_tool_call)

    def test_config_ollama_timeout(self):
        cfg = Config()
        self.assertIsNone(cfg.ollama_timeout)
        custom_cfg = Config(ollama_timeout=300.0)
        self.assertEqual(custom_cfg.ollama_timeout, 300.0)

    @patch("lokal_ajan.llm.ollama_client.httpx.stream")
    def test_chat_stream_timeout_raises_ollama_connection_error(self, mock_stream):
        # httpx.TimeoutException fırlatıldığında OllamaConnectionError'a sarmalanmalı
        mock_stream.side_effect = httpx.ReadTimeout("timed out")

        with self.assertRaises(OllamaConnectionError) as ctx:
            list(chat_stream(
                messages=[{"role": "user", "content": "hello"}],
                model="hf.co/mradermacher/LFM2.5-8B-A1B-Coder-i1-GGUF:Q4_K_M"
            ))
        
        err_msg = str(ctx.exception)
        self.assertIn("zaman aşımı", err_msg)
        self.assertIn("timed out", err_msg)

    @patch("lokal_ajan.llm.ollama_client.httpx.post")
    def test_preload_model(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        success = preload_model("test-model:latest", host="http://localhost:11434")
        self.assertTrue(success)
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        self.assertEqual(call_kwargs["json"]["model"], "test-model:latest")
        self.assertEqual(call_kwargs["json"]["prompt"], "")


    @patch("lokal_ajan.llm.ollama_client.httpx.post")
    def test_get_ollama_model_info_and_dynamic_profile(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "parameters": "num_ctx 16384\nstop <|im_end|>",
            "model_info": {"lfm2moe.context_length": 128000}
        }
        mock_post.return_value = mock_resp

        from lokal_ajan.llm.ollama_client import get_ollama_model_info
        info = get_ollama_model_info("test-model", host="http://localhost:11434")
        self.assertEqual(info.get("num_ctx"), 16384)
        self.assertEqual(info.get("context_length"), 128000)

        # Dynamic profile should inherit 16384
        prof = get_profile_for_model("hf.co/mradermacher/LFM2.5-8B-A1B-Coder-i1-GGUF:Q4_K_M", ollama_host="http://localhost:11434")
        self.assertEqual(prof.num_ctx, 16384)


if __name__ == "__main__":
    unittest.main()
