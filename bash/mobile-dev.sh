# shellcheck shell=bash
# mobile-dev VPS Bash configuration.

if [ "$TERM" = "xterm-ghostty" ]; then
  export TERM="xterm-256color"
fi

if [ -z "${TMUX:-}" ] && [ -n "${SSH_CONNECTION:-}" ]; then
  ta
fi
