# shellcheck shell=bash
# Shared interactive Bash configuration for desktop and mobile-dev hosts.

if [ -r "$HOME/.bash_host_metadata.sh" ]; then
  # shellcheck source=/dev/null
  source "$HOME/.bash_host_metadata.sh"
fi

HISTCONTROL=ignoreboth
shopt -s histappend
HISTSIZE=1000
HISTFILESIZE=2000
shopt -s checkwinsize

set -o vi

export EDITOR="nvim"
export VISUAL="nvim"
export MANPAGER='nvim +Man!'
export PATH="$HOME/.local/bin:$PATH"

if [ -x /usr/bin/dircolors ]; then
  if [ -r ~/.dircolors ]; then
    eval "$(dircolors -b ~/.dircolors)"
  else
    eval "$(dircolors -b)"
  fi
  alias ls='ls --color=auto'
  alias grep='grep --color=auto'
  alias fgrep='fgrep --color=auto'
  alias egrep='egrep --color=auto'
fi

alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'
alias cl='clear'
alias python='python3'
alias dots='cd ~/.dotfiles'
alias cd.='cd ~/.dotfiles'
alias brc='nvim ~/.dotfiles/bash/common.sh ~/.dotfiles/bash/desktop.sh ~/.dotfiles/bash/mobile-dev.sh'
alias flake='nvim ~/.dotfiles/flake.nix'
alias cx='codex'
alias ta='tmux new-session -A -s main'

nxb() {
  nh os switch "$HOME/.dotfiles#${DOTFILES_FLAKE_TARGET:?DOTFILES_FLAKE_TARGET is not set}"
}

conf() {
  nvim "${DOTFILES_NIXOS_CONFIG:?DOTFILES_NIXOS_CONFIG is not set}"
}

home() {
  nvim "${DOTFILES_HOME_MANAGER_CONFIG:?DOTFILES_HOME_MANAGER_CONFIG is not set}"
}

function brc. {
  if [ -r "$HOME/.bash_host_metadata.sh" ]; then
    # shellcheck source=/dev/null
    source "$HOME/.bash_host_metadata.sh"
  fi

  # shellcheck source=/dev/null
  source "$HOME/.bash_common.sh"

  case "${DOTFILES_FLAKE_TARGET:-}" in
    mobile-dev)
      if [ -f "$HOME/.bash_mobile_dev.sh" ]; then
        # shellcheck source=/dev/null
        source "$HOME/.bash_mobile_dev.sh"
      fi
      ;;
    nixos)
      if [ -f "$HOME/.bash_desktop.sh" ]; then
        # shellcheck source=/dev/null
        source "$HOME/.bash_desktop.sh"
      fi
      ;;
    *)
      printf 'Unknown DOTFILES_FLAKE_TARGET: %s\n' "${DOTFILES_FLAKE_TARGET:-<unset>}" >&2
      return 1
      ;;
  esac
}

alias nvimconf='nvim ~/.dotfiles/nvim/.config/nvim/init.lua'
alias nvimkeyb='nvim ~/.dotfiles/nvim/.config/nvim/lua/config/keymaps.lua'

# Default interactive Codex sessions to unrestricted mode. Pass --no-yolo to
# bypass this wrapper default and use the permissions configured by Codex.
codex() {
  local arg yolo=1
  local -a codex_args=()

  for arg in "$@"; do
    if [ "$arg" = "--no-yolo" ]; then
      yolo=0
    else
      codex_args+=("$arg")
    fi
  done

  if [ "$yolo" -eq 1 ]; then
    command codex --yolo "${codex_args[@]}"
  else
    command codex "${codex_args[@]}"
  fi
}

gdiff() {
  if command -v delta >/dev/null 2>&1; then
    if [ "$#" -eq 0 ]; then
      {
        git diff --quiet || { printf '\n# Unstaged changes\n\n'; git diff --color=always; }
        git diff --cached --quiet || { printf '\n# Staged changes\n\n'; git diff --cached --color=always; }
      } | delta --paging=always
    else
      git diff --color=always "$@" | delta --paging=always
    fi
  else
    if [ "$#" -eq 0 ]; then
      git diff --quiet || { printf '\n# Unstaged changes\n\n'; git diff; }
      git diff --cached --quiet || { printf '\n# Staged changes\n\n'; git diff --cached; }
    else
      git diff "$@"
    fi
  fi
}

gdiffs() {
  if [ "$#" -eq 0 ]; then
    git diff --quiet || { printf '\n# Unstaged changes\n\n'; git diff --stat; }
    git diff --cached --quiet || { printf '\n# Staged changes\n\n'; git diff --cached --stat; }
  else
    git diff --stat "$@"
  fi
}

gsyntax() {
  if command -v difft >/dev/null 2>&1; then
    difft "$@"
  else
    printf 'difftastic is not installed in this shell.\n' >&2
    return 127
  fi
}

alias_str=".."
cmd_str="cd .."
for _ in {1..10}; do
  # These aliases intentionally capture the progressively built command.
  # shellcheck disable=SC2139
  alias "${alias_str}=$cmd_str"
  alias_str="$alias_str."
  cmd_str="$cmd_str/.."
done
unset alias_str cmd_str

