from panfetch_ai.logging_setup import redact


def test_log_redaction_removes_tokens_and_api_keys() -> None:
    value = "url?access_token=secret123&x=1 Authorization: Bearer abc.xyz x-api-key=hello"
    redacted = redact(value)
    assert "secret123" not in redacted
    assert "abc.xyz" not in redacted
    assert "hello" not in redacted
    assert redacted.count("<redacted>") == 3
