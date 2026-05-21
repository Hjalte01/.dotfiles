# Shared interactive Bash configuration for desktop and mobile-dev hosts.

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
  test -r ~/.dircolors && eval "$(dircolors -b ~/.dircolors)" || eval "$(dircolors -b)"
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
alias home='nvim ~/.dotfiles/home-manager/home.nix'
alias flake='nvim ~/.dotfiles/flake.nix'
alias cx='codex'
alias ta='tmux new-session -A -s main'

alias_str=".."
cmd_str="cd .."
for i in $(seq 1 10); do
  alias "${alias_str}=$cmd_str"
  alias_str="$alias_str."
  cmd_str="$cmd_str/.."
done
unset alias_str cmd_str

osc52_copy() {
  local encoded
  encoded="$(base64 | tr -d '\n')" || return 1

  if [ -n "${TMUX:-}" ]; then
    printf '\033Ptmux;\033\033]52;c;%s\a\033\\' "$encoded"
  else
    printf '\033]52;c;%s\a' "$encoded"
  fi
}

copy_stdin() {
  if command -v wl-copy >/dev/null 2>&1 && [ -n "${WAYLAND_DISPLAY:-}" ]; then
    wl-copy "$@"
  else
    osc52_copy
  fi
}

unalias c 2>/dev/null || true
c() {
  if [ -t 0 ]; then
    printf '%s' "$*" | copy_stdin
  else
    tee >(copy_stdin >/dev/null)
  fi
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
    cd "$dir"
  fi
}

if command -v zoxide >/dev/null 2>&1; then
  eval "$(zoxide init bash --cmd cd)"
  alias zz='zi'
fi
