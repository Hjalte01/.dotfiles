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

      if [ -x /usr/bin/dircolors ]; then
        test -r ~/.dircolors && eval "$(dircolors -b ~/.dircolors)" || eval "$(dircolors -b)"
        alias ls='ls --color=auto'
        alias grep='grep --color=auto'
        alias fgrep='fgrep --color=auto'
        alias egrep='egrep --color=auto'
      fi

      alias ll='ls -alF'
      alias la='ls -A'
      alias l='ls -CF'
      alias cl='clear'
      alias python='python3'
      alias dots='cd ~/.dotfiles'
      alias cd.='cd ~/.dotfiles'
      alias brc='nvim ~/.dotfiles/bash/.mybashrc.sh'
      alias home='nvim ~/.dotfiles/home-manager/home.nix'
      alias flake='nvim ~/.dotfiles/flake.nix'
      alias cx='codex'
      alias ta='tmux new-session -A -s main'

      alias_str=".."
      cmd_str="cd .."
      for i in $(seq 1 10); do
        alias ''${alias_str}="$cmd_str"
        alias_str="$alias_str."
        cmd_str="$cmd_str/.."
      done

      cmdc() {
        if [ "$#" -eq 0 ]; then
          printf 'Usage: cmdc "command to run"\n'
          return 2
        fi

        local cmd tmp status
        tmp="$(mktemp)" || return 1

        if [ "$#" -eq 1 ]; then
          cmd="$1"
        else
          printf -v cmd '%q ' "$@"
          cmd="''${cmd% }"
        fi

        printf '$ %s\n' "$cmd" | tee "$tmp"
        eval "$cmd" 2>&1 | tee -a "$tmp"
        status="''${PIPESTATUS[0]}"

        if command -v wl-copy >/dev/null 2>&1 && wl-copy <"$tmp"; then
          printf 'Copied command and output to clipboard'
          if [ "$status" -ne 0 ]; then
            printf ' (exit %s)' "$status"
          fi
          printf '.\n'
        else
          printf 'Command output saved in %s; clipboard copy unavailable in this shell.\n' "$tmp" >&2
          return "$status"
        fi

        rm -f "$tmp"
        return "$status"
      }

      tldrf() {
        curl -Gs "https://www.mankier.com/api/explain/?cols=$(tput cols)" --data-urlencode "q=$*"
      }

      cdd() {
        local dir
        local find_cmd="find . -maxdepth 4 -type d -not -path '*/.*'"

        if command -v fd >/dev/null 2>&1; then
          find_cmd="fd . $HOME --type d --hidden --exclude .git"
        elif command -v fdfind >/dev/null 2>&1; then
          find_cmd="fdfind . $HOME --type d --hidden --exclude .git"
        fi

        dir=$(eval "$find_cmd" | fzf --preview 'tree -a -L 1 {}' --preview-window=right:50%) || return

        if [ -n "$dir" ]; then
          cd "$dir"
        fi
      }

      if command -v zoxide >/dev/null 2>&1; then
        eval "$(zoxide init bash --cmd cd)"
        alias zz='zi'
      fi
    '';
  };

  programs.home-manager.enable = true;

  home.stateVersion = "23.11";
}
