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

_hendrix_pid_file=/run/openconnect-hendrix.pid

_hendrix_network_ready() {
  timeout 3 getent ahostsv4 hendrixgate >/dev/null 2>&1
}

_hendrix_vpn_up() {
  if _hendrix_network_ready; then
    echo "KU network is already reachable."
    return 0
  fi

  # Tailscale's exclusive resolvconf entry otherwise hides the DNS servers
  # supplied by KU's VPN. This is restored by `hendrix down`.
  if systemctl is-active --quiet tailscaled.service; then
    echo "Temporarily disabling Tailscale DNS..."
    sudo tailscale set --accept-dns=false || return
  fi

  # Disabling Tailscale DNS may be sufficient when connected to KU's wired
  # network, in which case no VPN is needed.
  if _hendrix_network_ready; then
    echo "KU network is reachable; no new VPN connection is needed."
    return 0
  fi

  echo "Connecting to KU VPN (enter KUnet password, then NetIQ TOTP)..."
  if ! sudo openconnect \
    --background \
    --pid-file="$_hendrix_pid_file" \
    --protocol=anyconnect \
    --useragent=AnyConnect \
    --resolve=vpn.ku.dk:130.225.226.62 \
    --user=fhz806 \
    vpn.ku.dk; then
    sudo tailscale set --accept-dns=true >/dev/null 2>&1 || true
    return 1
  fi

  if ! _hendrix_network_ready; then
    echo "VPN connected, but Hendrix DNS is unavailable." >&2
    return 1
  fi

  echo "KU VPN connected."
}

_hendrix_vpn_down() {
  local pid=""

  if [ -r "$_hendrix_pid_file" ]; then
    read -r pid <"$_hendrix_pid_file"
  fi

  if [[ "$pid" =~ ^[0-9]+$ ]] && [ "$(ps -p "$pid" -o comm= 2>/dev/null)" = "openconnect" ]; then
    echo "Disconnecting KU VPN..."
    sudo kill -TERM "$pid"
    for _ in {1..20}; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.1
    done
  else
    echo "No helper-managed KU VPN is running."
  fi

  if [ -e "$_hendrix_pid_file" ]; then
    sudo rm -f -- "$_hendrix_pid_file"
  fi

  echo "Restoring Tailscale DNS..."
  sudo tailscale set --accept-dns=true
}

_hendrix_status() {
  if _hendrix_network_ready; then
    echo "Hendrix network: reachable"
  else
    echo "Hendrix network: unavailable"
  fi

  if [ -r "$_hendrix_pid_file" ]; then
    local pid
    read -r pid <"$_hendrix_pid_file"
    if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
      echo "KU VPN: running (PID $pid)"
      return
    fi
  fi
  echo "KU VPN: not managed by this helper"
}

hendrix() {
  case "${1:-ssh}" in
    up)
      _hendrix_vpn_up
      ;;
    down)
      _hendrix_vpn_down
      ;;
    status)
      _hendrix_status
      ;;
    ssh)
      shift || true
      _hendrix_vpn_up && command ssh hendrix "$@"
      ;;
    help | -h | --help)
      echo "Usage: hendrix [up|down|status|ssh [SSH_ARGS...]]"
      ;;
    *)
      echo "Usage: hendrix [up|down|status|ssh [SSH_ARGS...]]" >&2
      return 2
      ;;
  esac
}

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
