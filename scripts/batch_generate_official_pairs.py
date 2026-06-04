from __future__ import annotations

import argparse
import base64
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from extract_official_samples import normalize_samples


MAX_WIDTH = 900
MAX_HEIGHT = 1200
OVERLAY_OPACITY = 0.84
FEATHER_RADIUS = 6
BASE_LAYOUT = [
    {"x": 0.18, "y": 0.68, "w": 0.18, "h": 0.24, "rotation": -24},
    {"x": 0.33, "y": 0.45, "w": 0.14, "h": 0.21, "rotation": -10},
    {"x": 0.48, "y": 0.37, "w": 0.14, "h": 0.23, "rotation": -2},
    {"x": 0.62, "y": 0.40, "w": 0.14, "h": 0.21, "rotation": 7},
    {"x": 0.76, "y": 0.54, "w": 0.12, "h": 0.18, "rotation": 20},
]
RETRY_PRESETS = {
    "none": [],
    "alignment": [
        "Strictly align the manicure within the natural nail boundaries. Keep every design fully attached to the visible nail bed, with clean cuticle alignment and no floating, drifting, or spill onto the skin.",
        "Re-check nail placement on every visible finger. The manicure must sit flush on top of the original nail bed with centered geometry, consistent length, and realistic side-wall boundaries.",
    ],
    "style": [
        "Every visible nail must clearly show the target manicure design from the reference image. Do not leave nails bare, nearly nude, or close to the original natural nail look. Preserve the reference colors, patterns, finish, and decoration.",
        "Increase reference-style fidelity. Make the manicure visibly present on each nail while still preserving the original hand pose, skin tone, and lighting.",
    ],
    "mixed": [
        "Strictly align the manicure within the natural nail boundaries and keep every design attached to the visible nail bed. Avoid floating or shifted placement.",
        "Every visible nail must clearly show the target manicure design from the reference image. Do not leave nails bare or natural-looking.",
        "Re-check both placement and style fidelity. Keep the manicure centered on each nail, preserve the exact reference design language, and avoid any missing or misaligned nail art.",
    ],
}


@dataclass
class OfficialPair:
    hand_id: int
    style_id: int
    hand_url: str
    style_url: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch generate try-on images for official paired samples."
    )
    parser.add_argument(
        "--workbook",
        default=r"D:\Manicure\命题三美甲评测数据（对外版）.xlsx",
        help="Path to the official workbook.",
    )
    parser.add_argument(
        "--endpoint",
        default="http://localhost:3000/api/generate-tryon",
        help="Local generation endpoint exposed by the MVP server.",
    )
    parser.add_argument(
        "--provider",
        default="doubao",
        choices=["doubao", "openai"],
        help="Provider passed to the local generation endpoint.",
    )
    parser.add_argument(
        "--prompt",
        default="",
        help="Optional extra prompt appended to each request.",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/official-paired",
        help="Directory for generated images and logs.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only process the first N official pairs. 0 means all.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Regenerate images even if the output file already exists.",
    )
    parser.add_argument(
        "--save-guides",
        action="store_true",
        help="Save the synthesized guide image used for each request.",
    )
    parser.add_argument(
        "--request-retries",
        type=int,
        default=2,
        help="Retry count for API/network failures of the same request.",
    )
    parser.add_argument(
        "--request-retry-delay",
        type=float,
        default=2.0,
        help="Seconds to wait between API retry attempts.",
    )
    parser.add_argument(
        "--quality-retry-attempts",
        type=int,
        default=0,
        help="Generate extra candidates with retry prompt templates for each selected pair.",
    )
    parser.add_argument(
        "--retry-preset",
        default="mixed",
        choices=sorted(RETRY_PRESETS.keys()),
        help="Prompt template family used for quality retries.",
    )
    parser.add_argument(
        "--pairs",
        default="",
        help="Comma-separated pair ids like hand_01_style_01,hand_03_style_03. Empty means all official pairs.",
    )
    return parser.parse_args()


def parse_selected_pairs(raw_value: str) -> set[str]:
    if not raw_value.strip():
        return set()
    return {
        item.strip()
        for item in re.split(r"[,\s]+", raw_value.strip())
        if item.strip()
    }


def fetch_image_bytes(url: str, cache: Dict[str, bytes]) -> bytes:
    if url not in cache:
        with urllib.request.urlopen(url) as response:
            cache[url] = response.read()
    return cache[url]


def load_image(url: str, cache: Dict[str, bytes]) -> Image.Image:
    return Image.open(io.BytesIO(fetch_image_bytes(url, cache))).convert("RGBA")


