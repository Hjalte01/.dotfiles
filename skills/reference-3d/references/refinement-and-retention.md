# Refinement and reference retention

## Create a new model

Use the original approved image plus twenty individually generated, inspected and sealed camera views. Reuse a byte-verified active set for the same original when available. A released set is not a reusable cache: regenerate twenty views for a new reconstruction rather than weakening verification or passing missing files. Keep the pinned helper version and in-flight job contracts unchanged.

## Refine an existing model

Start from the exact selected editable source and its original image, with existing textures, rig, materials and review notes. Record the input revision/hashes and save a new derivative; preserve the selected baseline and frozen experiment evidence. Use the requested model mode explicitly. Low remains Sol Low without an automatic Astra pass.

Change only the requested details while checking identity, silhouette, palette, attachments and intended function. Existing angles may help if retained, but ordinary geometry, texture, rig or animation edits do not require another twenty-image batch. If the saved model cannot support the change and a reconstruction is needed, explain that distinction and use the create workflow. Synthetic angles infer unseen surfaces; the original remains the identity anchor.

Keep editable source, texture masters/maps, a validated export, matching previews, revision/provenance and worker receipts. For textured or skinned assets, use a compatible toolchain and a small native import check before a full build; the static material-colour pilot adapter rejects textures and skinning. Check UVs, weights, deformation seams and native texture loading. Surface maps and rigs are retained production inputs, not disposable camera images.

## Release generated camera images

The default for completed VPS Asset Studio jobs is to retain the original image and editable model, textures, exports, previews, prompts, manifests, hashes and receipts, while releasing the twenty generated camera binaries and their redundant working copies. This saves storage, not generation usage already spent. A later full reconstruction can regenerate views.

Use the project's managed retention controller, not a broad delete command. Before deletion it must verify the durable original and required finished artifacts; protect all unfinished, interrupted or retryable consumers and frozen comparisons. Shared cache acquisition, publication and cleanup must coordinate through the same lifecycle lock. Move released metadata out of the active cache namespace so strict byte verification remains meaningful.

Delete only inventoried regular files with verified paths, hashes, sizes and ownership. Native image outputs require producer/consumer provenance; preserve and report unproven historical outputs. Never remove an original reference, a texture, or another job's input because it shares a directory or filename pattern. Cleanup must resume safely after interruption and report actual recovered bytes without converting a completed model into a failed generation job.

If the host/project lacks this lifecycle, preserve the files and report the missing cleanup capability rather than applying an ad hoc purge. Older completed jobs can be audited by the same controller. Do not extend a VPS cleanup request to frozen PC experiments.