osc52_copy() {
  local encoded sequence terminator
  encoded="$(base64 | tr -d '\n')" || return 1

  if [ -n "${TMUX:-}" ]; then
    sequence=$'\033Ptmux;\033\033]52;c;'
    terminator=$'\a\033\\'
  else
    sequence=$'\033]52;c;'
    terminator=$'\a'
  fi

  # Clipboard helpers often silence their standard output. Send the escape
  # sequence straight to the terminal when possible so OSC52 still arrives.
  if { printf '%s%s%s' "$sequence" "$encoded" "$terminator" >/dev/tty; } 2>/dev/null; then
    return 0
  fi

  printf '%s%s%s' "$sequence" "$encoded" "$terminator"
}

copy_stdin() {
  local tmp tmux_status=0 osc52_status=0

  if [ -n "${TMUX:-}" ] && { [ -n "${SSH_CONNECTION:-}" ] || [ -n "${SSH_TTY:-}" ]; }; then
    tmp="$(mktemp)" || return 1
    command cat >"$tmp"
    tmux load-buffer - <"$tmp" || tmux_status=$?
    osc52_copy <"$tmp" || osc52_status=$?
    command rm -f -- "$tmp"
    [ "$tmux_status" -eq 0 ] && [ "$osc52_status" -eq 0 ]
  elif command -v wl-copy >/dev/null 2>&1 && [ -n "${WAYLAND_DISPLAY:-}" ]; then
    wl-copy
  else
    osc52_copy
  fi
}

paste_stdout() {
  if [ -n "${TMUX:-}" ] && { [ -n "${SSH_CONNECTION:-}" ] || [ -n "${SSH_TTY:-}" ]; }; then
    tmux save-buffer - 2>/dev/null || {
      printf 'The tmux paste buffer is empty.\n' >&2
      return 1
    }
  elif command -v wl-paste >/dev/null 2>&1 && [ -n "${WAYLAND_DISPLAY:-}" ]; then
    wl-paste
  else
    printf 'Paste is unavailable: use Wayland or a remote tmux session.\n' >&2
    return 1
  fi
}

alias p='paste_stdout'
alias v='paste_stdout'

unalias c 2>/dev/null || true
c() {
  if [ -t 0 ]; then
    printf '%s' "$*" | copy_stdin
  else
    tee >(copy_stdin >/dev/null)
  fi
}

history_pick() {
  local selected
  selected="$(builtin history | tac | fzf --bind 'ctrl-y:accept')" || return
  printf '%s\n' "$selected" | awk '{$1=""; sub(/^ /, ""); print}'
}

history() {
  local selected
  selected="$(history_pick)" || return
  printf '%s' "$selected" | copy_stdin >/dev/null 2>&1 || true
  printf '%s\n' "$selected"
}

history_insert() {
  local selected
  selected="$(history_pick)" || return
  printf '%s' "$selected" | copy_stdin >/dev/null 2>&1 || true
  READLINE_LINE="$selected"
  READLINE_POINT="${#READLINE_LINE}"
}

bind -x '"\C-h": history_insert'

sharecode() {
  local -a statuses
  repomix --stdout | copy_stdin
  statuses=("${PIPESTATUS[@]}")
  [ "${statuses[0]}" -eq 0 ] && [ "${statuses[1]}" -eq 0 ]
}

sharetree() {
  local -a statuses
  tree -a -I '.git|.nix-profile' | copy_stdin
  statuses=("${PIPESTATUS[@]}")
  [ "${statuses[0]}" -eq 0 ] && [ "${statuses[1]}" -eq 0 ]
}

cmdc() {
  if [ "$#" -eq 0 ]; then
    printf 'Usage: cmdc "command to run"\n'
    return 2
  fi

  local cmd tmp status
  tmp="$(mktemp)" || return 1

  if [ "$#" -eq 1 ]; then
    cmd="$1"
  else
    printf -v cmd '%q ' "$@"
    cmd="${cmd% }"
  fi

  printf '$ %s\n' "$cmd" | tee "$tmp"
  eval "$cmd" 2>&1 | tee -a "$tmp"
  status="${PIPESTATUS[0]}"

  if copy_stdin <"$tmp"; then
    printf 'Copied command and output'
    if [ "$status" -ne 0 ]; then
      printf ' (exit %s)' "$status"
    fi
    printf '.\n'
  else
    printf 'Failed to copy command output.\n' >&2
  fi

  rm -f "$tmp"
  return "$status"
}

tldrf() {
  curl -Gs "https://www.mankier.com/api/explain/?cols=$(tput cols)" --data-urlencode "q=$*"
}

cdd() {
  local dir
  local find_cmd="find . -maxdepth 4 -type d -not -path '*/.*'"

  if command -v fd >/dev/null 2>&1; then
    find_cmd="fd . $HOME --type d --hidden --exclude .git"
  elif command -v fdfind >/dev/null 2>&1; then
    find_cmd="fdfind . $HOME --type d --hidden --exclude .git"
  fi

  dir=$(eval "$find_cmd" | fzf --preview 'tree -a -L 1 {}' --preview-window=right:50%) || return

  if [ -n "$dir" ]; then
    cd "$dir" || return
  fi
}

if command -v zoxide >/dev/null 2>&1; then
  eval "$(zoxide init bash --cmd cd)"
  alias zz='zi'
fi
