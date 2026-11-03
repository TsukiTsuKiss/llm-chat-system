from studio.errors import detect_api_error, handle_api_error


def test_tool_call_error_is_detected_and_retried():
    message = "APIError: Tool choice is none, but model called a tool"
    code = detect_api_error(message)
    assert code == "tool_call"
    assert handle_api_error(code, attempt=0, max_retries=3, retry_delay=0) is True
    assert handle_api_error(code, attempt=2, max_retries=3, retry_delay=0) is False


def test_existing_error_codes_are_unchanged():
    assert detect_api_error("Error code: 429 - rate limit") == "429"
    assert detect_api_error("Connection timeout") == "504"
    assert detect_api_error("something else") is None
