---
name: med-3d
description: Create or refine Roblox assets with Sol Ultra and twenty-view Luau EditableMesh; the default middle tier for new 3D requests.
---

# Med 3D

Read and follow `$CODEX_HOME/skills/reference-3d/SKILL.md` (default `~/.codex/skills/reference-3d/SKILL.md`) with mode `med`: **GPT-6.1 Sol with ultra reasoning** authors the geometry.

This is the user's usual choice for new 3D skill requests when no other tier is specified.

Use the shared M03-T route: Sol Low coordinates the twenty reference views, then the selected geometry worker authors actual Luau EditableMesh source. Resolve the core from the installed skills root, not `../`: declarative installs can link each skill separately. This alias does not switch the caller's model; follow the core's explicit worker selection.

The core governs sealed-set reuse, original/source retention, create versus refine, native execution and verification, and existing pinned job contracts. Use its comparison mode only when a comparison is requested; do not add an automatic polishing pass with another tier.
