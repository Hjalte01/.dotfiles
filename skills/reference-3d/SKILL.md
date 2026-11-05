---
name: reference-3d
description: Shared twenty-view Luau EditableMesh workflow for the low, med and high Roblox 3D asset skills.
---

# Reference to 3D

Use the **M03-T approach**: an original image plus twenty generated camera views, followed by code-authored Roblox **Luau EditableMesh** geometry. Choose **med** unless the user specifies a tier. This is the user's workflow preference, not a guarantee of a quality or cost ranking.

| Tier | Geometry author | Reasoning | Entry point |
| --- | --- | --- | --- |
| low | `gpt-6.1-sol` | `low` | `$low-3d` |
| med / mid | `gpt-6.1-sol` | `ultra` | `$med-3d` |
| high | `gpt-6-astra` | `max` | `$high-3d` |

`$max-3d` and legacy core mode `max` mean **high**. For `compare`, run only the tiers requested; a legacy low/max comparison means low/high. Low-poly is a visual style, not a request for the Low reasoning tier. Resolve aliases through the installed skills root (`$CODEX_HOME/skills`, otherwise `~/.codex/skills`); separate declarative links make sibling `../` paths unreliable.

Choose **create** for a new reconstruction or **refine** for a change to a saved model. Refinement and reference cleanup use [refinement and retention](references/refinement-and-retention.md); another twenty-image batch is not automatic. Existing frozen jobs retain their pinned toolchain/model/prompt contracts: changing these skills does not migrate a running queue or rewrite its artifacts. Explicit user/project choices override this default.

## Select the actual workers

A skill does not switch its caller's model. For geometry, explicitly call `spawn_agent` with `fork_turns="none"`, the table's exact `model` and `reasoning_effort` values. In particular, med requests **`gpt-6.1-sol` with `reasoning_effort="ultra"`**, not medium, max or an inherited setting. Do not add an Astra polishing pass to low or med automatically.

Use a separate **`gpt-6.1-sol` / `low`** coordinator for new reference images in every tier. It coordinates the shared image backend, rather than selecting a Sol image model. Check the requested model-selection and deliverable capabilities before spending generation calls. If the exact model/effort is unavailable, explain the gap and checkpoint without new generation or substitution. For a complete native asset, disclose a missing Studio/bridge before costly new view generation and preserve useful preparation; a source-only request does not need Studio. Do not silently substitute a different geometry method. Record requested settings, available execution/usage receipts and unknown observations honestly.

## Reuse or generate the twenty views

Use this skill's unchanged `scripts/reference_set.py`; provide source and output paths.

1. Inspect and permanently retain the original. Reuse and `verify SET` an existing sealed set for that exact source hash. Otherwise `prepare SOURCE --output-root ROOT` creates or resumes its twenty camera jobs.
2. Have the Sol Low coordinator use the imagegen skill and built-in image generation for each missing view, explicitly referencing the original every time. Preserve the asset's identity, pose, proportions, parts, materials and palette; change only the camera. Use eight azimuths at elevations 0° and 30°, then four at 75°. These are twenty individual images, in addition to the original; rotations, duplicate files or a contact sheet do not replace them.
3. Retain each exact prompt and generation receipt through `record SET --view view-01 --image IMAGE --prompt PROMPT --receipt RECEIPT`. Inspect every individual view for identity and contradictions, resolving material inconsistencies before `seal SET`. Synthetic hidden surfaces remain interpretations.
4. Run `verify SET` before geometry. For comparisons, give every requested arm identical ordered files/hashes, instructions, tools, dimensions and budgets. Use fresh contexts without earlier candidate geometry or review feedback; preserve first submissions and identify later repairs separately. Do not generate another set for a different tier.

## Author and execute the Luau mesh

Read [the M03-T execution guide](references/m03t-luau-workflow.md) for the native factory interface, export and checks. For **create**, give the selected author the original, all twenty individual views, manifest and asset brief; require inspection of all twenty-one images. For **refine**, give the original, exact saved source and any retained useful views as described in the retention guide; released angles do not force regeneration for an ordinary edit.

The author produces editable `model.luau` using actual `AssetService:CreateEditableMesh()`, vertices and triangles, with intentional normals, colours and UVs. Prefer one MeshPart for a rigid asset when suitable. Build its silhouette, volumes, attachments and detail from the references; M03-T names the method, not a reusable whale shape. Match dimensions and economical triangle/material budgets to the asset and game. The whale trial's 24 studs / 10,000 triangles are not universal defaults, and a higher reasoning tier does not automatically mean a higher polygon budget.

Run the source in the appropriate Studio through available MCP/native tooling. Preserve project profile leases, other editors and existing safety/ownership rules. For a source-only request, deliver the requested Luau without claiming native verification. If a complete asset is requested but Studio is unavailable, save the source and report native execution/export pending; a script or simulated mesh is not a completed Roblox asset. Do not silently replace this route with Blender, Three.js-authored geometry or a hosted 3D generator.

## Deliver and verify

Keep the original, editable Luau, first source/derivatives, reference associations, actual native metrics and phase receipts. Export validated GLB/OBJ when required through real native mesh readback, or use a verified project-supported bake. A memory-backed EditableMesh preview is not a durable saved asset. Use existing task authorization for uploads; this skill alone does not authorize publishing games or spending money.

Check the actual asset from both sides and useful angles: silhouette, shading, colours, attachments, outward face winding, thin markings and intended openings. Correct a production asset's defects with recorded derivatives; preserve unmodified initial results in a comparison. When Studio integration/review is requested, save the real working place and verify loaded MeshParts in client Play. Keep visual approval distinct from technical success; no FPS or cost claim without measurement.

Report reference generation, inspection/source authoring, native build, export/upload/import and verification separately. Reused views incur no new image generation; their historical generation is shared work. Retain unknown token/cash values instead of estimating from elapsed time. Release generated angles only through the managed lifecycle after verified completion; retain frozen comparisons and unfinished consumers.
