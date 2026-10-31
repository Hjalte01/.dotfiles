{
  config,
  lib,
  osConfig ? {},
  pkgs,
  ...
}: let
  codex = pkgs.callPackage ../pkgs/codex-cli.nix {};
  hendrix = pkgs.callPackage ../pkgs/hendrix.nix {};
  devices = pkgs.callPackage ../pkgs/devices.nix {};
  canvas-lms-mcp = pkgs.callPackage ../pkgs/canvas-lms-mcp.nix {};
  filepick = pkgs.callPackage ../pkgs/filepick.nix {};
  pdfpick = pkgs.callPackage ../pkgs/pdfpick.nix {};
  dictation = pkgs.callPackage ../pkgs/dictation.nix {};
  rea = pkgs.callPackage ../pkgs/rea-agents.nix {};
  codexConfigPython = pkgs.python3.withPackages (p: [p.tomlkit]);
  hostName = osConfig.networking.hostName or "unknown";
  flakeTarget =
    if hostName == "mobile-dev"
    then "mobile-dev"
    else "nixos";
  nixosConfig =
    if hostName == "mobile-dev"
    then "nixos/mobile-dev.nix"
    else "nixos/configuration.nix";
  homeManagerConfig =
    if hostName == "mobile-dev"
    then "home-manager/mobile-dev.nix"
    else "home-manager/home.nix";
  hostContext =
    if hostName == "mobile-dev"
    then ''
      ## This Host

      - This machine is the `mobile-dev` VPS, intended for phone-driven remote Codex work.
      - Its NixOS configuration is `nixos/mobile-dev.nix` and its flake target is `mobile-dev`.
      - Keep VPS-specific system and Home Manager changes in the mobile-dev modules.
      - After completing and verifying a task in any Git repository on this VPS, commit its owned changes and push the current branch to its configured upstream automatically. When Codex Queue owns the run, leave pull/commit/push to its Git lifecycle. Preserve partial or unrelated edits and report blocked synchronization instead of forcing it.
    ''
    else ''
      ## This Host

      - This machine is the main PC (`${hostName}`), not the mobile VPS.
      - Its NixOS configuration is `nixos/configuration.nix` and its flake target is `nixos`.
      - Keep desktop-specific system and Home Manager changes in the desktop modules.
      - On this main PC, automatic task-completion commit/push is enabled only for `/home/hjalte/Documents/other/side_projects/roblox_gamemodes` and that repository's worktrees (Git remote `Hjalte01/roblox-gamemodes`). Other PC repositories keep their existing push behavior; do not automatically commit/push them unless explicitly requested. In the Roblox repository, publish only completed, verified, owned work once no other task is editing the checkout.
    '';
