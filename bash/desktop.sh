# shellcheck shell=bash
# Desktop-only Bash configuration.

export BROWSER=firefox
[ -x /usr/bin/lesspipe ] && eval "$(SHELL=/bin/sh lesspipe)"

alias open='xdg-open'
alias vps='ssh vps'

alias hypr='nvim ~/.dotfiles/hypr/hyprland.conf'

alias oo="nmcli radio wifi off && sleep 1 && nmcli radio wifi on"
alias touchdraw="touchscreen-toggle temp"
alias touchon="touchscreen-toggle on"
alias touchoff="touchscreen-toggle off"

eduroam() {
  nmcli connection up uuid 0701ab50-f4c4-41c3-b596-a220c4e3ffe5 --ask
}

nxb_old() {
  sudo nixos-rebuild switch --flake ~/.dotfiles/#nixos
}

# Hendrix commands are installed declaratively by Home Manager.
# Run `hendrix tui`, `hendrix up`, or `hendrix ssh`.
# Clear functions from older copies when a long-lived shell reloads its config.
unset -f hendrix _hendrix_vpn_up _hendrix_vpn_down _hendrix_status _hendrix_network_ready

ca() {
  local new_text current_clip
  new_text=$(cat)
  current_clip=$(wl-paste 2>/dev/null)
  echo -e "$current_clip\n$new_text" | wl-copy
  echo "Appended to clipboard."
}

ac() {
  local new_text current_clip
  new_text=$(cat)
  current_clip=$(wl-paste 2>/dev/null)
  echo -e "$new_text\n$current_clip" | wl-copy
  echo "Prepended to clipboard."
}

dev() {
  local file="$HOME/.dotfiles/home-manager/home.nix"

  if grep -q "devMode = false;" "$file"; then
    sed -i 's/devMode = false;/devMode = true;/g' "$file"
    echo "Dev Mode ENABLED. Rebuilding system..."
  elif grep -q "devMode = true;" "$file"; then
    sed -i 's/devMode = true;/devMode = false;/g' "$file"
    echo "Dev Mode DISABLED. Locking files to Nix store..."
  else
    echo "Error: Could not find 'devMode' toggle in home.nix"
    return 1
  fi

  sudo nixos-rebuild switch --flake ~/.dotfiles/#nixos
}

if [ -f "$HOME/.api_key_gpt" ]; then
  export OPENAI_API_KEY
  OPENAI_API_KEY=$(cat "$HOME/.api_key_gpt")
fi

alias yt-mp4='yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best" --merge-output-format mp4 -o "%(title)s.%(ext)s"'
alias yt-mp3='yt-dlp -x --audio-format mp3 -o "%(title)s.%(ext)s"'
