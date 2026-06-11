from scripts.run_tryon_agent_workflow import (
    build_retry_plan,
    choose_retry_preset,
    merge_retry_records,
)


def test_choose_retry_preset_for_alignment_review() -> None:
    record = {
        "reasons": [],
        "warnings": ["scene_drift_review"],
    }

    assert choose_retry_preset(record) == "alignment"


def test_choose_retry_preset_for_style_missing() -> None:
    record = {
        "reasons": ["nail_region_change_too_low"],
        "warnings": [],
    }

    assert choose_retry_preset(record) == "style"


def test_choose_retry_preset_for_detail_enhancement() -> None:
    record = {
        "reasons": [],
        "warnings": ["nail_region_change_review"],
    }

    assert choose_retry_preset(record) == "detail"


def test_build_retry_plan_skips_pass_records() -> None:
    records = [
        {
            "pair": "hand_01_style_01",
            "decision": "pass",
            "score": 95,
            "reasons": [],
            "warnings": [],
        },
        {
            "pair": "hand_02_style_02",
            "decision": "review",
            "score": 72,
            "reasons": [],
            "warnings": ["scene_drift_review"],
        },
    ]

    plan = build_retry_plan(records)

    assert len(plan) == 1
    assert plan[0]["pair"] == "hand_02_style_02"
    assert plan[0]["retryPreset"] == "alignment"


def test_merge_retry_records_keeps_better_retry_candidate() -> None:
    base_records = [
        {
            "pair": "hand_01_style_01",
            "decision": "review",
            "score": 70,
            "attempt": 0,
        }
    ]
    retry_records = [
        {
            "pair": "hand_01_style_01",
            "decision": "pass",
            "score": 88,
            "attempt": 1,
        }
    ]

    merged = merge_retry_records(base_records, retry_records)

    assert merged[0]["decision"] == "pass"
    assert merged[0]["attempt"] == 1
    assert merged[0]["retryHistory"][0]["score"] == 70
