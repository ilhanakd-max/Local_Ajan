import pytest
import json
import httpx
from unittest.mock import patch, MagicMock
from lokal_ajan.llm.openrouter_client import (
    chat_stream,
    OpenRouterConnectionError,
    FREE_FALLBACK_MODELS,
)


def _make_mock_stream_response(lines, status_code=200):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.iter_lines.return_value = iter(lines)
    mock_resp.raise_for_status.return_value = None
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False
    return mock_resp


def test_openrouter_free_payload_uses_fallback_models():
    captured_payload = None

    def fake_stream(method, url, headers=None, json=None, timeout=None):
        nonlocal captured_payload
        captured_payload = json
        lines = [
            'data: {"choices": [{"delta": {"content": "ok"}}]}',
            'data: [DONE]',
        ]
        return _make_mock_stream_response(lines)

    with patch("httpx.stream", side_effect=fake_stream):
        chunks = list(chat_stream(
            messages=[{"role": "user", "content": "hi"}],
            model="openrouter/free",
            api_key="fake-key",
            options={"num_ctx": 8192, "temperature": 0.2},
        ))

    assert chunks == ["ok"]
    assert captured_payload is not None
    assert captured_payload.get("models") == FREE_FALLBACK_MODELS
    assert "model" not in captured_payload
    assert captured_payload.get("max_tokens") == 4096


def test_openrouter_specific_model_strips_prefix():
    captured_payload = None

    def fake_stream(method, url, headers=None, json=None, timeout=None):
        nonlocal captured_payload
        captured_payload = json
        lines = [
            'data: {"choices": [{"delta": {"content": "hello"}}]}',
            'data: [DONE]',
        ]
        return _make_mock_stream_response(lines)

    with patch("httpx.stream", side_effect=fake_stream):
        chunks = list(chat_stream(
            messages=[{"role": "user", "content": "hi"}],
            model="openrouter/nvidia/nemotron-3-super-120b-a12b:free",
            api_key="fake-key",
        ))

    assert chunks == ["hello"]
    assert captured_payload is not None
    assert captured_payload.get("model") == "nvidia/nemotron-3-super-120b-a12b:free"
    assert "models" not in captured_payload


def test_openrouter_sse_error_payload_raises():
    lines = [
        'data: {"choices": [{"delta": {"content": "ok"}}]}',
        'data: {"error": {"message": "Provider returned error", "code": 429}}',
    ]

    with patch("httpx.stream", return_value=_make_mock_stream_response(lines)):
        chunks = list(chat_stream(
            messages=[{"role": "user", "content": "hi"}],
            model="openrouter/free",
            api_key="fake-key",
        ))
    assert chunks == ["ok"]


def test_openrouter_finish_reason_error_raises():
    lines = [
        'data: {"choices": [{"delta": {"content": "ok"}}]}',
        'data: {"choices": [{"delta": {}, "finish_reason": "error"}]}',
    ]

    with patch("httpx.stream", return_value=_make_mock_stream_response(lines)):
        chunks = list(chat_stream(
            messages=[{"role": "user", "content": "hi"}],
            model="openrouter/free",
            api_key="fake-key",
        ))
    assert chunks == ["ok"]


def test_openrouter_reasoning_stream_wrapped_in_think():
    lines = [
        'data: {"choices": [{"delta": {"reasoning": "analyzing..."}}]}',
        'data: {"choices": [{"delta": {"content": "done!"}}]}',
        'data: [DONE]',
    ]

    with patch("httpx.stream", return_value=_make_mock_stream_response(lines)):
        chunks = list(chat_stream(
            messages=[{"role": "user", "content": "hi"}],
            model="openrouter/free",
            api_key="fake-key",
        ))

    assert chunks == ["<think>", "analyzing...", "</think>", "done!"]


def test_parser_handles_arg_key_value_format():
    """Test that the parser correctly handles the <tool_call>name<arg_key>k</arg_key><arg_value>v</arg_value></tool_call> format."""
    from lokal_ajan.agent.parser import extract_tool_call, extract_all_tool_calls

    text = '<tool_call>list_dir<arg_key>path</arg_key><arg_value>/home/ilhan/Masaüstü/TEST/test4</arg_value></tool_call>'
    result = extract_tool_call(text)
    assert result is not None
    assert result[0] == "list_dir"
    assert result[1] == {"path": "/home/ilhan/Masaüstü/TEST/test4"}

    # Also test extract_all_tool_calls
    results = extract_all_tool_calls(text)
    assert len(results) == 1
    assert results[0][0] == "list_dir"
    assert results[0][1] == {"path": "/home/ilhan/Masaüstü/TEST/test4"}

    # Test with surrounding text
    text_with_context = 'I will inspect the directory.\n\n<tool_call>list_dir<arg_key>path</arg_key><arg_value>/some/path</arg_value></tool_call>'
    result2 = extract_tool_call(text_with_context)
    assert result2 is not None
    assert result2[0] == "list_dir"

    # Test multi-arg format
    text_multi = '<tool_call>write_file<arg_key>path</arg_key><arg_value>index.html</arg_value><arg_key>content</arg_key><arg_value><html>Hello</html></arg_value></tool_call>'
    result3 = extract_tool_call(text_multi)
    assert result3 is not None
    assert result3[0] == "write_file"
    assert result3[1]["path"] == "index.html"
    assert "<html>" in result3[1]["content"]
