from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build v1 operations strategy rules from labeled official styles."
    )
    parser.add_argument(
        "--input",
        default=r"D:\MVP\data\official_style_label_draft_v1.csv",
        help="Input labeled style CSV.",
    )
    parser.add_argument(
        "--output-dir",
        default=r"D:\MVP\analysis\ops_strategy_v1",
        help="Output directory for strategy artifacts.",
    )
    return parser.parse_args()


def load_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def style_ref(row: dict[str, str]) -> dict[str, str]:
    return {
        "style_id": f"style_{int(row['style_id']):02d}",
        "style_category": row["style_category"],
        "primary_color": row["primary_color"],
        "occasion": row["occasion"],
        "target_persona": row["target_persona"],
        "trend_keywords": row["trend_keywords"],
        "price_band": row["price_band"],
    }


def build_persona_rules(rows: list[dict[str, str]]) -> dict[str, dict]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["target_persona"]].append(row)

    persona_rules = {}
    for persona, items in grouped.items():
        top_styles = [style_ref(item) for item in items[:4]]
        top_occasions = sorted({item["occasion"] for item in items})
        top_colors = sorted({item["primary_color"] for item in items})
        top_styleset = sorted({item["style_category"] for item in items})
        persona_rules[persona] = {
            "recommended_styles": top_styles,
            "preferred_occasions": top_occasions,
            "preferred_colors": top_colors,
            "preferred_style_categories": top_styleset,
            "strategy_hint": (
                f"Prioritize {', '.join(top_styleset)} styles with "
                f"{', '.join(top_colors[:3])} tones for {persona}."
            ),
        }
    return persona_rules


def build_occasion_rules(rows: list[dict[str, str]]) -> dict[str, dict]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["occasion"]].append(row)

    rules = {}
    for occasion, items in grouped.items():
        rules[occasion] = {
            "recommended_styles": [style_ref(item) for item in items[:5]],
            "hero_colors": sorted({item["primary_color"] for item in items}),
            "hero_categories": sorted({item["style_category"] for item in items}),
            "campaign_angle": (
                f"Build {occasion} campaigns around "
                f"{', '.join(sorted({item['style_category'] for item in items})[:3])} "
                f"styles and highlight {', '.join(sorted({item['primary_color'] for item in items})[:3])} palettes."
            ),
        }
    return rules


def build_trend_clusters(rows: list[dict[str, str]]) -> list[dict]:
    clusters = [
        {
            "cluster_name": "premium_party_gloss",
            "match_rule": {
                "style_category": ["luxury", "cool-girl"],
                "occasion": ["party"],
            },
            "styles": [
                style_ref(row)
                for row in rows
                if row["style_category"] in {"luxury", "cool-girl"}
                and row["occasion"] == "party"
            ],
            "operator_action": "Use for high-attention homepage slots and night-out campaign creatives.",
        },
        {
            "cluster_name": "bridal_elegant_clean",
            "match_rule": {
                "occasion": ["wedding"],
                "style_category": ["elegant", "luxury"],
            },
            "styles": [
                style_ref(row)
                for row in rows
                if row["occasion"] == "wedding"
            ],
            "operator_action": "Package as bridal / event bundles and use polished trust-building copy.",
        },
        {
            "cluster_name": "cute_youth_festival",
            "match_rule": {
                "style_category": ["sweet", "daily"],
                "target_persona": ["student", "trend-follower"],
            },
            "styles": [
                style_ref(row)
                for row in rows
                if row["target_persona"] in {"student", "trend-follower"}
                and row["style_category"] in {"sweet", "daily"}
            ],
            "operator_action": "Use for campus, holiday, and low-threshold conversion campaigns.",
        },
    ]
    return clusters


def build_inventory_actions(rows: list[dict[str, str]]) -> list[dict]:
    short_count = sum(1 for row in rows if row["length"] == "short")
    long_count = sum(1 for row in rows if row["length"] == "long")
    premium_count = sum(1 for row in rows if row["price_band"] == "premium")
    daily_count = sum(1 for row in rows if row["occasion"] in {"daily", "commute"})

    return [
        {
            "theme": "inventory_balance",
            "observation": f"Long styles ({long_count}) exceed short styles ({short_count}).",
            "action": "Increase short daily-safe inventory exposure for broader conversion coverage.",
        },
        {
            "theme": "premium_focus",
            "observation": f"Premium styles count is {premium_count}.",
            "action": "Create premium merchandising slots and bundle copy for party and bridal users.",
        },
        {
            "theme": "daily_gap",
            "observation": f"Daily/commute occasion styles count is {daily_count}.",
            "action": "Promote daily-safe styles aggressively to office and minimalist audiences to fill the practical-demand gap.",
        },
    ]


def write_markdown(strategy: dict, output_path: Path) -> None:
    lines = [
        "# Operations Strategy Rules V1",
        "",
        "## Core Positioning",
        "- Prioritize premium glossy styles for attention-grabbing campaigns.",
        "- Use bridal/elegant clusters for trust-building and high-value conversions.",
        "- Use sweet/daily clusters for volume, student reach, and low-threshold offers.",
        "",
        "## Persona Rules",
    ]

    for persona, rule in strategy["persona_rules"].items():
        lines.append(f"- {persona}: {rule['strategy_hint']}")

    lines.extend(["", "## Occasion Rules"])
    for occasion, rule in strategy["occasion_rules"].items():
        lines.append(f"- {occasion}: {rule['campaign_angle']}")

    lines.extend(["", "## Trend Clusters"])
    for cluster in strategy["trend_clusters"]:
        lines.append(f"- {cluster['cluster_name']}: {cluster['operator_action']}")

    lines.extend(["", "## Inventory Actions"])
    for action in strategy["inventory_actions"]:
        lines.append(f"- {action['theme']}: {action['action']}")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    csv_path = Path(args.input)
    if not csv_path.exists():
        raise SystemExit(f"Input CSV not found: {csv_path}")

    rows = load_rows(csv_path)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    strategy = {
        "source_dataset": str(csv_path),
        "persona_rules": build_persona_rules(rows),
        "occasion_rules": build_occasion_rules(rows),
        "trend_clusters": build_trend_clusters(rows),
        "inventory_actions": build_inventory_actions(rows),
    }

    json_path = output_dir / "ops_strategy_rules_v1.json"
    md_path = output_dir / "ops_strategy_rules_v1.md"
    json_path.write_text(json.dumps(strategy, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(strategy, md_path)

    print(f"Wrote strategy JSON: {json_path}")
    print(f"Wrote strategy Markdown: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
