{ config, pkgs, ... }:

{
  home.username = "hjalte"; 
  home.homeDirectory = "/home/hjalte"; 

  # Packages you want installed just for your user
  home.packages = with pkgs; [
    neovim
    git
    ripgrep      # LazyVim needs this
    fd           # LazyVim needs this
    gcc          # Needed for Treesitter
    wl-clipboard # Clipboard support

    ghostty      # Terminal
    tree-sitter  # Nvim needs it
    nodejs_22    # required by mason
    unzip        # required by mason
    curl
    wget
  ];

  # ==========================================
  # SYMLINKING DOTFILES
  # Notice the ../ to go up one directory!
  # ==========================================
  home.file = {
    # 1. Neovim
    ".config/nvim" = {
      source = ../nvim/.config/nvim;
      recursive = true;
    };

    # 2. Waybar
    ".config/waybar" = {
      source = ../waybar/.config/waybar;
      recursive = true;
    };

    # 3. Tmux
    ".tmux.conf".source = ../tmux/.tmux.conf;

    # 4. Bash
    ".mybashrc.sh".source = ../bash/.mybashrc.sh;
  };

  # ==========================================
  # NATIVE BASH CONFIGURATION
  # ==========================================
  programs.bash = {
    enable = true;
    initExtra = ''
      # Load custom Omarchy configuration
      if [ -f ~/.mybashrc.sh ]; then
        source ~/.mybashrc.sh
      fi
    '';
  };

  # Let Home Manager install and manage itself.
  programs.home-manager.enable = true;

  # Don't change this without reading the Home Manager release notes!
  home.stateVersion = "23.11"; 
}
