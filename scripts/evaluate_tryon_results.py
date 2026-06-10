from __future__ import annotations

import argparse
import io
import json
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from PIL import Image, ImageChops, ImageStat

from extract_official_samples import normalize_samples
from llm_utils import call_chat_json, get_llm_config, image_file_to_data_url


DEFAULT_WORKBOOK = r"D:\Manicure\命题三美甲评测数据（对外版）.xlsx"
DEFAULT_BASELINE_SUMMARY = Path("outputs/official-paired/official_paired_baseline_summary.json")
BASE_LAYOUT = [
    {"x": 0.18, "y": 0.68, "w": 0.18, "h": 0.24},
    {"x": 0.33, "y": 0.45, "w": 0.14, "h": 0.21},
    {"x": 0.48, "y": 0.37, "w": 0.14, "h": 0.23},
    {"x": 0.62, "y": 0.40, "w": 0.14, "h": 0.21},
    {"x": 0.76, "y": 0.54, "w": 0.12, "h": 0.18},
]


@dataclass
class EvaluationThresholds:
    min_edge: int
    min_file_kb: int
    max_aspect_ratio: float
    review_drift: float
    fail_drift: float
    review_nail_change: float
    fail_nail_change: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate manicure try-on batch outputs with lightweight rules."
    )
    parser.add_argument(
        "--manifest",
        default="",
        help="Path to a batch results.json. Defaults to the official paired baseline manifest.",
    )
    parser.add_argument(
        "--workbook",
        default=DEFAULT_WORKBOOK,
        help="Official workbook path used to recover source hand URLs for scene-drift checks.",
    )
    parser.add_argument(
        "--output-dir",
        default="analysis/tryon_quality_v1",
        help="Directory for the JSON and Markdown quality reports.",
    )
    parser.add_argument("--min-edge", type=int, default=512)
    parser.add_argument("--min-file-kb", type=int, default=80)
    parser.add_argument("--max-aspect-ratio", type=float, default=2.4)
    parser.add_argument("--review-drift", type=float, default=0.30)
    parser.add_argument("--fail-drift", type=float, default=0.42)
    parser.add_argument("--review-nail-change", type=float, default=0.035)
    parser.add_argument("--fail-nail-change", type=float, default=0.018)
    parser.add_argument(
        "--enable-vlm",
        action="store_true",
        help="Optionally add multimodal model judging on top of rule-based checks.",
    )
    parser.add_argument(
        "--vlm-limit",
        type=int,
        default=8,
        help="Maximum records sent to the multimodal model. Use 0 for all records.",
    )
    return parser.parse_args()


def resolve_manifest_path(raw_manifest: str) -> Path:
    if raw_manifest:
        return Path(raw_manifest)

    if DEFAULT_BASELINE_SUMMARY.exists():
        summary = json.loads(DEFAULT_BASELINE_SUMMARY.read_text(encoding="utf-8"))
        run_dir = Path(summary["baseline_run_dir"])
        return run_dir / "results.json"

    candidates = sorted(Path("outputs/official-paired").glob("*/results.json"))
    if not candidates:
        raise FileNotFoundError("No batch results.json found under outputs/official-paired.")
    return candidates[-1]


def parse_pair_id(pair_id: str) -> tuple[int | None, int | None]:
    match = re.match(r"hand_(\d+)_style_(\d+)", pair_id or "")
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def load_hand_urls(workbook_path: Path) -> tuple[Dict[int, str], str | None]:
    if not workbook_path.exists():
        return {}, f"Workbook not found: {workbook_path}"

    try:
        samples = normalize_samples(workbook_path)
    except Exception as error:  # noqa: BLE001 - keep evaluation resilient.
        return {}, f"Failed to read workbook: {error}"

    return {
        int(sample["id"]): sample["handUrl"]
        for sample in samples.get("handSamples", [])
        if sample.get("handUrl")
    }, None


