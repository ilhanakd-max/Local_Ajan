import sys
import os
sys.path.insert(0, "src")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lokal_ajan.llm.model_profiles import get_profile_for_model
from lokal_ajan.config import load_config


def test_groq_model_profiles():
    for name in [
        "groq/openai/gpt-oss-120b",
        "groq/openai/gpt-oss-20b",
        "groq/qwen/qwen3.8-27b",
    ]:
        p = get_profile_for_model(name)
        assert p.num_ctx == 32768, f"Expected 32768, got {p.num_ctx} for {name}"
        assert p.native_tool_call is True
        assert p.prompt_level == "standard"
        assert p.max_tool_output == 30000


def test_groq_config():
    cfg = load_config()
    assert hasattr(cfg, "groq_api_key")
    assert cfg.groq_api_key.startswith("gsk_")


def test_launcher_external_models():
    from launcher.launcher import get_ollama_models
    models = get_ollama_models()
    expected = [
        "groq/openai/gpt-oss-120b",
        "groq/openai/gpt-oss-20b",
        "groq/qwen/qwen3.8-27b",
        "openrouter/free",
    ]
    for m in expected:
        assert m in models, f"Expected {m} to be in launcher models"


if __name__ == "__main__":
    tests = [
        test_groq_model_profiles,
        test_groq_config,
        test_launcher_external_models,
    ]
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
        except Exception as e:
            print(f"  ✗ {t.__name__}: {e}")
            raise
    print("Tüm Groq model testleri başarıyla geçti.")
