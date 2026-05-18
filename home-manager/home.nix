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
    stdenv.cc.cc.lib # Runtime libstdc++ for Python ML wheels
    zlib         # Runtime zlib for Python ML wheels
    wl-clipboard # Clipboard support
    cliphist     # Clipboard history
    imv          # billedeviser til wayland
    mpv          # videoafspilere
    zathura      # PDF/document viewer
    libnotify    # beskeder om ting virker?
    mako         # notification daemon for notify-send popups on Wayland
    yt-dlp       # Download youtube vid
    ffmpeg       # Handle the downloade video

    steam-run    # Run games in Nix
    ouch         # Extract archives from Nautilus
    unrar        # unzip rar files
    
    wineWow64Packages.stable
    winetricks

    tor-browser

    ghostty      # Terminal
    tree-sitter  # Nvim needs it
    python311      # Runtime for pix2tex venv used by math-ocr
    nodejs_22    # required by mason
    unzip        # required by mason
    curl
    wget
    unzip
    fzf
    zoxide      # Smart/frecency directory jumping
    xdg-utils   # Provides xdg-open for the open alias
    nh           # Friendly NixOS/Home Manager rebuild wrapper
    nix-output-monitor # Readable Nix build output
    alejandra    # Nix formatter
    nixd         # Nix language server
    
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
    wlr-randr   # Useful for manual display checks
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

    ".local/bin/rofi-menu" = {
      source = makeLink "scripts/rofi-menu" ../scripts/rofi-menu;
      executable = true;
    };

    ".local/bin/desktop-reload" = {
      source = makeLink "scripts/desktop-reload" ../scripts/desktop-reload;
      executable = true;
    };

    ".local/bin/battery-alert" = {
      source = makeLink "scripts/battery-alert" ../scripts/battery-alert;
      executable = true;
    };

    ".local/bin/waybar-toggle" = {
      source = makeLink "scripts/waybar-toggle" ../scripts/waybar-toggle;
      executable = true;
    };

    ".local/bin/display-menu" = {
      source = makeLink "scripts/display-menu" ../scripts/display-menu;
      executable = true;
    };

    ".local/bin/system-menu" = {
      source = makeLink "scripts/system-menu" ../scripts/system-menu;
      executable = true;
    };

    ".local/bin/autoclicker" = {
      source = makeLink "scripts/autoclicker" ../scripts/autoclicker;
      executable = true;
    };

    ".local/bin/autoscroll" = {
      source = makeLink "scripts/autoscroll" ../scripts/autoscroll;
      executable = true;
    };

    ".local/bin/math-ocr" = {
      source = makeLink "scripts/math-ocr" ../scripts/math-ocr;
      executable = true;
    };

    ".local/share/math-ocr/env".text = ''
      export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.zlib}/lib:''${LD_LIBRARY_PATH:-}"
    '';

    ".local/bin/notification-popups" = {
      source = makeLink "scripts/notification-popups" ../scripts/notification-popups;
      executable = true;
    };

    ".local/bin/clipboard-history" = {
      source = makeLink "scripts/clipboard-history" ../scripts/clipboard-history;
      executable = true;
    };

    ".local/bin/notification-history" = {
      source = makeLink "scripts/notification-history" ../scripts/notification-history;
      executable = true;
    };

    ".local/bin/extract-archive" = {
      source = makeLink "scripts/extract-archive" ../scripts/extract-archive;
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

  systemd.user.services.battery-alert = {
    Unit = {
      Description = "Battery threshold notifications";
      PartOf = [ "graphical-session.target" ];
      After = [ "graphical-session.target" ];
    };

    Service = {
      ExecStart = "%h/.local/bin/battery-alert";
      Restart = "always";
      RestartSec = 2;
    };

    Install.WantedBy = [ "graphical-session.target" ];
  };

  systemd.user.services.cliphist-text = {
    Unit = {
      Description = "Clipboard history watcher for text";
      PartOf = [ "graphical-session.target" ];
      After = [ "graphical-session.target" ];
    };

    Service = {
      ExecStart = "${pkgs.wl-clipboard}/bin/wl-paste --type text --watch ${pkgs.cliphist}/bin/cliphist store";
      Restart = "always";
      RestartSec = 2;
    };

    Install.WantedBy = [ "graphical-session.target" ];
  };

  systemd.user.services.cliphist-image = {
    Unit = {
      Description = "Clipboard history watcher for images";
      PartOf = [ "graphical-session.target" ];
      After = [ "graphical-session.target" ];
    };

    Service = {
      ExecStart = "${pkgs.wl-clipboard}/bin/wl-paste --type image --watch ${pkgs.cliphist}/bin/cliphist store";
      Restart = "always";
      RestartSec = 2;
    };

    Install.WantedBy = [ "graphical-session.target" ];
  };

  xdg.mimeApps = {
    enable = true;
    associations.added = {
      "application/x-executable" = [ "steam-run.desktop" ];
      "application/x-sharedlib" = [ "steam-run.desktop" ];
      "application/x-shellscript" = [ "steam-run.desktop" ];
      "text/x-shellscript" = [ "steam-run.desktop" ];
      "application/gzip" = [ "extract-archive.desktop" ];
      "application/vnd.rar" = [ "extract-archive.desktop" ];
      "application/x-7z-compressed" = [ "extract-archive.desktop" ];
      "application/x-bzip" = [ "extract-archive.desktop" ];
      "application/x-bzip-compressed-tar" = [ "extract-archive.desktop" ];
      "application/x-compressed-tar" = [ "extract-archive.desktop" ];
      "application/x-gtar" = [ "extract-archive.desktop" ];
      "application/x-rar" = [ "extract-archive.desktop" ];
      "application/x-tar" = [ "extract-archive.desktop" ];
      "application/x-xz" = [ "extract-archive.desktop" ];
      "application/x-xz-compressed-tar" = [ "extract-archive.desktop" ];
      "application/zip" = [ "extract-archive.desktop" ];
    };
    defaultApplications = {
      "image/png" = [ "imv.desktop" ];
      "image/jpeg" = [ "imv.desktop" ];
      "image/gif" = [ "imv.desktop" ];
      "video/mp4" = [ "mpv.desktop" ];
      "video/webm" = [ "mpv.desktop" ];
      "video/x-matroska" = [ "mpv.desktop" ];
      "text/html" = [ "firefox.desktop" ];
      "application/xhtml+xml" = [ "firefox.desktop" ];
      "x-scheme-handler/about" = [ "firefox.desktop" ];
      "x-scheme-handler/http" = [ "firefox.desktop" ];
      "x-scheme-handler/https" = [ "firefox.desktop" ];
      "x-scheme-handler/unknown" = [ "firefox.desktop" ];
      "application/pdf" = [ "firefox.desktop" ]; # Eksempel: Åbn PDF i Firefox
      "application/gzip" = [ "extract-archive.desktop" ];
      "application/vnd.rar" = [ "extract-archive.desktop" ];
      "application/x-7z-compressed" = [ "extract-archive.desktop" ];
      "application/x-bzip" = [ "extract-archive.desktop" ];
      "application/x-bzip-compressed-tar" = [ "extract-archive.desktop" ];
      "application/x-compressed-tar" = [ "extract-archive.desktop" ];
      "application/x-gtar" = [ "extract-archive.desktop" ];
      "application/x-rar" = [ "extract-archive.desktop" ];
      "application/x-tar" = [ "extract-archive.desktop" ];
      "application/x-xz" = [ "extract-archive.desktop" ];
      "application/x-xz-compressed-tar" = [ "extract-archive.desktop" ];
      "application/zip" = [ "extract-archive.desktop" ];
    };
  };

  xdg.desktopEntries."steam-run" = {
    name = "Steam Run";
    genericName = "Compatibility Runtime";
    comment = "Run executable files through the Steam runtime";
    exec = "${pkgs.steam-run}/bin/steam-run %f";
    icon = "steam";
    terminal = false;
    noDisplay = true;
    mimeType = [
      "application/x-executable"
      "application/x-sharedlib"
      "application/x-shellscript"
      "text/x-shellscript"
    ];
    categories = [ "Utility" ];
  };

  xdg.desktopEntries."extract-archive" = {
    name = "Extract Archive";
    genericName = "Archive Extractor";
    comment = "Extract archives next to the selected file";
    exec = "${config.home.homeDirectory}/.local/bin/extract-archive %f";
    icon = "package-x-generic";
    terminal = false;
    noDisplay = true;
    mimeType = [
      "application/gzip"
      "application/vnd.rar"
      "application/x-7z-compressed"
      "application/x-bzip"
      "application/x-bzip-compressed-tar"
      "application/x-compressed-tar"
      "application/x-gtar"
      "application/x-rar"
      "application/x-tar"
      "application/x-xz"
      "application/x-xz-compressed-tar"
      "application/zip"
    ];
    categories = [ "Utility" ];
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

  programs.qutebrowser = {
    # enable = true;
    enable = false;

    searchEngines = {
      DEFAULT = "https://www.google.com/search?q={}";
      g = "https://www.google.com/search?q={}";
      ddg = "https://duckduckgo.com/?q={}";
      nw = "https://wiki.nixos.org/index.php?search={}";
      aw = "https://wiki.archlinux.org/?search={}";
    };

    settings = {
      tabs.show = "multiple";
      tabs.position = "top";
      qt.args = [ "enable-smooth-scrolling" ];
      scrolling.smooth = true;
      content.autoplay = false;
      downloads.location.directory = "~/Downloads";
    };

    keyBindings.normal = {
      ",m" = "hint links spawn mpv {hint-url}";
      ",M" = "spawn mpv {url}";
    };

    quickmarks = {
      google = "https://google.com";
      youtube = "https://youtube.com";
      nixos = "https://wiki.nixos.org";
    };
  };


  # Let Home Manager install and manage itself.
  programs.home-manager.enable = true;

  # Enforce a global cursor theme to fix sizing/shape issues
  home.pointerCursor = {
    gtk.enable = true;
    x11.enable = true;
    name = "Adwaita";
    package = pkgs.adwaita-icon-theme;
    size = 24;
  };

  # Don't change this without reading the Home Manager release notes!
  home.stateVersion = "23.11"; 
}
