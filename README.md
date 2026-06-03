# Manicure Try-On MVP

This is a lightweight local MVP for manicure try-on. It helps us validate the
core experience first: upload a hand image, add a manicure style image, adjust
five nail regions, export a preview, and optionally call a backend image model
to generate a polished try-on result.

## Why this version

- It avoids training a segmentation model for the first milestone.
- It produces a stable demo that is easy to evaluate and iterate on.
- It leaves a clean integration point for a future multimodal image-editing API.

## Run locally

```bash
npm start
```

Then open `http://localhost:3000`.

## API configuration

Create `D:\MVP\.env.local` from `.env.example` and fill in at least one provider.

Supported providers:

- `openai`: uses `POST /v1/images/edits`
- `doubao`: uses Ark image generation with `reference_images` multi-image input

The frontend sends three images to the backend:

1. original hand image
2. manicure style reference
3. current canvas preview as a placement hint

This makes the generated result easier to control than sending only a hand
photo and a style image.

For official local testing, you can also point the app at the organizer workbook:

- `OFFICIAL_WORKBOOK_PATH=D:\Manicure\命题三美甲评测数据（对外版）.xlsx`
- `OFFICIAL_SAMPLES_PYTHON=python`

The server reads the workbook, extracts the official image URLs, and exposes
them through `/api/official-samples` for one-click loading in the UI.

## Doubao recommended setup

For local testing, prefer the Ark image generation flow with:

- `DOUBAO_IMAGE_MODEL=doubao-seedream-4.0`
- `DOUBAO_IMAGE_VERSION=250828`
- `DOUBAO_IMAGE_RESPONSE_FORMAT=url`

If your account only supports an older compatibility shape, you can enable:

- `DOUBAO_USE_LEGACY_IMAGE_FIELD=true`

The backend will otherwise send `reference_images`, which is the recommended
field for image-to-image generation in the current official docs.

## Current MVP scope

- Upload a hand image from local disk
- Upload a manicure style image from local disk
- Load remote hand/style images through the built-in image proxy
- Adjust each nail's position, size, and rotation
- Export the try-on result as a PNG
- Call OpenAI or Doubao from the backend to generate a polished try-on image
- Load official organizer samples with one click for local testing

## Batch generation for official paired samples

Use the existing local web backend as the generation gateway, then batch-create
the official paired sample set from the workbook.

1. Start the local server:

```bash
npm start
```

2. In another terminal, run the batch job:

```bash
npm run batch:official
```

Outputs are written to:

- `D:\MVP\outputs\official-paired\<timestamp>\*.png`
- `D:\MVP\outputs\official-paired\<timestamp>\results.json`

Useful options:

```bash
python scripts/batch_generate_official_pairs.py --limit 3 --save-guides
python scripts/batch_generate_official_pairs.py --provider openai
python scripts/batch_generate_official_pairs.py --overwrite
```

The batch script reuses the official hand-style pairing defined in the workbook
and synthesizes the same kind of guide image used by the browser UI, which
helps keep quality closer to the single-image interactive workflow.

## Retry bad samples with prompt templates

The batch script now supports two retry layers:

1. API retry for network / provider failures
2. quality retry for visually unsatisfying samples

Quality retry presets:

- `alignment`: use when nail placement drifts or floats
- `style`: use when the manicure style is weak, missing, or too close to bare nails
- `mixed`: combine placement and style corrections

Examples:

```bash
python scripts/batch_generate_official_pairs.py --pairs hand_01_style_01,hand_03_style_03 --quality-retry-attempts 2 --retry-preset mixed --overwrite
python scripts/batch_generate_official_pairs.py --pairs hand_03_style_03 --quality-retry-attempts 2 --retry-preset alignment --overwrite
python scripts/batch_generate_official_pairs.py --pairs hand_01_style_01 --quality-retry-attempts 2 --retry-preset style --overwrite
```

Output naming:

- base candidate: `hand_01_style_01.png`
- retry candidate 1: `hand_01_style_01.retry_1.png`
- retry candidate 2: `hand_01_style_01.retry_2.png`

The `results.json` manifest records every candidate prompt and output path, so
you can manually keep the best version after review.

## Style label template for operations

Export the 25 official style records into a CSV template:

```bash
npm run labels:styles
```

Output:

- `D:\MVP\data\official_style_label_template.csv`
- `D:\MVP\data\official_style_label_draft_v1.csv`
- `D:\MVP\data\style_label_taxonomy.json`
- `D:\MVP\data\official_style_labeling_guide.md`

This template is structured for the next operations stage, with columns for:

- color
- style category
- pattern
- finish
- length / shape
- complexity
- season / occasion
- target persona
- trend keywords
- operator notes

Use `style_label_taxonomy.json` as the controlled vocabulary and
`official_style_labeling_guide.md` as the annotation rulebook.
Use `official_style_label_draft_v1.csv` as the first-pass operational dataset.

Generate an operations-facing summary from the draft labels:

```bash
npm run analyze:styles
```

Output:

- `D:\MVP\analysis\style_ops_summary\official_style_ops_summary.json`
- `D:\MVP\analysis\style_ops_summary\official_style_ops_summary.md`

Generate the first structured operations strategy ruleset:

```bash
npm run strategy:ops
```

Output:

- `D:\MVP\analysis\ops_strategy_v1\ops_strategy_rules_v1.json`
- `D:\MVP\analysis\ops_strategy_v1\ops_strategy_rules_v1.md`

## Operations copilot demo API

The MVP now includes a minimal rule-based operations copilot endpoint:

- `POST /api/ops-copilot-demo`

It consumes the request contract in:

- `D:\MVP\analysis\ops_copilot_v1\ops_copilot_example_request.json`

And returns the same response structure as:

- `D:\MVP\analysis\ops_copilot_v1\ops_copilot_example_response.json`

Current behavior:

- recall candidate styles from the operator-provided style list
- merge persona rules and occasion rules
- score by persona fit, occasion fit, color fit, category fit, budget fit
- optionally boost styles from priority trend clusters
- return top style recommendations, campaign message, operator actions, risk notes

Local test:

1. Start the local server:

```bash
npm start
```

2. In another terminal, send the example request:

```powershell
$body = Get-Content -Path "D:\MVP\analysis\ops_copilot_v1\ops_copilot_example_request.json" -Raw
Invoke-RestMethod -Uri "http://localhost:3000/api/ops-copilot-demo" -Method Post -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 8
```

Or open the local dashboard page after starting the server:

- `http://localhost:3000/ops.html`

This endpoint is intentionally rule-based for the first demo version, so it is
easy to evaluate, explain, and iterate. A later version can keep the same
request/response contract and replace the internal logic with an LLM copilot.

## Next integration step

Improve the formal generation pipeline:

1. Detect or segment nail regions automatically
2. Generate a clean nail mask instead of relying only on the guide preview
3. Return edited result images plus quality scores
4. Keep the current UI for fallback correction and quick QA
