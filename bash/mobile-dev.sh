# mobile-dev VPS Bash configuration.

if [ "$TERM" = "xterm-ghostty" ]; then
  export TERM="xterm-256color"
fi

unalias ta 2>/dev/null || true
ta() {
  tmux new-session -A -s main
}

nxb() {
  sudo nixos-rebuild switch --flake ~/.dotfiles#mobile-dev
}

if [ -z "${TMUX:-}" ] && [ -n "${SSH_CONNECTION:-}" ]; then
  ta
fi
