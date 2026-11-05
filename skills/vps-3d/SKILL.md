---
name: vps-3d
description: Prepare Roblox reference views and editable Luau EditableMesh source on a VPS or headless host, with low/med/high tiers and an explicit handoff for later Studio execution on a PC.
---

# VPS 3D preparation

Deliver **source preparation only**: the retained original, a shared sealed twenty-view reference set for a new reconstruction, actual editable `model.luau`, inspection evidence and a PC handoff. Studio execution, durable mesh baking/export, upload, import and native visual review happen later on the PC. **Studio availability is not a precondition for this requested preparation.** A prepared source is not a verified Roblox mesh.

Read the installed `$CODEX_HOME/skills/reference-3d/SKILL.md` (default `~/.codex/skills/reference-3d/SKILL.md`) and its `references/m03t-luau-workflow.md`. Reuse its unchanged `scripts/reference_set.py`, image identity rules and Luau factory interface. This skill explicitly narrows delivery to source preparation; do not apply the core's complete-native-asset Studio gate or retention release policy to this unfinished native consumer. Resolve dependencies through the installed skills root, not sibling `../` links. If the shared core is missing, checkpoint and report that dependency rather than inventing a replacement.

## Select the actual author

Use **med** unless the user specifies another tier. Low-poly styling does not select low reasoning.

| Phase/tier | Actual model | Reasoning |
| --- | --- | --- |
| New reference/camera coordinator | `gpt-6.1-sol` | `low` |
| Low geometry | `gpt-6.1-sol` | `low` |
| Med / mid geometry | `gpt-6.1-sol` | `ultra` |
| High / legacy max geometry | `gpt-6-astra` | `max` |

In an interactive chat, explicitly spawn fresh workers with `fork_turns="none"` and these exact `model` and `reasoning_effort` values. The reference coordinator uses the imagegen skill and built-in image generation. Do not add a second-tier polishing pass automatically.

In a serial queue stage that forbids delegation, author directly **only when trusted controller/run metadata confirms that the caller was already selected with the exact model and effort for that phase**. Reading this skill does not switch models. A low reference stage must hand off to a separately selected med geometry stage; it must not author med geometry itself. If metadata is absent or settings differ, preserve work and request correct scheduling. Record requested settings separately from observed settings and retained execution receipts; never invent usage or model receipts.

Check exact worker and image-tool capabilities before new generation. Missing Studio is expected here; missing required model/effort or built-in image generation is a preparation blocker. Preserve existing jobs' frozen contracts and outputs; the controller must explicitly schedule a new preparation contract rather than silently repin an in-flight legacy job.

## Prepare references and Luau

For **create**, inspect and retain the original unchanged. Reuse and `verify SET` an existing sealed set for its exact hash, otherwise `prepare SOURCE --output-root ROOT`. Generate twenty individual camera images anchored to the original every time: eight azimuths at elevations 0° and 30°, then four at 75°. Record each exact prompt, image and receipt with the shared helper, inspect every output for identity, resolve contradictions, then `seal SET` and `verify SET`. A contact sheet, rotations or duplicate files do not replace the twenty views. Reuse one shared set across selected tiers; do not regenerate solely because the author tier changes.

For **refine**, start from the exact saved editable source, original and retained useful references; record input revision/hashes and preserve the baseline. Ordinary edits do not force twenty new views. If reconstruction is necessary, use create and record that decision.

Give the geometry author the brief, dimensions, original, all twenty ordered images and sealed manifest for create; require individual inspection of all twenty-one images. Produce an actual Luau module returning `function(ctx)` using `AssetService:CreateEditableMesh()`, vertices, triangles and intentional normals, colours and UVs. Use the shared geometry-free context (`container`, `entryId`, `meshPart`, `registerEditableMesh`, `checkpoint`) and record its expected interface. Match silhouette, attachments, functional openings and economical budgets to the brief. Preserve first source and subsequent revisions. Do not replace this method with Three.js, Blender geometry, primitive placeholders or a hosted 3D generator.

Perform available **static** checks on saved source: syntax parsing when a compatible Luau tool is available, dependency/interface review and source hash capture. Describe each check and its limit. Do not claim that static analysis executed EditableMesh APIs, proved face counts or established appearance, collision or durability. Keep unavailable checks explicitly pending.

## Save the PC handoff

Read [the handoff contract](references/pc-handoff.md) and save `handoff.json` plus a brief `HANDOFF.md` beside the prepared source. Use `prepared_source_only` only after the requested source and reference evidence exist; partial jobs stay `interrupted` with a resumable next step. Report reference generation, inspection, source authoring and static checks separately; native work remains pending.

Retain the original, editable source revisions, all twenty image binaries, prompts, receipts, manifests and hashes while the PC native consumer is unfinished. Record that consumer in the managed retention lifecycle when available. If it cannot protect pending consumers, preserve the files and report that gap. Do not release angles merely because VPS preparation completed. This skill does not authorize paid fallback services, Roblox uploads or game publication.
