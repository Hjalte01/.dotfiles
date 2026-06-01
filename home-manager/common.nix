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
    tmux
    tree
    unzip
    wget
    zsh
    zoxide
  ];

  home.file = {
    ".config/nvim" = {
      source = ../nvim/.config/nvim;
      recursive = true;
    };

    ".tmux.conf".source = ../tmux/.tmux.conf;
    ".bash_common.sh".source = ../bash/common.sh;

    ".local/bin/gai" = {
      source = ../scripts/gai;
      executable = true;
    };

    ".config/lazygit/config.yml".text = ''
      customCommands:
        - key: "<c-c>"
          context: "global"
          description: "Generate AI commit message"
          command: "zsh -ic 'gai'"
          loadingText: "Generating AI commit message..."
          output: terminal
    '';

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
