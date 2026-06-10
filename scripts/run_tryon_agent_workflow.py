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
    parser.add_argument(
        "--auto-retry",
        action="store_true",
        help="Automatically execute retry batches for non-pass candidates and re-evaluate them.",
    )
    parser.add_argument(
        "--retry-attempts",
        type=int,
        default=2,
        help="Retry prompt variants generated for each auto-retry batch.",
    )
    parser.add_argument(
        "--refresh-ops-report",
        action="store_true",
        help="Rebuild the operations daily report after the final quality report is written.",
    )
    return parser.parse_args()


def run_quality_evaluation(manifest: str) -> None:
    run_quality_evaluation_to_dir(manifest, str(QUALITY_REPORT_PATH.parent))


def run_quality_evaluation_to_dir(manifest: str, output_dir: str) -> None:
    command = [sys.executable, "scripts/evaluate_tryon_results.py"]
    if manifest:
        command.extend(["--manifest", manifest])
    if output_dir:
        command.extend(["--output-dir", output_dir])
    subprocess.run(command, check=True)


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_output_dir(stdout: str) -> Path:
    match = re.search(r"Output directory:\s*(.+)", stdout)
    if not match:
        raise RuntimeError(f"Could not parse batch output directory from stdout: {stdout}")
    return Path(match.group(1).strip())


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
    if any("output_missing" in signal or "failed" in signal for signal in signals):
        return "mixed"
    if any("scene_drift_high" in signal or "aspect_ratio" in signal for signal in signals):
        return "preserve"
    if any("scene_drift_review" in signal for signal in signals):
        return "alignment"
    if any("nail_region_change_too_low" in signal for signal in signals):
        return "style"
    if any("nail_region_change_review" in signal for signal in signals):
        return "detail"
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


def run_retry_batch(preset: str, pairs: List[str], attempts: int) -> Dict[str, Any]:
    command = [
        sys.executable,
        "scripts/batch_generate_official_pairs.py",
        "--pairs",
        ",".join(pairs),
        "--quality-retry-attempts",
        str(attempts),
        "--retry-preset",
        preset,
        "--overwrite",
    ]
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    output_dir = parse_output_dir(result.stdout)
    manifest_path = output_dir / "results.json"
    quality_output_dir = output_dir / "quality"
    run_quality_evaluation_to_dir(str(manifest_path), str(quality_output_dir))
    return {
        "preset": preset,
        "pairs": pairs,
        "attempts": attempts,
        "command": " ".join(command),
        "stdout": result.stdout,
        "stderr": result.stderr,
        "outputDir": str(output_dir),
        "manifestPath": str(manifest_path),
        "qualityReportPath": str(quality_output_dir / "tryon_quality_report.json"),
    }


def summarize_records(records: List[Dict[str, Any]], manifest_label: str, workbook_warning: str | None) -> Dict[str, Any]:
    total = len(records)
    decisions = {
        decision: sum(1 for record in records if record["decision"] == decision)
        for decision in ["pass", "review", "fail"]
    }
    avg_score = (
        round(sum(record.get("score", 0) for record in records) / total, 2)
        if total
        else 0
    )

    return {
        "manifest": manifest_label,
        "totalCandidates": total,
        "averageScore": avg_score,
        "decisions": decisions,
        "workbookWarning": workbook_warning,
        "reviewPairs": [
            {
                "pair": record["pair"],
                "attempt": record["attempt"],
                "score": record["score"],
                "decision": record["decision"],
                "decisionSource": record.get("decisionSource", "rules"),
                "reasons": record.get("reasons", []),
                "warnings": record.get("warnings", []),
            }
            for record in records
            if record["decision"] != "pass"
        ],
    }


def merge_retry_records(
    base_records: List[Dict[str, Any]],
    retry_records: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    merged = {record["pair"]: record for record in base_records}
    decision_rank = {"fail": 0, "review": 1, "pass": 2}

    for record in retry_records:
        pair = record["pair"]
        current = merged.get(pair)
        if current is None:
            merged[pair] = record
            continue

        current_rank = decision_rank.get(current.get("decision", "review"), 0)
        retry_rank = decision_rank.get(record.get("decision", "review"), 0)
        current_score = current.get("score", 0)
        retry_score = record.get("score", 0)

        if retry_rank > current_rank or (
            retry_rank == current_rank and retry_score >= current_score
        ):
            retry_record = dict(record)
            retry_record["retryHistory"] = current.get("retryHistory", []) + [current]
            merged[pair] = retry_record
        else:
            current.setdefault("retryHistory", []).append(record)

    return list(merged.values())


def write_quality_report(
    report_path: Path,
    records: List[Dict[str, Any]],
    thresholds: Dict[str, Any],
    manifest_label: str,
    workbook_warning: str | None,
    source_manifests: List[str],
) -> Dict[str, Any]:
    summary = summarize_records(records, manifest_label, workbook_warning)
    payload = {
        "summary": summary,
        "thresholds": thresholds,
        "records": records,
        "workflow": {
            "mode": "auto_retry" if any(record.get("retryHistory") for record in records) else "rule_only",
            "sourceManifest": manifest_label,
            "sourceManifests": source_manifests,
        },
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


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
    initial_records = report["records"]
    style_labels = load_style_labels(STYLE_LABEL_PATH)
    retry_runs = []
    final_records = initial_records
    final_manifest_label = report["summary"]["manifest"]
    source_manifests = [report["summary"]["manifest"]]

    if args.auto_retry:
        retry_plan = build_retry_plan(initial_records)
        grouped_pairs: Dict[str, List[str]] = {}
        for item in retry_plan:
            grouped_pairs.setdefault(item["retryPreset"], []).append(item["pair"])

        retry_records = []
        for preset, pairs in grouped_pairs.items():
            run_info = run_retry_batch(preset, pairs, args.retry_attempts)
            retry_runs.append(run_info)
            retry_report = load_json(Path(run_info["qualityReportPath"]))
            retry_records.extend(retry_report.get("records", []))
            source_manifests.append(run_info["manifestPath"])

        if retry_records:
            final_records = merge_retry_records(initial_records, retry_records)
            final_manifest_label = "merged:" + " | ".join(source_manifests)

    final_payload = write_quality_report(
        QUALITY_REPORT_PATH,
        final_records,
        report.get("thresholds", {}),
        final_manifest_label,
        report["summary"].get("workbookWarning"),
        source_manifests,
    )

    if args.refresh_ops_report or args.auto_retry:
        subprocess.run([sys.executable, "scripts/build_ops_daily_report.py"], check=True)

    payload = {
        "workflowVersion": "v2",
        "mode": "auto_retry" if args.auto_retry else "safe_existing_outputs",
        "qualitySummary": final_payload["summary"],
        "initialQualitySummary": report["summary"],
        "retryPlan": build_retry_plan(initial_records),
        "retryRuns": retry_runs,
        "opsActions": build_ops_actions(final_records, style_labels),
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
