from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Dict, List


STYLE_LABEL_PATH = Path("data/official_style_label_draft_v1.csv")
POPULARITY_PATH = Path("data/mock_style_popularity.json")
QUALITY_PATH = Path("analysis/tryon_quality_v1/tryon_quality_report.json")
WORKFLOW_PATH = Path("analysis/tryon_agent_workflow_v1/tryon_agent_workflow.json")
OUTPUT_DIR = Path("analysis/ops_daily_report_v1")


def normalize_style_key(value: str | int | None) -> str:
    if value is None:
        return ""
    try:
        return f"style_{int(value):02d}"
    except ValueError:
        return str(value)


def load_style_labels() -> Dict[str, Dict[str, str]]:
    with STYLE_LABEL_PATH.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        return {
            normalize_style_key(row.get("style_id")): row
            for row in reader
            if row.get("style_id")
        }


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def enrich_style(style_id: str, labels: Dict[str, Dict[str, str]], popularity: Dict[str, Any], quality: Dict[str, Any]) -> Dict[str, Any]:
    label = labels.get(style_id, {})
    return {
        "style_id": style_id,
        "style_category": label.get("style_category", ""),
        "primary_color": label.get("primary_color", ""),
        "occasion": label.get("occasion", ""),
        "target_persona": label.get("target_persona", ""),
        "price_band": label.get("price_band", ""),
        "trend_keywords": label.get("trend_keywords", ""),
        "hotness_score": popularity.get("hotness_score", 0),
        "recent_growth": popularity.get("recent_growth", 0),
        "views": popularity.get("views", 0),
        "tryons": popularity.get("tryons", 0),
        "favorites": popularity.get("favorites", 0),
        "bookings": popularity.get("bookings", 0),
        "quality_decision": quality.get("decision", "unknown"),
        "quality_score": quality.get("score"),
    }


def build_quality_by_style(report: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    quality = {}
    for record in report.get("records", []):
        style_id = normalize_style_key(record.get("styleId"))
        if style_id:
            quality[style_id] = {
                "decision": record.get("decision", "unknown"),
                "score": record.get("score"),
                "warnings": record.get("warnings", []),
                "reasons": record.get("reasons", []),
            }
    return quality


def top_counts(items: List[Dict[str, Any]], key: str, limit: int = 5) -> List[Dict[str, Any]]:
    counts = Counter(item.get(key, "") for item in items if item.get(key))
    return [{"name": name, "count": count} for name, count in counts.most_common(limit)]


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# 美甲智能运营日报 v1",
        "",
        f"- 日期：{report['date']}",
        f"- 数据口径：{report['data_scope']}",
        "",
        "## 今日趋势洞察",
        "",
    ]

    for item in report["trend_insights"]["hot_styles"]:
        lines.append(
            f"- {item['style_id']}：热度 {item['hotness_score']}，场景 {item['occasion']}，风格 {item['style_category']}，质检 {item['quality_decision']}"
        )

    lines.extend(["", "## 增长预警", ""])
    for item in report["trend_insights"]["growth_styles"]:
        lines.append(
            f"- {item['style_id']}：增长 {item['recent_growth']}，关键词 {item['trend_keywords']}"
        )

    lines.extend(["", "## 推荐池与复查队列", ""])
    lines.append(f"- 可进入推荐池：{report['quality_gate']['ready_count']} 款")
    lines.append(f"- 需要复查：{report['quality_gate']['review_count']} 款")
    lines.append(f"- 暂不推荐：{report['quality_gate']['fail_count']} 款")

    lines.extend(["", "## 今日运营动作", ""])
    for action in report["operator_actions"]:
        lines.append(f"- {action}")

    lines.extend(["", "## 风险提示", ""])
    for risk in report["risk_notes"]:
        lines.append(f"- {risk}")

    lines.extend(["", "## 下一步执行", ""])
    for item in report["execution_plan"]:
        lines.append(f"- {item}")

    return "\n".join(lines) + "\n"


def main() -> int:
    labels = load_style_labels()
    popularity_payload = load_json(POPULARITY_PATH)
    quality_report = load_json(QUALITY_PATH)
    workflow = load_json(WORKFLOW_PATH)
    quality_by_style = build_quality_by_style(quality_report)

    popularity_by_id = {
        item["style_id"]: item for item in popularity_payload.get("styles", [])
    }
    enriched = [
        enrich_style(style_id, labels, popularity, quality_by_style.get(style_id, {}))
        for style_id, popularity in popularity_by_id.items()
    ]

    hot_styles = sorted(enriched, key=lambda item: item["hotness_score"], reverse=True)[:5]
    growth_styles = sorted(enriched, key=lambda item: item["recent_growth"], reverse=True)[:5]
    ready_styles = [item for item in enriched if item["quality_decision"] == "pass"]
    review_styles = [item for item in enriched if item["quality_decision"] == "review"]
    fail_styles = [item for item in enriched if item["quality_decision"] == "fail"]

    report = {
        "date": date.today().isoformat(),
        "report_version": "v1",
        "data_scope": "official style labels + mock popularity + try-on quality report + Agent Workflow",
        "data_sources": {
            "style_labels": str(STYLE_LABEL_PATH),
            "mock_popularity": str(POPULARITY_PATH),
            "quality_report": str(QUALITY_PATH),
            "agent_workflow": str(WORKFLOW_PATH),
        },
        "trend_insights": {
            "hot_styles": hot_styles,
            "growth_styles": growth_styles,
            "top_categories": top_counts(ready_styles, "style_category"),
            "top_occasions": top_counts(ready_styles, "occasion"),
            "top_personas": top_counts(ready_styles, "target_persona"),
        },
        "quality_gate": {
            "ready_count": len(ready_styles),
            "review_count": len(review_styles),
            "fail_count": len(fail_styles),
            "review_styles": review_styles,
            "fail_styles": fail_styles,
        },
        "operator_actions": [
            f"将 {', '.join(item['style_id'] for item in hot_styles[:3])} 放入今日高热推荐位。",
            "将质检为 review 的款式先进入复查队列，生成更高质量试戴图后再主推。",
            "围绕高频场景和风格制作首页推荐标题与专题入口。",
            "使用运营 Copilot 对 party / wedding / dating 等高价值场景分别生成活动文案。",
        ],
        "risk_notes": [
            "当前热度来自 mock 数据，仅用于 MVP 验证，不能等同真实用户行为。",
            "质检 v1 是规则评估，仍需要人工抽检关键样例。",
            "review 款式不建议直接进入首页主推，避免用户看到低质量试戴结果。",
        ],
        "execution_plan": [
            "今日先上线 pass 且热度靠前的款式进入推荐池。",
            "对 review 样例执行 Workflow 中建议的质量重试命令。",
            "收集真实曝光、点击、试戴、收藏、预约数据，用于替换 mock 热度。",
        ],
        "workflow_snapshot": {
            "quality_summary": workflow.get("qualitySummary", {}),
            "retry_plan": workflow.get("retryPlan", []),
        },
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "ops_daily_report.json"
    md_path = OUTPUT_DIR / "ops_daily_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
