{
  config,
  pkgs,
  ...
}: let
  # ⚠️ THE MASTER SWITCH ⚠️
  devMode = false;

  # Helper function to automatically pick the right link type
  makeLink = stringPath: nixPath:
    if devMode
    then config.lib.file.mkOutOfStoreSymlink "${config.home.homeDirectory}/.dotfiles/${stringPath}"
    else nixPath;

  steamRunLibraryPath = pkgs.lib.makeLibraryPath [
    pkgs.libxmu
    pkgs.libGLU
    pkgs.libGL
  ];

  entmax = pkgs.python313Packages.buildPythonPackage rec {
    pname = "entmax";
    version = "1.3";
    format = "wheel";

    src = pkgs.fetchurl {
      url = "https://files.pythonhosted.org/packages/06/a0/71747f0d98e441d0670b06205afd24d832e88c0ee62129ca47ce88505304/${pname}-${version}-py3-none-any.whl";
      hash = "sha256-Qbse29SXobU7Hw/IC+/VQ0mdxwS05UNt32xXKKLQBUY=";
    };

    propagatedBuildInputs = with pkgs.python313Packages; [
      torch
    ];

    buildPhase = ''
      runHook preBuild
      runHook postBuild
    '';
    doCheck = false;
  };

  xTransformers = pkgs.python313Packages.buildPythonPackage rec {
    pname = "x-transformers";
    version = "0.15.0";
    format = "wheel";

    src = pkgs.fetchurl {
      url = "https://files.pythonhosted.org/packages/be/52/62fd9d73f4c3f56442c590bc020f25597df5ba37db789f7861922b991e5c/x_transformers-${version}-py3-none-any.whl";
      hash = "sha256-f+788y9GAFwrkUHX3AsIoKRy5Kf06h+V6ejdTnkicwk=";
    };

    propagatedBuildInputs = with pkgs.python313Packages; [
      einops
      torch
      entmax
    ];

    buildPhase = ''
      runHook preBuild
      runHook postBuild
    '';
    doCheck = false;
  };

  timm = pkgs.python313Packages.buildPythonPackage rec {
    pname = "timm";
    version = "0.5.4";
    format = "wheel";

    src = pkgs.fetchurl {
      url = "https://files.pythonhosted.org/packages/49/65/a83208746dc9c0d70feff7874b49780ff110810feb528df4b0ecadcbee60/${pname}-${version}-py3-none-any.whl";
      hash = "sha256-BZLI/S1G0HacC36VSz2s6pN2nu5A2rtL1/KsuFJDtYg=";
    };

    propagatedBuildInputs = with pkgs.python313Packages; [
      torch
      torchvision
    ];

    buildPhase = ''
      runHook preBuild
      runHook postBuild
    '';
    doCheck = false;
  };

  pix2tex = pkgs.python313Packages.buildPythonApplication rec {
    pname = "pix2tex";
    version = "0.1.4";
    format = "wheel";

    src = pkgs.fetchurl {
      url = "https://files.pythonhosted.org/packages/12/b8/673667ace0a131169502420810aa9dfca69aad960d5af88da68ddd46c7f0/${pname}-${version}-py3-none-any.whl";
      hash = "sha256-oCQwlQj8PopM5SQeCVJ2Ym0JjfU+YJQQAT8uw1pLdhI=";
    };

    weights = pkgs.fetchurl {
      url = "https://github.com/lukas-blecher/LaTeX-OCR/releases/download/v0.0.1/weights.pth";
      sha256 = "1anzl6am328gvkmph3jy2j1y5jym7gc8nnpvhav6q9ixqm0r2gd6";
    };

    imageResizer = pkgs.fetchurl {
      url = "https://github.com/lukas-blecher/LaTeX-OCR/releases/download/v0.0.1/image_resizer.pth";
      sha256 = "0n44f69adbfx7cdmjwr0miv735rxq8jvp434a8mi9bc5k5jj0f0w";
    };

    nativeBuildInputs = [
      pkgs.ninja
      pkgs.python313Packages.pythonRelaxDepsHook
    ];

    pythonRelaxDeps = [
      "albumentations"
    ];
    pythonRemoveDeps = [
      "opencv-python-headless"
    ];

    propagatedBuildInputs = with pkgs.python313Packages; [
      albumentations
      einops
      munch
      numpy
      opencv4
      pandas
      pillow
      pyyaml
      requests
      timm
      tokenizers
      torch
      tqdm
      transformers
      xTransformers
    ];

    buildPhase = ''
      runHook preBuild
      runHook postBuild
    '';
    postInstall = ''
      transforms_file="$out/${pkgs.python313.sitePackages}/pix2tex/dataset/transforms.py"
      substituteInPlace "$transforms_file" \
        --replace-fail "value=[255, 255, 255]" "fill=[255, 255, 255]" \
        --replace-fail "alb.GaussNoise(10, p=.2)" "alb.GaussNoise(std_range=(0.0, 10.0 / 255.0), p=.2)" \
        --replace-fail "alb.ImageCompression(95, p=.3)" "alb.ImageCompression(quality_range=(95, 100), p=.3)" \
        --replace-fail "alb.ToGray(always_apply=True)" "alb.ToGray(p=1.0)"

      checkpoint_dir="$out/${pkgs.python313.sitePackages}/pix2tex/model/checkpoints"
      install -Dm644 "$weights" "$checkpoint_dir/weights.pth"
      install -Dm644 "$imageResizer" "$checkpoint_dir/image_resizer.pth"
    '';

    doCheck = false;
  };

  swayosdOveramplified = pkgs.swayosd.overrideAttrs (oldAttrs: {
    patches = (oldAttrs.patches or []) ++ [
      ../patches/swayosd-overamplified-css.patch
    ];
  });

  talonCommunity = pkgs.fetchFromGitHub {
    owner = "talonhub";
    repo = "community";
    rev = "641a0852752ad1ef2af1a4334aabda8e87d550f7";
    sha256 = "043g8gzp40a2y3438biszs5xzxflddix27plr4mv5avr1djv13w1";
  };
