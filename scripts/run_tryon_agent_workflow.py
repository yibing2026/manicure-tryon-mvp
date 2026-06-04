from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


QUALITY_REPORT_PATH = Path("analysis/tryon_quality_v1/tryon_quality_report.json")
STYLE_LABEL_PATH = Path("data/official_style_label_draft_v1.csv")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a safe Agent workflow over existing manicure try-on outputs."
    )
    parser.add_argument(
        "--manifest",
        default="",
        help="Optional batch results.json passed through to the quality evaluator.",
    )
    parser.add_argument(
        "--output-dir",
        default="analysis/tryon_agent_workflow_v1",
        help="Directory for workflow JSON and Markdown reports.",
    )
    parser.add_argument(
        "--skip-evaluate",
        action="store_true",
        help="Reuse the existing quality report instead of re-running evaluation.",
    )
    return parser.parse_args()


def run_quality_evaluation(manifest: str) -> None:
    command = [sys.executable, "scripts/evaluate_tryon_results.py"]
    if manifest:
        command.extend(["--manifest", manifest])
    subprocess.run(command, check=True)


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_style_id(pair_id: str) -> int | None:
    match = re.match(r"hand_\d+_style_(\d+)", pair_id or "")
    return int(match.group(1)) if match else None


def normalize_style_key(style_id: int | str | None) -> str:
    if style_id is None:
        return ""
    try:
        return f"style_{int(style_id):02d}"
    except ValueError:
        return str(style_id)


def load_style_labels(path: Path) -> Dict[str, Dict[str, str]]:
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        return {
            normalize_style_key(row.get("style_id")): row
            for row in reader
            if row.get("style_id")
        }


def choose_retry_preset(record: Dict[str, Any]) -> str:
    signals = set(record.get("reasons", [])) | set(record.get("warnings", []))
    if any("nail_region_change" in signal for signal in signals):
        return "style"
    if any("scene_drift" in signal or "aspect_ratio" in signal for signal in signals):
        return "alignment"
    if any("missing" in signal or "failed" in signal for signal in signals):
        return "mixed"
    return "mixed"


