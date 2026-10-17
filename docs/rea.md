# REA

REA (Reverse Engineer Anything) is pinned in `pkgs/rea-agents.nix` and installed
through `home-manager/common.nix` on both hosts. Its runtime dependencies are
locked in `pkgs/rea-agents/package-lock.json`. Native Node modules are patched
for NixOS during the build.

Home Manager activation registers REA's Node MCP entry point in the writable Codex config and
installs the matching workflow skill in
`~/.agents/skills/reverse-engineer-anything`. Existing Codex settings are
preserved; the first changed configuration is backed up as
`~/.codex/config.toml.before-nix-rea`.

Restart Codex after activation to load the server and skill. Check the install:

```sh
rea --version
rea doctor --client codex --json
rea mcp doctor --json
```

JavaScript/Electron static analysis and browser inspection do not require a
native decompiler. Native binary analysis requires a separately configured
compatible Ghidra, Hopper, or IDA installation. No native analysis provider is
installed by this module.

Update REA declaratively rather than using `rea update`: change the version and
archive hash, regenerate the runtime lock from the published package after
removing `devDependencies` and `scripts` from its package manifest, and update
`npmDepsHash`. Build, run the diagnostics, then run `nxb`.

Upstream: <https://rea.tools/get-started/> and <https://github.com/morluto/rea>.