def load_source_urls(workbook_path: Path) -> tuple[Dict[int, str], Dict[int, str], str | None]:
    if not workbook_path.exists():
        warning = f"Workbook not found: {workbook_path}"
        return {}, {}, warning

    try:
        samples = normalize_samples(workbook_path)
    except Exception as error:  # noqa: BLE001 - keep evaluation resilient.
        warning = f"Failed to read workbook: {error}"
        return {}, {}, warning

    hand_urls = {
        int(sample["id"]): sample["handUrl"]
        for sample in samples.get("handSamples", [])
        if sample.get("handUrl")
    }
    style_urls = {
        int(sample["id"]): sample.get("enhancedStyleUrl") or sample.get("originalStyleUrl")
        for sample in samples.get("styleSamples", [])
        if sample.get("enhancedStyleUrl") or sample.get("originalStyleUrl")
    }
    return hand_urls, style_urls, None


def iter_candidates(manifest: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    for result in manifest.get("results", []):
        attempts = result.get("attempts") or []
        if attempts:
            for attempt in attempts:
                yield {
                    "pair": result.get("pair"),
                    "batchStatus": result.get("status"),
                    "output": attempt.get("output"),
                    "attempt": attempt.get("attempt", 0),
                    "requestId": attempt.get("requestId"),
                    "provider": attempt.get("provider"),
                    "model": attempt.get("model"),
                    "elapsedSeconds": result.get("elapsedSeconds"),
                }
        else:
            yield {
                "pair": result.get("pair"),
                "batchStatus": result.get("status"),
                "output": result.get("output"),
                "attempt": 0,
                "requestId": result.get("requestId"),
                "provider": result.get("provider"),
                "model": result.get("model"),
                "elapsedSeconds": result.get("elapsedSeconds"),
            }


def fetch_image(url: str, cache: Dict[str, Image.Image]) -> Image.Image:
    if url not in cache:
        with urllib.request.urlopen(url, timeout=12) as response:
            payload = response.read()
        cache[url] = Image.open(io.BytesIO(payload)).convert("RGB")
    return cache[url]


def scene_drift_score(source: Image.Image, generated: Image.Image) -> float:
    # Compare low-resolution grayscale thumbnails so the metric focuses on pose/scene drift.
    size = (96, 96)
    source_thumb = source.convert("L").resize(size, Image.Resampling.LANCZOS)
    generated_thumb = generated.convert("L").resize(size, Image.Resampling.LANCZOS)
    diff = ImageChops.difference(source_thumb, generated_thumb)
    rms = ImageStat.Stat(diff).rms[0]
    return round(rms / 255, 4)


def nail_region_change_score(source: Image.Image, generated: Image.Image) -> float:
    # Use the same coarse nail layout as the guide image to detect weak style application.
    source_resized = source.convert("RGB").resize(generated.size, Image.Resampling.LANCZOS)
    generated_rgb = generated.convert("RGB")
    width, height = generated_rgb.size
    region_scores = []

    for region in BASE_LAYOUT:
        box_width = max(8, round(region["w"] * width))
        box_height = max(8, round(region["h"] * height))
        center_x = round(region["x"] * width)
        center_y = round(region["y"] * height)
        left = max(0, center_x - box_width // 2)
        top = max(0, center_y - box_height // 2)
        right = min(width, left + box_width)
        bottom = min(height, top + box_height)

        if right <= left or bottom <= top:
            continue

        source_crop = source_resized.crop((left, top, right, bottom))
        generated_crop = generated_rgb.crop((left, top, right, bottom))
        diff = ImageChops.difference(source_crop, generated_crop)
        channel_means = ImageStat.Stat(diff).mean
        region_scores.append(sum(channel_means) / (len(channel_means) * 255))

    if not region_scores:
        return 0
    return round(sum(region_scores) / len(region_scores), 4)


def evaluate_candidate(
    candidate: Dict[str, Any],
    hand_urls: Dict[int, str],
    source_cache: Dict[str, Image.Image],
    thresholds: EvaluationThresholds,
) -> Dict[str, Any]:
    pair = candidate.get("pair") or ""
    hand_id, style_id = parse_pair_id(pair)
    output_path = Path(candidate.get("output") or "")
    reasons: List[str] = []
    warnings: List[str] = []
    score = 100

    record: Dict[str, Any] = {
        "pair": pair,
        "handId": hand_id,
        "styleId": style_id,
        "attempt": candidate.get("attempt", 0),
        "requestId": candidate.get("requestId"),
        "provider": candidate.get("provider"),
        "model": candidate.get("model"),
        "output": str(output_path),
        "batchStatus": candidate.get("batchStatus"),
    }

    if candidate.get("batchStatus") != "success":
        score -= 40
        reasons.append("batch_status_not_success")

    if candidate.get("attempt", 0) > 0:
        warnings.append("quality_retry_candidate")

    if not output_path.exists():
        record.update(
            {
                "exists": False,
                "score": 0,
                "decision": "fail",
                "reasons": reasons + ["output_missing"],
                "warnings": warnings,
            }
        )
        return record

    file_kb = round(output_path.stat().st_size / 1024, 1)
    record["exists"] = True
    record["fileKB"] = file_kb

    if file_kb < thresholds.min_file_kb:
        score -= 20
        reasons.append("file_too_small")

    try:
        with Image.open(output_path) as image:
            generated = image.convert("RGB")
            width, height = generated.size
    except Exception as error:  # noqa: BLE001 - report broken image files.
        record.update(
            {
                "score": 0,
                "decision": "fail",
                "reasons": reasons + [f"image_open_failed:{error}"],
                "warnings": warnings,
            }
        )
        return record

    aspect_ratio = round(max(width / height, height / width), 3)
    record.update(
        {
            "width": width,
            "height": height,
            "aspectRatio": aspect_ratio,
        }
    )

    if min(width, height) < thresholds.min_edge:
        score -= 25
        reasons.append("image_edge_too_small")

    if aspect_ratio > thresholds.max_aspect_ratio:
        score -= 15
        reasons.append("aspect_ratio_unusual")

    hand_url = hand_urls.get(hand_id or -1)
    if hand_url:
        try:
            source_hand = fetch_image(hand_url, source_cache)
            drift = scene_drift_score(source_hand, generated)
            nail_change = nail_region_change_score(source_hand, generated)
            record["sceneDrift"] = drift
            record["nailRegionChange"] = nail_change
            if drift >= thresholds.fail_drift:
                score -= 25
                reasons.append("scene_drift_high")
            elif drift >= thresholds.review_drift:
                score -= 10
                warnings.append("scene_drift_review")

            if nail_change <= thresholds.fail_nail_change:
                score -= 20
                reasons.append("nail_region_change_too_low")
            elif nail_change <= thresholds.review_nail_change:
                score -= 10
                warnings.append("nail_region_change_review")
        except Exception as error:  # noqa: BLE001 - source checks are optional.
            warnings.append(f"source_fetch_or_compare_failed:{error}")
    else:
        warnings.append("source_hand_unavailable")

    score = max(0, min(100, score))
    decision = "pass"
    if score < 60 or "scene_drift_high" in reasons:
        decision = "fail"
    elif score < 80 or warnings:
        decision = "review"

    record.update(
        {
            "score": score,
            "decision": decision,
            "decisionSource": "rules",
            "ruleScore": score,
            "ruleDecision": decision,
            "reasons": reasons,
            "warnings": warnings,
        }
    )
    return record


def normalize_vlm_decision(value: Any) -> str:
    decision = str(value or "review").strip().lower()
    return decision if decision in {"pass", "review", "fail"} else "review"


def choose_final_decision(rule_decision: str, vlm_decision: str) -> str:
    order = {"pass": 0, "review": 1, "fail": 2}
    return rule_decision if order[rule_decision] >= order[vlm_decision] else vlm_decision


def build_vlm_messages(
    record: Dict[str, Any],
    hand_url: str | None,
    style_url: str | None,
) -> List[Dict[str, Any]]:
    output_path = Path(record.get("output") or "")
    image_items: List[Dict[str, Any]] = []
    if hand_url:
        image_items.append({"type": "image_url", "image_url": {"url": hand_url}})
    if style_url:
        image_items.append({"type": "image_url", "image_url": {"url": style_url}})
    image_items.append(
        {
            "type": "image_url",
            "image_url": {"url": image_file_to_data_url(output_path)},
        }
    )

    prompt = (
        "你是美甲 AI 试戴质检员。请依次查看图片：原始手图、款式参考图、生成试戴图。"
        "如果前两张缺失，则只根据生成试戴图和规则分数判断。"
        "请检查：1 指甲贴合是否准确；2 款式是否应用到指甲；3 手部结构、肤色、背景是否保真；"
        "4 款式颜色和装饰是否与参考图一致。必须只返回 JSON，不要 Markdown。"
        "JSON 字段：score(0-100), decision(pass/review/fail), alignment_score, "
        "nail_coverage_score, hand_fidelity_score, style_consistency_score, "
        "issues(array), retry_preset(alignment/style/mixed/none), explanation。"
        f"规则系统初评分：{record.get('ruleScore')}，规则系统判断：{record.get('ruleDecision')}，"
        f"规则原因：{record.get('reasons')}，规则警告：{record.get('warnings')}。"
    )
    return [
        {
            "role": "system",
            "content": (
                "You are a strict visual QA evaluator for manicure try-on images. "
                "Return compact JSON only."
            ),
        },
        {
            "role": "user",
            "content": [{"type": "text", "text": prompt}, *image_items],
        },
    ]


def apply_vlm_evaluation(
    records: List[Dict[str, Any]],
    hand_urls: Dict[int, str],
    style_urls: Dict[int, str],
    limit: int,
) -> Dict[str, Any]:
    config = get_llm_config("VLM")
    selected = [record for record in records if record.get("decision") != "pass"]
    selected.extend(record for record in records if record.get("decision") == "pass")
    if limit > 0:
        selected = selected[:limit]

    summary = {
        "enabled": True,
        "model": config.get("model"),
        "apiBase": config.get("api_base"),
        "requested": len(selected),
        "succeeded": 0,
        "failed": 0,
        "errors": [],
    }

    for record in selected:
        hand_url = hand_urls.get(record.get("handId") or -1)
        style_url = style_urls.get(record.get("styleId") or -1)
        try:
            response = call_chat_json(
                messages=build_vlm_messages(record, hand_url, style_url),
                config=config,
                temperature=0.1,
                timeout=120,
            )
            vlm_json = response["json"]
            vlm_decision = normalize_vlm_decision(vlm_json.get("decision"))
            vlm_score = int(max(0, min(100, round(float(vlm_json.get("score", 0))))))
            rule_decision = record.get("ruleDecision", record.get("decision", "review"))
            final_decision = choose_final_decision(rule_decision, vlm_decision)
            final_score = round((record.get("ruleScore", 0) * 0.55) + (vlm_score * 0.45))

            record["vlmEvaluation"] = {
                "model": response["model"],
                "score": vlm_score,
                "decision": vlm_decision,
                "alignmentScore": vlm_json.get("alignment_score"),
                "nailCoverageScore": vlm_json.get("nail_coverage_score"),
                "handFidelityScore": vlm_json.get("hand_fidelity_score"),
                "styleConsistencyScore": vlm_json.get("style_consistency_score"),
                "issues": vlm_json.get("issues", []),
                "retryPreset": vlm_json.get("retry_preset"),
                "explanation": vlm_json.get("explanation", ""),
                "usage": response.get("usage"),
            }
            record["score"] = min(record.get("score", 0), final_score)
            record["decision"] = final_decision
            record["decisionSource"] = "rules+vlm"
            if final_decision != rule_decision:
                record.setdefault("warnings", []).append("vlm_escalated_decision")
            summary["succeeded"] += 1
        except Exception as error:  # noqa: BLE001 - keep fallback usable.
            record.setdefault("warnings", []).append(f"vlm_failed:{error}")
            summary["failed"] += 1
            summary["errors"].append({"pair": record.get("pair"), "message": str(error)})

    return summary


def summarize(records: List[Dict[str, Any]], manifest_path: Path, workbook_warning: str | None) -> Dict[str, Any]:
    total = len(records)
    decisions = {
        decision: sum(1 for record in records if record["decision"] == decision)
        for decision in ["pass", "review", "fail"]
    }
    avg_score = round(
        sum(record.get("score", 0) for record in records) / total,
        2,
    ) if total else 0

    return {
        "manifest": str(manifest_path),
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
                "reasons": record["reasons"],
                "warnings": record["warnings"],
            }
            for record in records
            if record["decision"] != "pass"
        ],
    }


def render_markdown(summary: Dict[str, Any], records: List[Dict[str, Any]]) -> str:
    lines = [
        "# Try-On Quality Evaluation v1",
        "",
        "This report is generated by `scripts/evaluate_tryon_results.py`.",
        "It uses lightweight engineering rules rather than a trained vision model.",
        "",
        "## Summary",
        "",
        f"- Manifest: `{summary['manifest']}`",
        f"- Total candidates: {summary['totalCandidates']}",
        f"- Average score: {summary['averageScore']}",
        f"- Pass: {summary['decisions']['pass']}",
        f"- Review: {summary['decisions']['review']}",
        f"- Fail: {summary['decisions']['fail']}",
    ]

    if summary.get("workbookWarning"):
        lines.append(f"- Workbook/source check warning: {summary['workbookWarning']}")

    if summary.get("vlm"):
        vlm = summary["vlm"]
        lines.extend(
            [
                f"- VLM enabled: {vlm.get('enabled')}",
                f"- VLM model: `{vlm.get('model')}`",
                f"- VLM succeeded / failed: {vlm.get('succeeded')} / {vlm.get('failed')}",
            ]
        )

    lines.extend(
        [
            "",
            "## Review Queue",
            "",
            "| Pair | Attempt | Score | Decision | Reasons | Warnings |",
            "| :--- | ---: | ---: | :--- | :--- | :--- |",
        ]
    )

    review_records = [record for record in records if record["decision"] != "pass"]
    if not review_records:
        lines.append("| - | - | - | pass | - | - |")
    else:
        for record in review_records:
            lines.append(
                "| {pair} | {attempt} | {score} | {decision} | {reasons} | {warnings} |".format(
                    pair=record["pair"],
                    attempt=record["attempt"],
                    score=record["score"],
                    decision=record["decision"],
                    reasons=", ".join(record["reasons"]) or "-",
                    warnings=", ".join(record["warnings"]) or "-",
                )
            )

    lines.extend(
        [
            "",
            "## Rule Notes",
            "",
            "- `sceneDrift` compares low-resolution grayscale thumbnails of the source hand and generated result.",
            "- A high drift score means the generated image may have changed pose, scene, crop, or hand structure too much.",
            "- `nailRegionChange` compares expected nail regions between source and generated images; very low change may mean the style is missing or too weak.",
            "- Retry candidates are marked for review because a human or later Agent step should choose the best candidate.",
            "- The rule system is the default fallback; optional VLM judging can escalate ambiguous or risky cases.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    thresholds = EvaluationThresholds(
        min_edge=args.min_edge,
        min_file_kb=args.min_file_kb,
        max_aspect_ratio=args.max_aspect_ratio,
        review_drift=args.review_drift,
        fail_drift=args.fail_drift,
        review_nail_change=args.review_nail_change,
        fail_nail_change=args.fail_nail_change,
    )
    manifest_path = resolve_manifest_path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    hand_urls, style_urls, workbook_warning = load_source_urls(Path(args.workbook))
    source_cache: Dict[str, Image.Image] = {}

    records = [
        evaluate_candidate(candidate, hand_urls, source_cache, thresholds)
        for candidate in iter_candidates(manifest)
    ]
    vlm_summary = None
    if args.enable_vlm:
        vlm_summary = apply_vlm_evaluation(records, hand_urls, style_urls, args.vlm_limit)

    summary = summarize(records, manifest_path, workbook_warning)
    if vlm_summary:
        summary["vlm"] = vlm_summary

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_payload = {
        "summary": summary,
        "thresholds": thresholds.__dict__,
        "records": records,
    }

    json_path = output_dir / "tryon_quality_report.json"
    md_path = output_dir / "tryon_quality_report.md"
    json_path.write_text(
        json.dumps(report_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(summary, records), encoding="utf-8")

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
