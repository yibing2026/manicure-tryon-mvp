from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List


DEFAULT_LOG_PATH = Path("logs/api-calls.jsonl")
DEFAULT_OUTPUT_DIR = Path("analysis/agent_log_insights_v1")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze API call logs and convert them into Agent iteration suggestions."
    )
    parser.add_argument("--log-path", default=str(DEFAULT_LOG_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args()


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            records.append({"status": "parse_error", "raw": line[:240]})
    return records


def safe_average(values: Iterable[float]) -> float:
    clean_values = [value for value in values if isinstance(value, (int, float))]
    return round(mean(clean_values), 2) if clean_values else 0


def classify_error(message: str) -> str:
    text = message.lower()
    if "activated" in text or "access" in text or "permission" in text:
        return "model_permission"
    if "404" in text or "does not exist" in text:
        return "model_or_endpoint"
    if "timeout" in text or "network" in text or "fetch" in text:
        return "network_or_timeout"
    if "key" in text or "auth" in text or "401" in text:
        return "auth_config"
    if "rate" in text or "429" in text:
        return "rate_limit"
    return "other"


def build_iteration_suggestions(summary: Dict[str, Any]) -> List[Dict[str, str]]:
    suggestions = []
    error_types = summary["error_types"]
    retry_presets = summary["retry_presets"]
    success_rate = summary["success_rate"]
    avg_duration = summary["average_duration_ms"]

    if success_rate < 0.85:
        suggestions.append(
            {
                "area": "provider_fallback",
                "priority": "high",
                "suggestion": "启用多 provider 兜底；当主模型失败时自动切换备用模型或返回规则预览结果。",
            }
        )

    if error_types.get("model_permission", 0) or error_types.get("model_or_endpoint", 0):
        suggestions.append(
            {
                "area": "model_config",
                "priority": "high",
                "suggestion": "将模型可用性做成启动前检查，避免运行时才暴露模型未开通或 endpoint 错误。",
            }
        )

    if error_types.get("rate_limit", 0):
        suggestions.append(
            {
                "area": "rate_control",
                "priority": "medium",
                "suggestion": "为批量生成增加并发限制、退避重试和预算上限，减少限流导致的失败。",
            }
        )

    if avg_duration > 45000:
        suggestions.append(
            {
                "area": "latency",
                "priority": "medium",
                "suggestion": "记录不同尺寸和质量参数的耗时，对低价值预览任务优先使用较低成本配置。",
            }
        )

    if retry_presets.get("alignment", 0) > retry_presets.get("style", 0):
        suggestions.append(
            {
                "area": "prompt_alignment",
                "priority": "medium",
                "suggestion": "位置偏移是主要重试信号，下一轮应强化保留手部姿态、指甲边界和引导图权重。",
            }
        )
    elif retry_presets.get("style", 0):
        suggestions.append(
            {
                "area": "prompt_style_transfer",
                "priority": "medium",
                "suggestion": "款式缺失是主要重试信号，下一轮应强化颜色、纹理、装饰元素和参考图一致性。",
            }
        )

    if not suggestions:
        suggestions.append(
            {
                "area": "steady_state",
                "priority": "low",
                "suggestion": "当前日志未暴露明显系统性失败，可继续扩大样例规模并观察新 bad case。",
            }
        )

    return suggestions


def summarize(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    status_counts = Counter(record.get("status", "unknown") for record in records)
    provider_counts = Counter(record.get("provider", "unknown") for record in records)
    model_counts = Counter(record.get("requestedModel", "unknown") for record in records)
    retry_presets = Counter(
        record.get("retry", {}).get("preset") or "none"
        for record in records
        if record.get("retry") is not None
    )
    error_types = Counter(
        classify_error(record.get("error", {}).get("message", ""))
        for record in records
        if record.get("status") == "error"
    )
    durations_by_provider: Dict[str, List[float]] = defaultdict(list)
    for record in records:
        provider = record.get("provider", "unknown")
        duration = record.get("durationMs")
        if isinstance(duration, (int, float)):
            durations_by_provider[provider].append(duration)

    total = len(records)
    success = status_counts.get("success", 0)
    summary = {
        "total_calls": total,
        "success_count": success,
        "error_count": status_counts.get("error", 0),
        "success_rate": round(success / total, 4) if total else 0,
        "status_counts": dict(status_counts),
        "provider_counts": dict(provider_counts),
        "model_counts": dict(model_counts),
        "retry_presets": dict(retry_presets),
        "error_types": dict(error_types),
        "average_duration_ms": safe_average(record.get("durationMs") for record in records),
        "average_duration_by_provider_ms": {
            provider: safe_average(values)
            for provider, values in durations_by_provider.items()
        },
    }
    summary["agent_iteration_suggestions"] = build_iteration_suggestions(summary)
    return summary


def render_markdown(payload: Dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Agent Log Insights v1",
        "",
        f"- Log path: `{payload['log_path']}`",
        f"- Total calls: {summary['total_calls']}",
        f"- Success rate: {summary['success_rate']}",
        f"- Average duration: {summary['average_duration_ms']} ms",
        "",
        "## Error Types",
        "",
    ]
    if summary["error_types"]:
        for name, count in summary["error_types"].items():
            lines.append(f"- {name}: {count}")
    else:
        lines.append("- No errors found.")

    lines.extend(["", "## Retry Presets", ""])
    for name, count in summary["retry_presets"].items():
        lines.append(f"- {name}: {count}")

    lines.extend(["", "## Agent Iteration Suggestions", ""])
    for item in summary["agent_iteration_suggestions"]:
        lines.append(f"- [{item['priority']}] {item['area']}：{item['suggestion']}")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Logs are treated as engineering telemetry, not user behavior data.",
            "- The analyzer does not read API keys or raw image base64 payloads.",
            "- Suggestions should feed the next prompt, retry, model-routing, or quality-gate iteration.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    log_path = Path(args.log_path)
    output_dir = Path(args.output_dir)
    records = load_jsonl(log_path)
    payload = {
        "report_version": "v1",
        "log_path": str(log_path),
        "summary": summarize(records),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "agent_log_insights.json"
    md_path = output_dir / "agent_log_insights.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
