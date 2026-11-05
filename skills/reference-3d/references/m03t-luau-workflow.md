# M03-T: reference-driven Luau EditableMesh

This is a geometry-authoring route, not Roblox Assistant's AI procedural-model generator. The selected tier authors Luau from the image set; Studio executes that exact source. Modelling choices remain the author's responsibility. Do not copy the whale's anatomy, palette or numbers into an unrelated asset.

## Source interface

Prefer a source module returning `function(ctx)` with these geometry-free facilities:

| Context | Meaning |
| --- | --- |
| `ctx.container` | The asset's isolated native Model; build outside the DataModel where practical. |
| `ctx.entryId` | Stable candidate/asset identifier. |
| `ctx.meshPart(mesh, name)` | Actual `CreateMeshPartAsync(Content.fromObject(mesh), options)`, parenting to the owned container and retaining the mesh/part pair. |
| `ctx.registerEditableMesh(mesh, part)` | Register a directly created memory-backed pair for readback/baking. |
| `ctx.checkpoint()` | Ownership/guard check and a yield between logical batches. |

Create the actual mesh with `AssetService:CreateEditableMesh()`. `AddVertex`, `AddTriangle`, `AddNormal`, `AddColor` and `AddUV` return IDs. Set corner attribute **IDs** with `SetFaceNormals`, `SetFaceColors` and `SetFaceUVs`. Return the owned Model or nil; do not insert automatically running scripts or edit other scene content. Keep the editable source as a ModuleScript/data artifact when embedding it in a review place.

Use smooth normals on intended curved surfaces and intentional sharp normals on hard edges. Normals do not change triangle winding: reversed triangles can hide surface ribbons from one side. Check cross-product orientation against intended outward directions, meaningful thickness/caps, degenerate faces and attachments. Double-sided display is an intentional rendering choice, not a substitute for solid geometry or collision. Use colours/textures that fit the reference; avoid accidental checker shading on smooth skin.

Code runs on Studio's main thread. Yield per logical component or roughly per thousand elements rather than per vertex; parent small completed containers so the parent operation itself does not freeze the editor. Retain and time the exact submitted source before any repair.

## Native execution and persistence

Discover the current Studio ID and mode before actions; keep one mutation owner. Use the project's configured saved profile/bridge, avoiding new logins or another editor when the intended one is already available. Do not broaden permissions, install plugins or refresh all Codex connections merely to generate a mesh.

Use a geometry-free harness for execution and registration. Save its actual face/vertex counts, dimensions, Part count and timing. Preserve source and native errors rather than reporting a build that never ran. Missing native capabilities leave a clearly named source-only checkpoint.

For durability, use a verified native bake or export actual retained mesh face corners: positions, normals, RGBA and UVs; zero-based triangle indices; native Part Size, MeshSize, CFrame, colour/transparency and material. Carry the source hash, asset ID and reference-manifest hash. A supported exporter can account for `CFrame * (Size/MeshSize)` while preserving attributes. Validate the real exported file and its geometry/attribute round trip; do not recreate or cosmetically improve geometry in the exporter.

Follow the project's safe upload helper and existing authorization if a hosted mesh is needed. Preserve accepted operation IDs; reconcile an uncertain upload instead of sending it again. Reimport the durable result, verify mesh/Part counts, dimensions, palette, UVs/textures and front/back appearance. Retain the original and editable Luau even when Roblox stores a hosted mesh ID.

Save the actual local Studio file through a supported local Save route. `AssetService:SavePlaceAsync` is a cloud operation, not a local-file fallback. Verify source/mesh IDs and labels in the saved file, preserving existing content. Record whether a fresh reopen was actually checked; do not imply it from an editor preview.

## Review checks from the whale trials

- Preload actual **MeshPart Instances** in client Play. Bare mesh-ID strings produced asset-type mismatch failures even for valid control assets; collect callback statuses and assert failures outside the callback.
- A cloned SurfaceGui sign may need `Adornee` explicitly set to its own Part. Check rendered labels, not just nonempty Text properties.
- For visual comparisons, put cloned subjects at the same position with matching camera, lighting, viewport and fixed renderer quality. Keep original captures and source/condition provenance; restore settings and remove temporary objects afterwards. Follow a project's native comparison gate when available; metadata consistency is not aesthetic approval.
- Distinguish initial output, technical repair, aesthetic refinement and scene assembly. Keep each version and incremental/cumulative phase time. Do not promote an unreviewed candidate into an approved library merely because generation, upload or rendering succeeded.

Current API references: [EditableMesh](https://create.roblox.com/docs/reference/engine/classes/EditableMesh), [AssetService](https://create.roblox.com/docs/reference/engine/classes/AssetService). Check current tool schemas/docs when an API is uncertain; do not guess a substitute operation.
