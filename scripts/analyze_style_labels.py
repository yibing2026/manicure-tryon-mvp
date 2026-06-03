from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze the official draft style label dataset for operations."
    )
    parser.add_argument(
        "--input",
        default=r"D:\MVP\data\official_style_label_draft_v1.csv",
        help="Input CSV path.",
    )
    parser.add_argument(
        "--output-dir",
        default=r"D:\MVP\analysis\style_ops_summary",
        help="Directory for JSON and Markdown outputs.",
    )
    return parser.parse_args()


def load_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def top_counts(rows: list[dict[str, str]], field: str) -> list[dict[str, object]]:
    counter = Counter(row[field] for row in rows if row.get(field))
    return [{"value": key, "count": value} for key, value in counter.most_common()]


def build_persona_recommendations(rows: list[dict[str, str]]) -> dict[str, list[str]]:
    grouped: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for row in rows:
        persona = row["target_persona"]
        grouped[persona].append(
            (
                row["style_id"],
                row["style_category"],
                row["trend_keywords"],
            )
        )

    output: dict[str, list[str]] = {}
    for persona, items in grouped.items():
        formatted = []
        for style_id, style_category, keywords in items[:4]:
            formatted.append(
                f"style_{int(style_id):02d}: {style_category} | {keywords}"
            )
        output[persona] = formatted
    return output


def build_color_style_matrix(rows: list[dict[str, str]]) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        matrix[row["primary_color"]][row["style_category"]] += 1
    return {
        color: dict(sorted(style_counts.items(), key=lambda item: (-item[1], item[0])))
        for color, style_counts in sorted(matrix.items())
    }


def write_markdown(summary: dict, output_path: Path) -> None:
    lines = [
        "# Official Style Operations Summary",
        "",
        f"- Total styles: {summary['total_styles']}",
        f"- Reviewed status counts: {json.dumps(summary['label_status'], ensure_ascii=False)}",
        "",
        "## Top Primary Colors",
    ]
    for item in summary["top_primary_colors"][:8]:
        lines.append(f"- {item['value']}: {item['count']}")

    lines.extend(["", "## Top Style Categories"])
    for item in summary["top_style_categories"]:
        lines.append(f"- {item['value']}: {item['count']}")

    lines.extend(["", "## Top Occasions"])
    for item in summary["top_occasions"]:
        lines.append(f"- {item['value']}: {item['count']}")

    lines.extend(["", "## Target Persona Recommendations"])
    for persona, styles in summary["persona_recommendations"].items():
        lines.append(f"- {persona}:")
        for style in styles:
            lines.append(f"  - {style}")

    lines.extend(["", "## Operational Takeaways"])
    lines.extend(summary["takeaways"])
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    csv_path = Path(args.input)
    if not csv_path.exists():
        raise SystemExit(f"Input CSV not found: {csv_path}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = load_rows(csv_path)
    summary = {
        "total_styles": len(rows),
        "top_primary_colors": top_counts(rows, "primary_color"),
        "top_style_categories": top_counts(rows, "style_category"),
        "top_patterns": top_counts(rows, "pattern"),
        "top_finishes": top_counts(rows, "finish"),
        "top_occasions": top_counts(rows, "occasion"),
        "top_personas": top_counts(rows, "target_persona"),
        "label_status": dict(Counter(row["label_status"] for row in rows)),
        "color_style_matrix": build_color_style_matrix(rows),
        "persona_recommendations": build_persona_recommendations(rows),
        "takeaways": [
            "1. The current style set is heavily concentrated in glossy premium-oriented designs; this supports luxury and party recommendations first.",
            "2. Short daily-safe styles exist, but they are underrepresented compared with long decorative styles; this is a useful inventory balancing insight.",
            "3. Student, fashion-lover, young-professional, and bridal-user are the clearest initial persona buckets for recommendation and campaign copy.",
            "4. Red/pink/nude/white dominate the palette; black and metallic silver/gold act as stronger accent clusters for trend campaigns.",
            "5. Wedding, party, dating, and commute are the most reusable occasion axes for early-stage operations segmentation."
        ]
    }

    json_path = output_dir / "official_style_ops_summary.json"
    md_path = output_dir / "official_style_ops_summary.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(summary, md_path)

    print(f"Wrote JSON summary: {json_path}")
    print(f"Wrote Markdown summary: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
