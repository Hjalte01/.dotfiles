---
name: reference-3d
description: Create editable 3D assets from an approved image and twenty shared views, refine saved models, and compare Sol Low and Astra Max when requested.
---

# Reference to 3D

Choose `low` (default), `max`, or `compare` from the request. Low uses GPT-6.1 Sol with low reasoning for geometry; max uses GPT-6 Astra with max reasoning. Both share a GPT-6.1 Sol low coordinator for the twenty-view stage. Never add an Astra polishing pass unless requested; preserve each initial result.

Choose **create** or **refine** independently of the model mode. Create follows the twenty-view workflow below. For changes to a saved model, or cleanup of completed reference sets, read [Refinement and retention](references/refinement-and-retention.md). Keep the original reference permanently; managed cleanup can release generated angles only after verified completion and when no unfinished consumer needs them. Frozen comparisons retain their assigned inputs.

## Select real workers

A skill cannot change its caller's model. Explicitly select workers with the available model-selection mechanism: for collaboration use `spawn_agent` with `fork_turns="none"`, `model="gpt-6.1-sol"`, `reasoning_effort="low"`, or `model="gpt-6-astra"`, `reasoning_effort="max"`. This workflow authorizes those model-specific workers, not extra unrelated delegation. Record requested and observed model/effort, execution IDs and raw usage receipts; mark unavailable observations unknown. If selection is unavailable, explain the missing capability before spending generation calls. Never silently use the caller instead. Image generation uses the shared image backend; Sol Low coordinates it, rather than selecting a Sol image model.

## Freeze the shared references

Use `scripts/reference_set.py` relative to this skill. Paths and output roots are caller supplied, so the same workflow works on the VPS.

1. Inspect the approved source. `prepare SOURCE --output-root ROOT` creates or resumes a source-hash cache and twenty camera jobs. The original is the identity anchor, not one of the twenty new views.
2. In the Sol Low worker, use the imagegen skill and built-in image generation to produce each planned view with the original image explicitly referenced each time. Show the same single isolated asset: preserve pose, silhouette, proportions, parts, palette and materials. Change only camera angle. No collages, scenes, redesigned details, programmatic image rotations or duplicated files. Angles are relative to the asset's front: eight azimuths at elevations 0° and 30°, then four at 75°.
3. Save each exact prompt and generation receipt. `record SET --view view-01 --image IMAGE --prompt PROMPT --receipt RECEIPT` copies them with provenance. Never silently overwrite completed work. Resume missing views; retain rejected attempts outside the registered set. Inspect all twenty individual images, checking identity and contradictions; a contact sheet alone is insufficient. Synthetic unseen surfaces are interpretations, not measured ground truth. Resolve material inconsistencies before sealing.
4. `seal SET` verifies twenty distinct file hashes and immutable source/provenance and writes the ordered manifest hash. `verify SET` before each geometry arm. Both arms must receive the identical files, order and hashes; never regenerate a second set for max.

## Produce actual geometry

Give each arm a fresh selected model context, the original, all twenty individual images, sealed manifest, asset description and the same tools, dimensions, triangle/material budgets and validation criteria. Require inspection of every image. Images are references; the result must be editable geometry authored through code or modeling tools, never a raster render labeled a 3D model. No paid or third-party geometry-generation fallback.

Choose one common toolchain before comparison. A compatible project may provide `games/asset_design_lab/experiment/toolkit`: its Three.js exporter creates GLB/OBJ, checker validates glTF and material-colored rigid meshes, and renderer makes authoring previews. Its static pilot adapter has a 10,000-triangle limit; this is an adapter limit, not a universal game standard. Inspect the local toolkit interface before use. Blender/headless Blender is another option if available; use the same pipeline for both arms. Check device resources and software before placing jobs, honor queue locks and user limits, and stop on exhausted allowance, missing capabilities or repeated failure instead of retrying indefinitely.

Save separate `low/` and `max/` outputs: editable model and generation source, validated GLB, validation report, dimensions/triangles/material metrics, matching camera renders, worker configuration and raw usage receipts. Keep comparisons fair and distinguish measured usage from account-wide weekly estimates. Renders do not prove Roblox readiness. When requested, create a separate native Studio test place with labeled side-by-side assets, equal presentation and actual Play verification. Preserve authorization boundaries: preparing local files does not authorize asset uploads or publishing a place.
