from __future__ import annotations

import argparse
import csv
from pathlib import Path

from extract_official_samples import normalize_samples


HEADER = [
    "style_id",
    "style_label",
    "original_style_url",
    "enhanced_style_url",
    "primary_color",
    "secondary_color",
    "accent_color",
    "style_category",
    "pattern",
    "finish",
    "length",
    "shape",
    "complexity",
    "season",
    "occasion",
    "target_persona",
    "price_band",
    "trend_keywords",
    "operator_notes",
    "label_status",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a structured label template for official manicure styles."
    )
    parser.add_argument(
        "--workbook",
        default=r"D:\Manicure\命题三美甲评测数据（对外版）.xlsx",
        help="Path to the official workbook.",
    )
    parser.add_argument(
        "--output",
        default=r"D:\MVP\data\official_style_label_template.csv",
        help="Output CSV path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workbook_path = Path(args.workbook)
    if not workbook_path.exists():
        raise SystemExit(f"Workbook not found: {workbook_path}")

    samples = normalize_samples(workbook_path)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER)
        writer.writeheader()
        for sample in samples["styleSamples"]:
            writer.writerow(
                {
                    "style_id": sample["id"],
                    "style_label": sample["label"],
                    "original_style_url": sample["originalStyleUrl"],
                    "enhanced_style_url": sample["enhancedStyleUrl"],
                    "primary_color": "",
                    "secondary_color": "",
                    "accent_color": "",
                    "style_category": "",
                    "pattern": "",
                    "finish": "",
                    "length": "",
                    "shape": "",
                    "complexity": "",
                    "season": "",
                    "occasion": "",
                    "target_persona": "",
                    "price_band": "",
                    "trend_keywords": "",
                    "operator_notes": "",
                    "label_status": "todo",
                }
            )

    print(f"Wrote style label template: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
