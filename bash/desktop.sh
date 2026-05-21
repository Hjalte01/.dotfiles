# Desktop-only Bash configuration.

export BROWSER=firefox
[ -x /usr/bin/lesspipe ] && eval "$(SHELL=/bin/sh lesspipe)"

alias open='xdg-open'
alias p='wl-paste'
alias v='wl-paste'

alias hypr="nvim $HOME/.dotfiles/hypr/hyprland.conf"
alias brc.=". $HOME/.bash_common.sh; . $HOME/.bash_desktop.sh"
alias conf="nvim $HOME/.dotfiles/nixos/configuration.nix"
alias nvimconf="nvim $HOME/.dotfiles/nvim/.config/nvim/lua/plugins/code-companion.lua.bak"
alias nvimkeyb="nvim $HOME/.dotfiles/nvim/.config/nvim/lua/config/keymaps.lua"

alias oo="nmcli radio wifi off && sleep 1 && nmcli radio wifi on"

yaya() {
  local INSTALL_SCRIPT="$HOME/omarchy-supplement/install-all.sh"
  local MARKER="# INSERT_HERE"

  for PACKAGE in "$@"; do
    echo "---------------------------------"
    echo "Attempting to install: $PACKAGE"
    yay -S "$PACKAGE"

    if pacman -Qi "$PACKAGE" >/dev/null 2>&1; then
      if grep -q "\"$PACKAGE\"" "$INSTALL_SCRIPT"; then
        echo "Installed, but '$PACKAGE' is already in your install list."
      else
        sed -i "/$MARKER/i \    \"$PACKAGE\"" "$INSTALL_SCRIPT"
        echo "Success. Added '$PACKAGE' to your automation script."
      fi
    else
      echo "Installation failed. Not added to script."
    fi
  done
}

history_pick() {
  local selected
  selected="$(
    builtin history |
      tac |
      fzf --bind 'ctrl-y:execute-silent(echo {+} | awk '\''{$1=""; sub(/^ /, ""); print}'\'' | wl-copy)+abort'
  )" || return

  printf '%s\n' "$selected" | awk '{$1=""; sub(/^ /, ""); print}'
}

history() {
  local selected
  selected="$(history_pick)" || return
  printf '%s' "$selected" | wl-copy >/dev/null 2>&1 || true
  printf '%s\n' "$selected"
}

history_insert() {
  local selected
  selected="$(history_pick)" || return
  printf '%s' "$selected" | wl-copy >/dev/null 2>&1 || true
  READLINE_LINE="$selected"
  READLINE_POINT="${#READLINE_LINE}"
}

bind -x '"\C-h": history_insert'

WACOM_TOUCH_ID="0018:056A:5367.0003"
WACOM_DRIVER_PATH="/sys/bus/hid/drivers/wacom"

ts_disable() {
  echo "Disabling Wacom Touchscreen..."
  if [ -d "$WACOM_DRIVER_PATH/$WACOM_TOUCH_ID" ]; then
    echo "$WACOM_TOUCH_ID" | sudo tee "$WACOM_DRIVER_PATH/unbind" >/dev/null
    echo "Touchscreen Disabled."
  else
    echo "Touchscreen already disabled."
  fi
}

ts_enable() {
  echo "Enabling Wacom Touchscreen..."
  if [ ! -d "$WACOM_DRIVER_PATH/$WACOM_TOUCH_ID" ]; then
    echo "$WACOM_TOUCH_ID" | sudo tee "$WACOM_DRIVER_PATH/bind" >/dev/null
    echo "Touchscreen Enabled."
  else
    echo "Touchscreen already enabled."
  fi
}

alias venvsip='source $HOME/Documents/sip/venv/bin/activate'
alias venvno='source $HOME/Documents/no/venv/bin/activate'

auto_sip() {
  cd "$HOME/Documents/sip/assignment_7/" || return
  venvsip
  nvim task
}

tf_sip() {
  cd "$HOME/Documents/sip/assignment_8/task/" || return
  source ../tf/venv/bin/activate
  nvim .
}

nxb_old() {
  sudo nixos-rebuild switch --flake ~/.dotfiles/#nixos
}

nxb() {
  nh os switch ~/.dotfiles#nixos
}

alias sharecode="npx repomix --copy && rm repomix-output.* 2>/dev/null"
alias sharetree="tree -a -I '.git|.nix-profile' | wl-copy"

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