in {
  imports = [./themes.nix ./reference-3d.nix];

  home.username = "hjalte";
  home.homeDirectory = "/home/hjalte";

  home.sessionPath = [
    "$HOME/.local/bin"
  ];

  home.sessionVariables = {
    EDITOR = "nvim";
    VISUAL = "nvim";
    MANPAGER = "nvim +Man!";
    NPM_CONFIG_PREFIX = "${config.home.homeDirectory}/.local";
    DOTFILES_FLAKE_TARGET = flakeTarget;
    DOTFILES_NIXOS_CONFIG = "${config.home.homeDirectory}/.dotfiles/${nixosConfig}";
    DOTFILES_HOME_MANAGER_CONFIG = "${config.home.homeDirectory}/.dotfiles/${homeManagerConfig}";
  };

  xdg.configFile."dictation/terms.tsv".source = ../pkgs/dictation/terms.tsv;

  # Scenario Lab profiles inherit the user's login and selected model.
  # Profile files are shared; Studio itself remains desktop-only.
  home.file.".codex/scenario-lab.config.toml".text = ''
    approval_policy = "never"
    sandbox_mode = "workspace-write"
    web_search = "live"
    [sandbox_workspace_write]
    network_access = true
  '';
  home.file.".codex/scenario-lab-qwen.config.toml".text = ''
    approval_policy = "never"
    sandbox_mode = "workspace-write"
    [sandbox_workspace_write]
    network_access = true
  '';


  # Codex updates its own writable config. Manage this preference without
  # replacing the file or importing account-specific settings into the store.
  home.activation.codexCompactStatusLine = lib.hm.dag.entryAfter ["writeBoundary"] ''
    run ${codexConfigPython}/bin/python3 ${../scripts/codex-status-line.py}
  '';

  home.activation.codexReasoningDefaults = lib.hm.dag.entryAfter ["codexCompactStatusLine"] ''
    run ${codexConfigPython}/bin/python3 - <<'PY'
    import os
    from pathlib import Path
    import shutil

    import tomlkit

    path = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "config.toml"
    previous = path.read_text() if path.exists() else ""
    document = tomlkit.parse(previous)
    document.setdefault("model", "gpt-6.1-sol")
    document["model_reasoning_effort"] = "ultra"
    document["plan_mode_reasoning_effort"] = "ultra"
    updated = tomlkit.dumps(document)
    if updated != previous:
        path.parent.mkdir(parents=True, exist_ok=True)
        backup = path.with_name("config.toml.before-ultra-defaults")
        if path.exists() and not backup.exists():
            shutil.copy2(path, backup)
        path.write_text(updated)
    PY
  '';

  home.activation.codexRea = lib.hm.dag.entryAfter ["codexReasoningDefaults"] ''
    run ${codexConfigPython}/bin/python3 ${../scripts/codex-rea.py} ${rea} ${pkgs.nodejs_22}/bin/node
  '';

  home.packages = with pkgs; [
    (writeShellScriptBin "c" ''
      source ${../bash/clipboard.sh}
      c "$@"
    '')
    alejandra
    btop
    bubblewrap
    canvas-lms-mcp
    hendrix
    codex
    cppman
    curl
    delta
    difftastic
    devices
    dictation
    fd
    fastfetch
    filepick
    pdfpick
    fzf
    gcc
    gh
    git
    git-lfs
    glow
    jq
    lazygit
    neovim
    nh
    nix-output-monitor
    nixd
    nodejs_22
    pandoc # Markdown PDF preview in Neovim
    ripgrep
    repomix
    rea
    shellcheck
    shfmt
    sqlite
    tmux
    tree
    tree-sitter # Nvim needs it
    typst # Fast PDF engine for Pandoc
    unzip
    usbutils
    wget
    zsh
    zotero
    zoxide
  ];

  home.file = {
    ".config/pdfpick/roots".text = ''
      # PDF search roots, relative to home or absolute. "." searches home.
      .
    '';

    ".config/filepick/roots".text = ''
      # Personal search roots, relative to home (absolute paths also work).
      Downloads
      Desktop
      Documents
      Pictures
      Videos
      Music
      Public
      Templates
      Projects
      projects
      src
      .dotfiles
      Zotero/storage
    '';

    ".config/filepick/ignore".text = ''
      # Extra gitignore-style exclusions for filepick. --all bypasses these.
      # Project .gitignore, .ignore, and .filepick-ignore files are also respected.
      **/wandb/
      **/lightning_logs/
      **/checkpoints/
      **/tensorboard/
      **/.ipynb_checkpoints/
    '';

    ".bash_host_metadata.sh".text = ''
      # Generated by Home Manager. Sourced by the shared Bash configuration so
      # long-lived shells can refresh host-specific paths after a rebuild.
      export DOTFILES_FLAKE_TARGET=${flakeTarget}
      export DOTFILES_NIXOS_CONFIG=${config.home.homeDirectory}/.dotfiles/${nixosConfig}
      export DOTFILES_HOME_MANAGER_CONFIG=${config.home.homeDirectory}/.dotfiles/${homeManagerConfig}
    '';

    ".codex/AGENTS.md".text = ''
      # Default Codex Context

      - The system is NixOS managed from `/home/hjalte/.dotfiles`.
      - Prefer reproducible, declarative NixOS/Home Manager changes over manual setup.
      - Shared configuration should live as high as practical in the shared/general profile, especially in `home-manager/common.nix`, so both the main PC and mobile VPS can reuse it.
      - Host-specific changes should stay in the relevant PC or mobile VPS modules.
      - Manual fixes are acceptable only when a declarative solution is not practical yet; when possible, leave the work in a state that can be made reproducible later.
      - After changing NixOS, Home Manager, Neovim, shell, Hyprland, or other dotfiles that are activated through the flake, run `nxb` before finishing so the live system matches the repository. If the user explicitly says not to run `nxb` or gives a conflicting instruction, follow the user's latest explicit instruction instead.

      ## Git synchronization

      - Before editing or testing in a Git repository, inspect its branch/upstream, tracked and untracked changes, unfinished Git operations and other active tasks using the checkout. Repeat after work may have arrived from another device.
      - If the checkout is clean and idle, fetch the configured upstream with a bounded timeout and automatically pull available fast-forward updates using `git pull --ff-only --no-rebase --no-autostash`. Re-read instructions and relevant files after updating. An up-to-date or purely ahead branch needs no pull.
      - Preserve dirty or concurrently used checkouts. Never stash, discard, reset, force-push, rebase, switch branches or auto-commit unrelated work to enable synchronization. Report a missing/ambiguous upstream, divergence or a network failure accurately.
      - Automatic completion commit/push follows the host-specific scope below. Commit only the completed task's files after verification; never use blanket staging in a shared dirty checkout. Use a normal non-force push to the current branch's configured upstream and verify its remote commit. Retain local work and report a rejected/failed push. A failed or cancelled task does not authorize publishing partial work.
      - When a queue or controller owns Git operations, respect its locks and lifecycle; do not race a second pull or push from inside the model task.

      ## Progress and Waiting

      - Before starting work that may take more than about 30 seconds, briefly explain what you are doing and give a rough expected wait when you can estimate it. State uncertainty instead of inventing an ETA.
      - During ongoing work, send a concise, meaningful progress update at least every 60 seconds when the tools allow. Explain what has completed, what is happening now, and what remains. Do not leave the user with only a generic "working" indicator.
      - If a command, connection, queue, or external service stalls, promptly say what you are waiting on, whether progress is still being observed, and when you will retry or time out. Distinguish active work from waiting and being blocked.
      - Prefer bounded command timeouts and short polling intervals so you can keep the user informed. If a tool cannot yield updates while running, warn the user before starting it and describe the expected silence.
      - For longer tasks, use a short checklist or completed/total counts when useful. Only show percentages or progress bars when they reflect measured progress; do not invent them.
      - Apply these communication preferences across all projects and tasks, including SSH, cluster jobs, builds, tests, and research.

      ${hostContext}

      ## Device Inventory and Job Placement

      - `devices --json` shows the shared device inventory, measured Linux specs, sources and snapshot times. The inventory is `~/.dotfiles/data/devices.json`; `devices path` prints the active path if overridden.
      - Before choosing the main PC or VPS for a job, run `devices refresh all` (or the relevant device ID), then `devices check --ram GIB --cpus N --disk GIB` with the job's needs. Add `--cuda` or `--arch x86_64` when required. These commands inspect resources; they do not start jobs.
      - CPU slots and RAM describe capacity, not universal performance scores. `devices bench ID` is an optional brief synthetic CPU workload, run only when performance measurement is useful. Check software support and GPU VRAM separately.
      - The iPad model remains unconfirmed. Apple mobile devices are clients in this inventory; do not treat them as Linux execution hosts.

      ## Shared Context Locations

      - `/home/hjalte/Pictures/Screenshots` is a common place to check for recent images or screenshots.
      - `/home/hjalte/Documents/Codex-Inbox` is used for sharing captures and images with Codex.
      - In `Codex-Inbox`, prefer active context only: read `ACTIVE/`, `ACTIVE_CONTEXT.txt`, or files named with `ACTIVE` unless the user asks for older context.
      - If the user refers to a recent screenshot or capture without a precise filename, check file dates and active inbox markers before asking for clarification.
    '';

    ".config/nvim" = {
      source = ../nvim/.config/nvim;
      recursive = true;
    };

    ".config/cppman/cppman.cfg".text = ''
      [Settings]
      source = cppreference.com
      updatemanpath = false
      pager = nvim
    '';

    ".tmux.conf".source = ../tmux/.tmux.conf;
    ".bash_common.sh".source = ../bash/common.sh;
    ".bash_clipboard.sh".source = ../bash/clipboard.sh;

    ".local/bin/gai" = {
      source = ../scripts/gai;
      executable = true;
    };

    ".local/bin/update-codex" = {
      source = ../scripts/update-codex;
      executable = true;
    };

    ".local/bin/absalon-mcp" = {
      source = pkgs.replaceVars ../scripts/absalon-mcp {
        inherit canvas-lms-mcp;
      };
      executable = true;
    };

    ".config/lazygit/config.yml" = {
      force = true;
      text = ''
        customCommands:
          - key: "<c-c>"
            context: "global"
            description: "Generate AI commit message"
            command: "GAI_EXIT_LAZYGIT_IF_CLEAN=1 bash -ic 'gai'"
            loadingText: "Generating AI commit message..."
            output: terminal
      '';
    };

    ".npmrc".text = ''
      prefix=${config.home.homeDirectory}/.local
    '';
  };

  programs.bash = {
    enable = true;
    initExtra = ''
      if [ -f ~/.bash_common.sh ]; then
        source ~/.bash_common.sh
      fi
    '';
  };

  programs.direnv = {
    enable = true;
    nix-direnv.enable = true;
  };

  programs.home-manager.enable = true;

  systemd.user.services.filepick-index = {
    Unit.Description = "Refresh the cached personal file index";
    Service = {
      Type = "oneshot";
      ExecStart = "${filepick}/bin/filepick --index";
      Nice = 10;
      IOSchedulingClass = "idle";
    };
  };

  systemd.user.timers.filepick-index = {
    Unit.Description = "Keep personal file search ready to open";
    Timer = {
      OnStartupSec = "30s";
      OnUnitInactiveSec = "2min";
      AccuracySec = "15s";
    };
    Install.WantedBy = ["timers.target"];
  };

  home.stateVersion = "23.11";
}
