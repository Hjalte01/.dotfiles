{ config, pkgs, ... }:


let
  # ⚠️ THE MASTER SWITCH ⚠️
  devMode = false;

  # Helper function to automatically pick the right link type
  makeLink = stringPath: nixPath:
    if devMode 
    then config.lib.file.mkOutOfStoreSymlink "${config.home.homeDirectory}/.dotfiles/${stringPath}"
    else nixPath;
in
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

    grim          # takes the picture 
    slurp         # Drags the captured picture



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
  # ==========================================
  home.file = {
    # 1. Neovim (Directory - needs recursive)
    ".config/nvim" = {
      source = makeLink "nvim/.config/nvim" ../nvim/.config/nvim;
      recursive = true;
    };

    # 2. Waybar (Directory - needs recursive)
    ".config/waybar" = {
      source = makeLink "waybar/.config/waybar" ../waybar/.config/waybar;
      recursive = true;
    };

    # 3. Rofi (Single File)
    ".config/rofi/config.rasi".source = makeLink "rofi/config.rasi" ../rofi/config.rasi;

    # 4. Tmux (Single File)
    ".tmux.conf".source = makeLink "tmux/.tmux.conf" ../tmux/.tmux.conf;

    # 5. Bash (Single File)
    ".mybashrc.sh".source = makeLink "bash/.mybashrc.sh" ../bash/.mybashrc.sh;

    # 6. Hyprland (Single File)
    ".config/hypr/hyprland.conf".source = makeLink "hypr/hyprland.conf" ../hypr/hyprland.conf;

    # 7. Waybar Dev Badge Trigger
    ".cache/dev-mode-status".text = if devMode then "[ DEV ]" else "";
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
