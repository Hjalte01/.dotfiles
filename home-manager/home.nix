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
    tree

    # --- hypr window-manager ---
    waybar       
    rofi

    # For your custom scripts
    jq          # Required by window_opacity.sh to parse JSON
    ydotool     # Required by auto_clicker_toggle.sh to simulate clicks
    zenity      # Required by auto_clicker_toggle.sh for the pop-up input box

    # For your app keybinds
    nautilus    # Your preferred file manager
    spotify     # Your music player
    btop        # Your system monitor
    lazydocker  # Your docker manager
    wlr-randr   # Required by your display toggle bind
    blueman     # A standard Bluetooth manager GUI (since you are missing omarchy-bluetooth)

    # For Fn-keys
    brightnessctl # briightness 
    playerctl     # 
    pavucontrol   # sound/audio
    swayosd       # brightness/audio graphics



    # --- Nvim nix packages instead of Mason ---
    vscode-langservers-extracted 
    python311Packages.flake8  # Adds flake8 to your PATH correctly
    vtsls
    pyright
    stylua
    shfmt
    shellcheck
    lua-language-server
    jdt-language-server
  ];  

  # ==========================================
  # SYMLINKING DOTFILES
  # Notice the ../ to go up one directory!
  # ==========================================
  home.file = {
    # Neovim
    ".config/nvim" = {
      source = ../nvim/.config/nvim;
      recursive = true;
    };

    # Waybar
    ".config/waybar" = {
      source = ../waybar/.config/waybar;
      recursive = true;
    };

    # Tmux
    ".tmux.conf".source = ../tmux/.tmux.conf;

    # Bash
    ".mybashrc.sh".source = ../bash/.mybashrc.sh;

    # hyprland
    ".config/hypr/hyprland.conf".source = ../hypr/hyprland.conf;

    # Rofi
    ".config/rofi/config.rasi".source = ../rofi/config.rasi;
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

  # Enforce a global cursor theme to fix sizing/shape issues
  home.pointerCursor = {
    gtk.enable = true;
    x11.enable = true;
    name = "Adwaita";
    package = pkgs.adwaita-icon-theme;
    size = 24;
  };

  # Let Home Manager install and manage itself.
  programs.home-manager.enable = true;

  # Don't change this without reading the Home Manager release notes!
  home.stateVersion = "23.11"; 
}