in {
  imports = [
    ./common.nix
  ];

  services.easyeffects.enable = true;

  # Packages you want installed just for your user
  home.packages = with pkgs; [
    stdenv.cc.cc.lib # Runtime libstdc++ for Python ML wheels
    zlib # Runtime zlib for Python ML wheels
    wl-clipboard # Clipboard support
    cliphist # Clipboard history
    file # Detect text/image types for Codex clipboard history captures
    imv # billedeviser til wayland
    mpv # videoafspilere
    zathura # PDF/document viewer
    libnotify # beskeder om ting virker?
    mako # notification daemon for notify-send popups on Wayland
    yt-dlp # Download youtube vid
    ffmpeg # Handle the downloade video

    steam-run # Run games in Nix
    ouch # Extract archives from Nautilus
    unrar # unzip rar files

    wineWow64Packages.stable
    winetricks

    tor-browser
    (pkgs.callPackage ../pkgs/talon.nix {})

    ghostty # Terminal
    tree-sitter # Nvim needs it
    python311
    pix2tex # Math OCR without runtime pip installs
    xdg-utils # Provides xdg-open for the open alias
    glib # Provides gio for the fuzzy "Open with" launcher
    man-pages # C library/API man pages, e.g. man 3 printf
    man-pages-posix

    # --- hypr window-manager ---
    waybar
    rofi

    # For your custom scripts
    ydotool # Wayland input helper for the autoclicker

    # For your app keybinds
    nautilus # Your preferred file manager
    spotify # Your music player
    lazydocker # Your docker manager
    wlr-randr # Useful for manual display checks
    blueman # A standard Bluetooth manager GUI (since you are missing omarchy-bluetooth)

    # For Fn-keys
    keyd # Keyboard event monitor/remapping CLI
    brightnessctl # briightness
    playerctl #
    pavucontrol # sound/audio
    easyeffects # PipeWire microphone/speaker effects
    swayosdOveramplified # brightness/audio graphics

    grim # takes the picture
    slurp # Drags the captured picture

    # --- Nvim nix packages instead of Mason ---
    vscode-langservers-extracted
    python311Packages.flake8 # Adds flake8 to your PATH correctly
    vtsls
    pyright
    stylua
    lua-language-server
    jdt-language-server
    glibc.dev # The core C standard library headers (<stdio.h>, <stdlib.h>)

    clang-tools
    online-judge-tools
  ];

  # ==========================================
  # SYMLINKING DOTFILES
  # ==========================================
  home.file = {
    # 2. Waybar (Directory - needs recursive)
    ".talon/user/community" = {
      source = talonCommunity;
      recursive = true;
    };

    ".talon/user/local/microphone-selection-key.talon".text = ''
      key(ctrl-alt-.): user.microphone_selection_toggle()
    '';

    ".talon/user/local/escape-cancel.talon".text = ''
      key(escape):
          user.cancel_current_phrase()
          key(escape)
    '';

    ".config/waybar" = {
      source = makeLink "waybar/.config/waybar" ../waybar/.config/waybar;
      recursive = true;
    };

    # 3. Rofi (Single File)
    ".config/rofi/config.rasi".source = makeLink "rofi/config.rasi" ../rofi/config.rasi;

    # 4. Mako notifications
    ".config/mako/config".source = makeLink "mako/config" ../mako/config;

    ".config/swayosd/config.toml".source = makeLink "swayosd/config.toml" ../swayosd/config.toml;
    ".config/swayosd/style.css".source = makeLink "swayosd/style.css" ../swayosd/style.css;

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

    ".local/bin/idle-monitor-toggle" = {
      source = makeLink "scripts/idle-monitor-toggle" ../scripts/idle-monitor-toggle;
      executable = true;
    };

    ".local/bin/idle-workspace-status" = {
      source = makeLink "scripts/idle-workspace-status" ../scripts/idle-workspace-status;
      executable = true;
    };

    ".local/bin/workspace-dispatch" = {
      source = makeLink "scripts/workspace-dispatch" ../scripts/workspace-dispatch;
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

    ".local/bin/cursor-circle" = {
      source = makeLink "scripts/cursor-circle" ../scripts/cursor-circle;
      executable = true;
    };

    ".local/bin/math-ocr" = {
      source = makeLink "scripts/math-ocr" ../scripts/math-ocr;
      executable = true;
    };

    ".local/bin/easyeffects-start-bypassed" = {
      source = makeLink "scripts/easyeffects-start-bypassed" ../scripts/easyeffects-start-bypassed;
      executable = true;
    };

    ".local/bin/talon-microphone-menu" = {
      text = ''
        #!/bin/sh
        set -eu

        if [ ! -S "$HOME/.talon/.sys/repl.sock" ]; then
          ${pkgs.libnotify}/bin/notify-send "Talon is not running" "Start Talon before opening the microphone picker."
          exit 1
        fi

        if ! printf '%s\n' \
          'from talon import actions' \
          'actions.user.microphone_selection_toggle()' \
          | "$HOME/.talon/.venv/bin/repl" >/tmp/talon-microphone-menu.log 2>&1; then
          ${pkgs.libnotify}/bin/notify-send "Talon microphone picker failed" "See /tmp/talon-microphone-menu.log"
          exit 1
        fi
      '';
      executable = true;
    };

    ".local/bin/notification-popups" = {
      source = makeLink "scripts/notification-popups" ../scripts/notification-popups;
      executable = true;
    };

    ".local/bin/clipboard-history" = {
      source = makeLink "scripts/clipboard-history" ../scripts/clipboard-history;
      executable = true;
    };

    ".local/bin/codex-capture" = {
      source = makeLink "scripts/codex-capture" ../scripts/codex-capture;
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

    ".local/bin/screenshot-focused-output" = {
      source = makeLink "scripts/screenshot-focused-output" ../scripts/screenshot-focused-output;
      executable = true;
    };

    ".local/bin/steam-run" = {
      text = ''
        #!/bin/sh
        export LD_LIBRARY_PATH="${steamRunLibraryPath}:''${LD_LIBRARY_PATH:-}"
        exec ${pkgs.steam-run}/bin/steam-run "$@"
      '';
      executable = true;
    };

    # 7. Bash (Single File)
    ".mybashrc.sh".source = makeLink "bash/.mybashrc.sh" ../bash/.mybashrc.sh;
    ".bash_desktop.sh".source = makeLink "bash/desktop.sh" ../bash/desktop.sh;

    # 8. Hyprland (Single File)
    ".config/hypr/hyprland.conf".source = makeLink "hypr/hyprland.conf" ../hypr/hyprland.conf;

    # 9. Waybar Dev Badge Trigger
    ".cache/dev-mode-status".text =
      if devMode
      then "[ DEV ]"
      else "";

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
      PartOf = ["graphical-session.target"];
      After = ["graphical-session.target"];
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
      PartOf = ["graphical-session.target"];
      After = ["graphical-session.target"];
    };

    Service = {
      ExecStart = "%h/.local/bin/battery-alert";
      Restart = "always";
      RestartSec = 2;
    };

    Install.WantedBy = ["graphical-session.target"];
  };

  systemd.user.services.cliphist-text = {
    Unit = {
      Description = "Clipboard history watcher for text";
      PartOf = ["graphical-session.target"];
      After = ["graphical-session.target"];
    };

    Service = {
      ExecStart = "${pkgs.wl-clipboard}/bin/wl-paste --type text --watch ${pkgs.cliphist}/bin/cliphist store";
      Restart = "always";
      RestartSec = 2;
    };

    Install.WantedBy = ["graphical-session.target"];
  };

  systemd.user.services.cliphist-image = {
    Unit = {
      Description = "Clipboard history watcher for images";
      PartOf = ["graphical-session.target"];
      After = ["graphical-session.target"];
    };

    Service = {
      ExecStart = "${pkgs.wl-clipboard}/bin/wl-paste --type image --watch ${pkgs.cliphist}/bin/cliphist store";
      Restart = "always";
      RestartSec = 2;
    };

    Install.WantedBy = ["graphical-session.target"];
  };

  xdg.desktopEntries."steam-run" = {
    name = "Steam Run";
    genericName = "Compatibility Runtime";
    comment = "Run executable files through the Steam runtime";
    exec = "${config.home.homeDirectory}/.local/bin/steam-run %f";
    icon = "steam";
    terminal = false;
    noDisplay = true;
    mimeType = [
      "application/x-executable"
      "application/x-sharedlib"
      "application/x-shellscript"
      "text/x-shellscript"
    ];
    categories = ["Utility"];
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
    categories = ["Utility"];
  };

  # ==========================================
  # NATIVE BASH CONFIGURATION
  # ==========================================
  programs.bash = {
    enable = true;
    initExtra = ''
      if [ -f ~/.bash_desktop.sh ]; then
        source ~/.bash_desktop.sh
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
      qt.args = ["enable-smooth-scrolling"];
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

  # Enforce a global cursor theme to fix sizing/shape issues
  home.pointerCursor = {
    gtk.enable = true;
    x11.enable = true;
    name = "Adwaita";
    package = pkgs.adwaita-icon-theme;
    size = 24;
  };
}
