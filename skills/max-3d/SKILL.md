---
name: max-3d
description: Create an editable 3D asset with Astra Max using the same Sol Low twenty-view reference set as low-3d.
---

# Max 3D

Read and follow `$CODEX_HOME/skills/reference-3d/SKILL.md` (default `~/.codex/skills/reference-3d/SKILL.md`) with mode `max`: GPT-6.1 Sol low coordinates the twenty new views; GPT-6 Astra max authors the editable geometry. Resolve the core from the installed skills root, not through `../` from this directory: declarative installs can symlink each skill separately. Reuse an existing sealed reference set for this source. This alias does not switch the caller's model; use the core's explicit worker selection. If the user asks for a low/max comparison, use core mode `compare` with the same sealed set.
