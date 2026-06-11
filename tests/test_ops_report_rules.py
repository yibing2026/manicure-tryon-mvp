from scripts.build_ops_daily_report import build_quality_by_style, top_counts


def test_build_quality_by_style_normalizes_numeric_style_id() -> None:
    report = {
        "records": [
            {
                "styleId": 3,
                "decision": "review",
                "score": 77,
                "warnings": ["nail_region_change_review"],
                "reasons": [],
            }
        ]
    }

    quality = build_quality_by_style(report)

    assert quality["style_03"]["decision"] == "review"
    assert quality["style_03"]["score"] == 77


def test_top_counts_ignores_empty_values() -> None:
    items = [
        {"style_category": "luxury"},
        {"style_category": "daily"},
        {"style_category": "luxury"},
        {"style_category": ""},
    ]

    assert top_counts(items, "style_category", limit=2) == [
        {"name": "luxury", "count": 2},
        {"name": "daily", "count": 1},
    ]
