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
    imv          # billedeviser til wayland
    mpv          # videoafspilere
    zathura      # PDF/document viewer
    libnotify    # beskeder om ting virker?
    mako         # notification daemon for notify-send popups on Wayland
    yt-dlp       # Download youtube vid
    ffmpeg       # Handle the downloade video

    steam-run    # Run games in Nix
    unrar        # unzip rar files
    
    wineWow64Packages.stable
    winetricks

    tor-browser

    ghostty      # Terminal
    tree-sitter  # Nvim needs it
    nodejs_22    # required by mason
    unzip        # required by mason
    curl
    wget
    unzip
    fzf
    zoxide      # Smart/frecency directory jumping
    xdg-utils   # Provides xdg-open for the open alias
    
    glow
    tree
    bubblewrap    # required by codex AI for secure code sandboxing
    man-pages     # C library/API man pages, e.g. man 3 printf
    man-pages-posix

    # --- hypr window-manager ---
    waybar       
    rofi

    # For your custom scripts
    jq          # Required by window_opacity.sh to parse JSON
    ydotool     # Wayland input helper for the autoclicker

    # For your app keybinds
    nautilus    # Your preferred file manager
    spotify     # Your music player
    btop        # Your system monitor
    lazygit     # Your git manager
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
    glibc.dev   # The core C standard library headers (<stdio.h>, <stdlib.h>)

    clang-tools
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

    # 4. Mako notifications
    ".config/mako/config".source = makeLink "mako/config" ../mako/config;

    # 5. Custom scripts
    ".local/bin/custom-keybinds" = {
      source = makeLink "scripts/custom-keybinds" ../scripts/custom-keybinds;
      executable = true;
    };

    ".local/bin/autoclicker" = {
      source = makeLink "scripts/autoclicker" ../scripts/autoclicker;
      executable = true;
    };

    ".local/bin/math-ocr" = {
      source = makeLink "scripts/math-ocr" ../scripts/math-ocr;
      executable = true;
    };

    ".local/bin/notification-popups" = {
      source = makeLink "scripts/notification-popups" ../scripts/notification-popups;
      executable = true;
    };

    # 6. Tmux (Single File)
    ".tmux.conf".source = makeLink "tmux/.tmux.conf" ../tmux/.tmux.conf;

    # 7. Bash (Single File)
    ".mybashrc.sh".source = makeLink "bash/.mybashrc.sh" ../bash/.mybashrc.sh;

    # 8. Hyprland (Single File)
    ".config/hypr/hyprland.conf".source = makeLink "hypr/hyprland.conf" ../hypr/hyprland.conf;

    # 9. Waybar Dev Badge Trigger
    ".cache/dev-mode-status".text = if devMode then "[ DEV ]" else "";
      
    # Ghostty (Directory - needs recursive)
    ".config/ghostty" = {
      source = makeLink "ghostty/.config/ghostty" ../ghostty/.config/ghostty;
      recursive = true;
    };

    # Zathura
    ".config/zathura/zathurarc".source = makeLink "zathura/zathurarc" ../zathura/zathurarc;

  };

  systemd.user.services.waybar = {
    Unit = {
      Description = "Waybar status bar";
      PartOf = [ "graphical-session.target" ];
      After = [ "graphical-session.target" ];
    };

    Service = {
      ExecStart = "${pkgs.waybar}/bin/waybar";
      Restart = "always";
      RestartSec = 2;
    };
  };

  # ==========================================
  # AUTOMATED IMPERATIVE SETUP
  # ==========================================
  home.activation = {
    setupPix2TexVenv = config.lib.dag.entryAfter ["writeBoundary"] ''
      VENV_PATH="$HOME/.local/share/pix2tex-venv"
      if [ ! -d "$VENV_PATH" ]; then
        # Bypass systemd silencing by broadcasting directly to your terminal
        ${pkgs.util-linux}/bin/wall "🤖 Home Manager: Downloading PyTorch for Math OCR. This takes 1-3 minutes. Do not cancel..."

        run ${pkgs.python3}/bin/python3 -m venv "$VENV_PATH"
        run "$VENV_PATH/bin/pip" install "pix2tex[gui]"

        ${pkgs.util-linux}/bin/wall "✅ Math OCR Python environment built successfully!"
      fi
    '';
  };




  xdg.mimeApps = {
    enable = true;
    defaultApplications = {
      "image/png" = [ "imv.desktop" ];
      "image/jpeg" = [ "imv.desktop" ];
      "image/gif" = [ "imv.desktop" ];
      "video/mp4" = [ "mpv.desktop" ];
      "video/webm" = [ "mpv.desktop" ];
      "video/x-matroska" = [ "mpv.desktop" ];
      "application/pdf" = [ "firefox.desktop" ]; # Eksempel: Åbn PDF i Firefox
    };
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