def fit_canvas_size(image: Image.Image) -> tuple[int, int]:
    ratio = min(MAX_WIDTH / image.width, MAX_HEIGHT / image.height, 1.0)
    return max(1, round(image.width * ratio)), max(1, round(image.height * ratio))


def build_nail_layout(width: int, height: int) -> List[Dict[str, float]]:
    return [
        {
            "x": nail["x"] * width,
            "y": nail["y"] * height,
            "w": nail["w"] * width,
            "h": nail["h"] * height,
            "rotation": nail["rotation"],
        }
        for nail in BASE_LAYOUT
    ]


def alpha_mask(width: int, height: int, opacity: float) -> Image.Image:
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, width - 1, height - 1), fill=round(255 * opacity))
    return mask.filter(ImageFilter.GaussianBlur(FEATHER_RADIUS))


def paste_rotated(
    base_image: Image.Image,
    overlay: Image.Image,
    center_x: float,
    center_y: float,
    rotation_deg: float,
) -> None:
    rotated = overlay.rotate(rotation_deg, resample=Image.Resampling.BICUBIC, expand=True)
    left = round(center_x - rotated.width / 2)
    top = round(center_y - rotated.height / 2)
    base_image.alpha_composite(rotated, (left, top))


def synthesize_guide_image(
    hand_image: Image.Image,
    style_image: Image.Image,
) -> Image.Image:
    canvas_width, canvas_height = fit_canvas_size(hand_image)
    guide = hand_image.resize(
        (canvas_width, canvas_height), Image.Resampling.LANCZOS
    ).convert("RGBA")

    for nail in build_nail_layout(canvas_width, canvas_height):
        patch = ImageOps.fit(
            style_image,
            (max(1, round(nail["w"])), max(1, round(nail["h"]))),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        ).convert("RGBA")
        patch.putalpha(alpha_mask(patch.width, patch.height, OVERLAY_OPACITY))
        paste_rotated(guide, patch, nail["x"], nail["y"], nail["rotation"])

    return guide


