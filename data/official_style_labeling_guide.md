# Official Style Labeling Guide

This guide is for filling `official_style_label_template.csv` consistently.

## Goal

Use a compact, operations-friendly tag set that supports:

- trend analysis
- audience segmentation
- recommendation rules
- campaign copy generation

Do not over-annotate. One clear label per field is preferred over long free text.

## Field Rules

`primary_color`
- Use the visually dominant color of the style.

`secondary_color`
- Use the second most visible color.
- If the style is effectively single-color, set `none`.

`accent_color`
- Use only when a small but important accent exists, such as metallic lines or gem decoration.
- Otherwise set `none`.

`style_category`
- Choose the overall commercial style impression, not the technical paint method.
- Example:
  - nude glossy office nails -> `daily` or `minimal`
  - metallic mirror with gems -> `luxury`

`pattern`
- Choose the strongest visible design structure.
- For mixed designs across fingers, use the dominant pattern or `mixed`.

`finish`
- Choose the surface impression seen by customers: `glossy`, `matte`, `mirror`, `glitter`, etc.

`length`
- `short`: mostly within a practical daily wear length
- `medium`: visibly extended but not dramatic
- `long`: obviously extended, photo-oriented, or high-fashion length

`shape`
- Use the dominant nail silhouette.
- If multiple nail shapes are obvious, use `mixed`.

`complexity`
- `low`: mostly solid color / simple french / minimal line
- `medium`: one to two decorative techniques or a moderate mixed design
- `high`: multi-element, rich decoration, or visually dense design

`season`
- Use the best-fit commercial season.
- If it is broadly usable year-round, use `all-season`.

`occasion`
- Pick the strongest likely usage scenario.

`target_persona`
- Choose the most likely buyer segment from an operations perspective.

`price_band`
- This is not actual selling price.
- Use a merchandising judgment:
  - `budget`: easy daily style, low complexity
  - `mid`: mainstream commercial style
  - `premium`: high-fashion, luxury, or visually expensive design

`trend_keywords`
- Use 2-5 keywords separated by commas.
- Example: `minimal, nude, glossy`

`operator_notes`
- Short free-text notes only when needed.
- Use for ambiguity, promotional hints, or bundle suggestions.

`label_status`
- `todo`: not labeled
- `draft`: first pass complete
- `reviewed`: checked and confirmed

## Consistency Rules

1. Prefer the customer-facing impression over technical detail.
2. Do not create new category names outside `style_label_taxonomy.json`.
3. If uncertain between two tags, choose the one that is more useful for recommendation and campaign grouping.
4. Keep `trend_keywords` short and reusable.

## Suggested Workflow

1. Fill color, style, pattern, finish first.
2. Then fill length, shape, complexity.
3. Last fill season, occasion, target persona, price band.
4. Mark `draft`.
5. Do a second pass for consistency and mark `reviewed`.
