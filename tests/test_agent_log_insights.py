from scripts.analyze_agent_logs import classify_error, summarize


def test_classify_model_permission_error() -> None:
    message = "Your account has not activated the model service in Ark Console."

    assert classify_error(message) == "model_permission"


def test_classify_rate_limit_error() -> None:
    message = "Request failed with 429 rate limit exceeded."

    assert classify_error(message) == "rate_limit"


def test_summarize_logs_generates_model_config_suggestion() -> None:
    records = [
        {
            "status": "error",
            "provider": "doubao",
            "requestedModel": "doubao-seedream",
            "durationMs": 1200,
            "retry": {"preset": "alignment"},
            "error": {"message": "The model endpoint does not exist."},
        },
        {
            "status": "success",
            "provider": "mock",
            "requestedModel": "mock-tryon-v1",
            "durationMs": 20,
            "retry": {"preset": "alignment"},
        },
    ]

    summary = summarize(records)
    areas = {
        suggestion["area"]
        for suggestion in summary["agent_iteration_suggestions"]
    }

    assert summary["success_rate"] == 0.5
    assert summary["error_types"]["model_or_endpoint"] == 1
    assert "provider_fallback" in areas
    assert "model_config" in areas
