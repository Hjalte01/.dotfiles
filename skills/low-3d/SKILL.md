---
name: low-3d
description: Create an editable 3D asset with Sol Low using twenty reference views, or refine an existing asset while retaining its original image and source.
---

# Low 3D

Read and follow `$CODEX_HOME/skills/reference-3d/SKILL.md` (default `~/.codex/skills/reference-3d/SKILL.md`) with mode `low`: GPT-6.1 Sol low coordinates the twenty new views and authors the editable geometry. Resolve the core from the installed skills root, not through `../` from this directory: declarative installs can symlink each skill separately. Reuse an existing sealed reference set for this source. This alias does not switch the caller's model; use the core's explicit worker selection. Do not add an Astra polish unless separately requested. If the user asks for a low/max comparison, use core mode `compare` with the same sealed set.

Choose **create** for a new reconstruction and **refine** for changes to an existing editable model. Read `references/refinement-and-retention.md` from the installed core skill root. The twenty-view process remains the default for initial creation; refinement does not automatically regenerate twenty images. Keep the original image permanently. After verified completion, release generated angles through the project's managed cleanup lifecycle, preserving editable sources, textures, exports and provenance.
