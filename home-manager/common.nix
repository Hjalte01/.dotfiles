{
  config,
  pkgs,
  ...
}: let
  codex = pkgs.callPackage ../pkgs/codex-cli.nix {};
in {
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
  };

  home.packages = with pkgs; [
    alejandra
    btop
    bubblewrap
    codex
    cppman
    curl
    delta
    difftastic
    fd
    fzf
    gcc
    gh
    git
    glow
    jq
    lazygit
    neovim
    nh
    nix-output-monitor
    nixd
    nodejs_22
    ripgrep
    shellcheck
    shfmt
    sqlite
    tmux
    tree
    unzip
    wget
    zsh
    zotero
    zoxide
  ];

  home.file = {
    ".codex/AGENTS.md".text = ''
      # Default Codex Context

      - The system is NixOS managed from `/home/hjalte/.dotfiles`.
      - Prefer reproducible, declarative NixOS/Home Manager changes over manual setup.
      - Shared configuration should live as high as practical in the shared/general profile, especially in `home-manager/common.nix`, so both the main PC and mobile VPS can reuse it.
      - Host-specific changes should stay in the relevant PC or mobile VPS modules.
      - Manual fixes are acceptable only when a declarative solution is not practical yet; when possible, leave the work in a state that can be made reproducible later.
      - After changing NixOS, Home Manager, Neovim, shell, Hyprland, or other dotfiles that are activated through the flake, run `nxb` before finishing so the live system matches the repository. If the user explicitly says not to run `nxb` or gives a conflicting instruction, follow the user's latest explicit instruction instead.

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

    ".local/bin/gai" = {
      source = ../scripts/gai;
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

  programs.home-manager.enable = true;

  home.stateVersion = "23.11";
}
