{
  config,
  pkgs,
  lib,
  ...
}: let
  dictation = pkgs.callPackage ../pkgs/dictation.nix {};
  modelFile = "parakeet-ultra-Q8_0.gguf";
  model = pkgs.fetchurl {
    url = "https://huggingface.co/handy-computer/parakeet-ultra-gguf/resolve/39eeb55181f0d354fd934f06e92fd8d5037fed8e/${modelFile}";
    hash = "sha256-AHpZdh6SWHefGJ3zlrUNErg7tbeeZt9LlVwjDS8qClk=";
  };
  live = pkgs.callPackage ../pkgs/dictation-live.nix {
    inherit dictation model;
    handy = config.services.handy.package;
  };
  streamingModelFile = "nemotron-3.5-asr-streaming-0.6b-Q8_0.gguf";
  streamingModel = pkgs.fetchurl {
    url = "https://huggingface.co/handy-computer/nemotron-3.5-asr-streaming-0.6b-gguf/resolve/6d44e540bc31b0de1dbe174a3cea87f53a7f22fb/${streamingModelFile}";
    hash = "sha256-uUVFsxOzIj/aeyhXpSaB2oE5NcISdkPR6f8MI9mICJw=";
  };
  settings = pkgs.writeText "dictation-handy-settings.json" (builtins.toJSON {
    # Ultra improves the original V3's English/Danish accuracy. The GGUF engine
    # can use the Radeon GPU; keep the model warm to avoid repeated cold loads.
    # A file outside the bundled catalog is identified by its filename stem.
    selected_model = "parakeet-ultra-Q8_0";
    selected_language = "auto";
    translate_to_english = false;
    model_unload_timeout = "never";
    vad_enabled = true;
    post_process_enabled = false;
    paste_method = "external_script";
    clipboard_handling = "dont_modify";
    external_script_path = "${dictation}/bin/dictation-paste";
    log_level = "info";
  });
  configure = pkgs.writeShellApplication {
    name = "configure-handy-dictation";
    runtimeInputs = [pkgs.coreutils pkgs.jq];
    text = ''
      data_dir="''${XDG_DATA_HOME:-$HOME/.local/share}/com.pais.handy"
      mkdir -p "$data_dir"
      store="$data_dir/settings_store.json"
      if [[ -e "$store" && ! -e "$store.before-dictation-upgrade" ]]; then
        install -m600 "$store" "$store.before-dictation-upgrade"
      fi
      temporary="$(mktemp "$data_dir/.settings_store.XXXXXX")"
      trap 'rm -f "$temporary"' EXIT
      if [[ -e "$store" ]]; then
        jq --slurpfile managed ${settings} '.settings = ((.settings // {}) + $managed[0])' "$store" > "$temporary"
      else
        jq -n --slurpfile managed ${settings} '{settings: $managed[0]}' > "$temporary"
      fi
      mv "$temporary" "$store"
      rm -f "''${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/handy-recording"
    '';
  };
in {
  home.packages = [
    live
    (pkgs.callPackage ../pkgs/dictation-benchmark.nix {
      inherit dictation;
      dictation-live = live;
      handy = config.services.handy.package;
    })
  ];
  services.handy.enable = true;
  # Keep Handy available as a settings/benchmark fallback, with the Rust
  # service owning interactive capture and the existing desktop shortcut.
  systemd.user.services.handy.Install.WantedBy = lib.mkForce [];
  systemd.user.services.handy.Service.ExecStartPre = "${configure}/bin/configure-handy-dictation";
  systemd.user.services.dictation-live = {
    Unit = {
      Description = "Live local dictation with native Rust overlay";
      After = ["graphical-session.target" "pipewire.service"];
      PartOf = ["graphical-session.target"];
    };
    Service = {
      ExecStart = "${live}/bin/dictation-live serve";
      Environment = ["GDK_BACKEND=wayland"];
      Restart = "on-failure";
      RestartSec = 2;
    };
    Install.WantedBy = ["graphical-session.target"];
  };

  home.file = {
    ".local/share/com.pais.handy/models/${modelFile}".source = model;
    ".local/share/com.pais.handy/models/${streamingModelFile}".source = streamingModel;
    ".local/bin/handy-toggle".source = "${live}/bin/dictation-live-toggle";
  };
}