def image_to_data_url(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    payload = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{payload}"


def decode_data_url(data_url: str) -> bytes:
    _, payload = data_url.split(",", 1)
    return base64.b64decode(payload)


def request_generation_once(endpoint: str, payload: dict) -> dict:
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
            message = payload.get("error") or payload
        except json.JSONDecodeError:
            message = body
        raise RuntimeError(f"HTTP {error.code}: {message}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(
            "Failed to reach the local MVP server. Start `npm start` in D:\\MVP first."
        ) from error


def request_generation_with_retries(
    endpoint: str,
    payload: dict,
    retries: int,
    retry_delay: float,
) -> dict:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return request_generation_once(endpoint, payload)
        except Exception as error:  # noqa: BLE001
            last_error = error
            if attempt >= retries:
                break
            time.sleep(retry_delay)
    if last_error is None:
        raise RuntimeError("Unknown request failure")
    raise last_error


def build_official_pairs(workbook_path: Path) -> List[OfficialPair]:
    samples = normalize_samples(workbook_path)
    style_by_enhanced = {
        sample["enhancedStyleUrl"]: sample for sample in samples["styleSamples"]
    }

    pairs = []
    for hand in samples["handSamples"]:
        enhanced_url = hand.get("linkedEnhancedStyleUrl", "")
        style = style_by_enhanced.get(enhanced_url)
        if not style:
            continue
        pairs.append(
            OfficialPair(
                hand_id=int(hand["id"]),
                style_id=int(style["id"]),
                hand_url=hand["handUrl"],
                style_url=style["enhancedStyleUrl"],
            )
        )
    return pairs


def ensure_output_dir(output_dir: Path) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = output_dir / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def build_prompt_variants(user_prompt: str, preset_name: str, retry_attempts: int) -> List[str]:
    prompts = [user_prompt.strip()]
    preset_steps = RETRY_PRESETS[preset_name]
    for attempt_index in range(retry_attempts):
        extra_instruction = (
            preset_steps[attempt_index]
            if attempt_index < len(preset_steps)
            else preset_steps[-1] if preset_steps else ""
        )
        merged = " ".join(part for part in [user_prompt.strip(), extra_instruction] if part)
        prompts.append(merged)
    return prompts


def iter_target_pairs(
    all_pairs: Iterable[OfficialPair],
    selected_pairs: set[str],
) -> List[OfficialPair]:
    if not selected_pairs:
        return list(all_pairs)

    filtered = []
    for pair in all_pairs:
        stem = f"hand_{pair.hand_id:02d}_style_{pair.style_id:02d}"
        if stem in selected_pairs:
            filtered.append(pair)
    return filtered


def main() -> int:
    args = parse_args()
    workbook_path = Path(args.workbook)
    if not workbook_path.exists():
        print(f"Workbook not found: {workbook_path}", file=sys.stderr)
        return 1

    all_pairs = build_official_pairs(workbook_path)
    selected_pairs = parse_selected_pairs(args.pairs)
    pairs = iter_target_pairs(all_pairs, selected_pairs)
    pairs = pairs[: args.limit] if args.limit > 0 else pairs
    if not pairs:
        print("No official paired samples found.", file=sys.stderr)
        return 1

    output_root = ensure_output_dir(Path(args.output_dir))
    cache: Dict[str, bytes] = {}
    results = []

    print(f"Found {len(pairs)} official pairs. Output directory: {output_root}")

    for index, pair in enumerate(pairs, start=1):
        stem = f"hand_{pair.hand_id:02d}_style_{pair.style_id:02d}"
        image_path = output_root / f"{stem}.png"
        guide_path = output_root / f"{stem}.guide.png"

        if image_path.exists() and not args.overwrite and args.quality_retry_attempts == 0:
            results.append(
                {
                    "pair": stem,
                    "status": "skipped",
                    "output": str(image_path),
                    "reason": "exists",
                }
            )
            print(f"[{index}/{len(pairs)}] Skipped {stem} (already exists)")
            continue

        started_at = time.perf_counter()
        try:
            hand_image = load_image(pair.hand_url, cache)
            style_image = load_image(pair.style_url, cache)
            guide_image = synthesize_guide_image(hand_image, style_image)

            if args.save_guides:
                guide_image.save(guide_path)

            guide_data_url = image_to_data_url(guide_image)
            prompts = build_prompt_variants(
                args.prompt,
                args.retry_preset,
                args.quality_retry_attempts,
            )
            attempt_records = []
            primary_output = image_path

            for attempt_index, prompt in enumerate(prompts):
                payload = {
                    "provider": args.provider,
                    "handImage": pair.hand_url,
                    "styleImage": pair.style_url,
                    "guideImage": guide_data_url,
                    "prompt": prompt,
                    "retryAttempt": attempt_index,
                    "retryPreset": args.retry_preset if attempt_index else None,
                }

                response = request_generation_with_retries(
                    args.endpoint,
                    payload,
                    retries=args.request_retries,
                    retry_delay=args.request_retry_delay,
                )
                if not response.get("imageDataUrl"):
                    raise RuntimeError("The local endpoint returned no imageDataUrl.")

                attempt_path = (
                    primary_output
                    if attempt_index == 0
                    else output_root / f"{stem}.retry_{attempt_index}.png"
                )
                attempt_path.write_bytes(decode_data_url(response["imageDataUrl"]))
                attempt_records.append(
                    {
                        "attempt": attempt_index,
                        "output": str(attempt_path),
                        "prompt": prompt,
                        "provider": response.get("provider"),
                        "model": response.get("model"),
                        "requestId": response.get("requestId"),
                        "providerDebug": response.get("providerDebug"),
                    }
                )

            elapsed = round(time.perf_counter() - started_at, 2)
            results.append(
                {
                    "pair": stem,
                    "status": "success",
                    "output": str(primary_output),
                    "attempts": attempt_records,
                    "elapsedSeconds": elapsed,
                }
            )
            print(
                f"[{index}/{len(pairs)}] Success {stem} ({elapsed}s, candidates={len(attempt_records)})"
            )
        except Exception as error:  # noqa: BLE001
            elapsed = round(time.perf_counter() - started_at, 2)
            results.append(
                {
                    "pair": stem,
                    "status": "failed",
                    "error": str(error),
                    "elapsedSeconds": elapsed,
                }
            )
            print(f"[{index}/{len(pairs)}] Failed {stem}: {error}")

    manifest = {
        "workbook": str(workbook_path),
        "provider": args.provider,
        "endpoint": args.endpoint,
        "pairCount": len(pairs),
        "selectedPairs": sorted(selected_pairs),
        "qualityRetryAttempts": args.quality_retry_attempts,
        "retryPreset": args.retry_preset,
        "requestRetries": args.request_retries,
        "results": results,
    }
    manifest_path = output_root / "results.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    success_count = sum(1 for item in results if item["status"] == "success")
    failed_count = sum(1 for item in results if item["status"] == "failed")
    skipped_count = sum(1 for item in results if item["status"] == "skipped")

    print(
        f"Completed. success={success_count}, failed={failed_count}, skipped={skipped_count}"
    )
    print(f"Manifest: {manifest_path}")
    return 0 if failed_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
