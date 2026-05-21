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
    curl
    fd
    fzf
    gcc
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
    tmux
    tree
    unzip
    wget
    zoxide
  ];

  home.file = {
    ".config/nvim" = {
      source = ../nvim/.config/nvim;
      recursive = true;
    };

    ".tmux.conf".source = ../tmux/.tmux.conf;

    ".npmrc".text = ''
      prefix=${config.home.homeDirectory}/.local
    '';
  };

  programs.bash = {
    enable = true;
    initExtra = ''
      set -o vi

      export EDITOR="nvim"
      export VISUAL="nvim"
      export MANPAGER='nvim +Man!'
      export PATH="$HOME/.local/bin:$PATH"

      alias ll='ls -alF'
      alias la='ls -A'
      alias l='ls -CF'
      alias cl='clear'
      alias dots='cd ~/.dotfiles'
      alias cx='codex'
      alias ta='tmux new-session -A -s main'

      if command -v zoxide >/dev/null 2>&1; then
        eval "$(zoxide init bash --cmd cd)"
        alias zz='zi'
      fi
    '';
  };

  programs.home-manager.enable = true;

  home.stateVersion = "23.11";
}