def build_retry_plan(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    plan = []
    for record in records:
        if record.get("decision") == "pass":
            continue

        pair = record["pair"]
        preset = choose_retry_preset(record)
        plan.append(
            {
                "pair": pair,
                "decision": record["decision"],
                "score": record["score"],
                "retryPreset": preset,
                "suggestedCommand": (
                    "python scripts/batch_generate_official_pairs.py "
                    f"--pairs {pair} --quality-retry-attempts 2 "
                    f"--retry-preset {preset} --overwrite"
                ),
                "signals": {
                    "reasons": record.get("reasons", []),
                    "warnings": record.get("warnings", []),
                },
            }
        )
    return plan


def build_ops_actions(records: List[Dict[str, Any]], style_labels: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    pass_records = [record for record in records if record.get("decision") == "pass"]
    review_records = [record for record in records if record.get("decision") != "pass"]
    ready_styles = []
    held_styles = []

    for record in pass_records:
        style_key = normalize_style_key(record.get("styleId"))
        style = style_labels.get(style_key, {})
        ready_styles.append(
            {
                "pair": record["pair"],
                "styleId": style_key,
                "styleCategory": style.get("style_category", ""),
                "occasion": style.get("occasion", ""),
                "targetPersona": style.get("target_persona", ""),
                "trendKeywords": style.get("trend_keywords", ""),
                "score": record.get("score"),
            }
        )

    for record in review_records:
        style_key = normalize_style_key(record.get("styleId"))
        style = style_labels.get(style_key, {})
        held_styles.append(
            {
                "pair": record["pair"],
                "styleId": style_key,
                "reason": "quality_review_required",
                "styleCategory": style.get("style_category", ""),
                "occasion": style.get("occasion", ""),
                "targetPersona": style.get("target_persona", ""),
            }
        )

    category_counts = Counter(item["styleCategory"] for item in ready_styles if item["styleCategory"])
    occasion_counts = Counter(item["occasion"] for item in ready_styles if item["occasion"])
    persona_counts = Counter(item["targetPersona"] for item in ready_styles if item["targetPersona"])

    top_ready = sorted(
        ready_styles,
        key=lambda item: (item["score"] or 0, item["styleId"]),
        reverse=True,
    )[:5]

    return {
        "readyForRecommendationCount": len(ready_styles),
        "heldForQualityReviewCount": len(held_styles),
        "topReadyStyles": top_ready,
        "heldStyles": held_styles,
        "trendSignals": {
            "topCategories": category_counts.most_common(5),
            "topOccasions": occasion_counts.most_common(5),
            "topPersonas": persona_counts.most_common(5),
        },
        "operatorActions": [
            "Move pass candidates into the demo gallery or recommendation pool.",
            "Hold review/fail candidates until retry candidates are generated and re-evaluated.",
            "Use the top category/persona signals to prepare campaign copy for the operations page.",
        ],
    }


def format_signal_counts(values: List[List[Any]] | List[tuple[Any, Any]]) -> str:
    if not values:
        return "-"
    return ", ".join(f"{name} ({count})" for name, count in values)


def render_markdown(payload: Dict[str, Any]) -> str:
    summary = payload["qualitySummary"]
    retry_plan = payload["retryPlan"]
    ops = payload["opsActions"]

    lines = [
        "# Try-On Agent Workflow v1",
        "",
        "This workflow safely reuses existing generated outputs, runs quality evaluation, builds a retry plan, and prepares operations actions.",
        "",
        "## Workflow Steps",
        "",
        "1. Load official paired generation manifest.",
        "2. Run `evaluate:tryon` quality checks.",
        "3. Split candidates into pass/review/fail queues.",
        "4. Generate retry commands for non-pass candidates.",
        "5. Produce operations actions for recommendation and campaign planning.",
        "",
        "## Quality Gate",
        "",
        f"- Total candidates: {summary['totalCandidates']}",
        f"- Average score: {summary['averageScore']}",
        f"- Pass: {summary['decisions']['pass']}",
        f"- Review: {summary['decisions']['review']}",
        f"- Fail: {summary['decisions']['fail']}",
        "",
        "## Retry Plan",
        "",
        "| Pair | Score | Decision | Preset | Command |",
        "| :--- | ---: | :--- | :--- | :--- |",
    ]

    if not retry_plan:
        lines.append("| - | - | pass | - | No retry needed. |")
    else:
        for item in retry_plan:
            lines.append(
                f"| {item['pair']} | {item['score']} | {item['decision']} | "
                f"{item['retryPreset']} | `{item['suggestedCommand']}` |"
            )

    lines.extend(
        [
            "",
            "## Operations Actions",
            "",
            f"- Ready for recommendation: {ops['readyForRecommendationCount']}",
            f"- Held for quality review: {ops['heldForQualityReviewCount']}",
            f"- Top categories: {format_signal_counts(ops['trendSignals']['topCategories'])}",
            f"- Top occasions: {format_signal_counts(ops['trendSignals']['topOccasions'])}",
            f"- Top personas: {format_signal_counts(ops['trendSignals']['topPersonas'])}",
            "",
            "## Top Ready Styles",
            "",
            "| Pair | Style | Category | Occasion | Persona | Keywords |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
    )

    for item in ops["topReadyStyles"]:
        lines.append(
            "| {pair} | {styleId} | {styleCategory} | {occasion} | {targetPersona} | {trendKeywords} |".format(
                **item
            )
        )

    if not ops["topReadyStyles"]:
        lines.append("| - | - | - | - | - | - |")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This v1 workflow does not call image generation by default, so it is safe to run without spending API credits.",
            "- Retry commands are explicit suggestions; the operator can run them after reviewing cost and quality tradeoffs.",
            "- The next upgrade is to let the workflow optionally execute retries and re-run evaluation automatically.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    if not args.skip_evaluate:
        run_quality_evaluation(args.manifest)

    report = load_json(QUALITY_REPORT_PATH)
    records = report["records"]
    style_labels = load_style_labels(STYLE_LABEL_PATH)
    payload = {
        "workflowVersion": "v1",
        "mode": "safe_existing_outputs",
        "qualitySummary": report["summary"],
        "retryPlan": build_retry_plan(records),
        "opsActions": build_ops_actions(records, style_labels),
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "tryon_agent_workflow.json"
    md_path = output_dir / "tryon_agent_workflow.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
