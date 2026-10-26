# shellcheck shell=bash
# Shared by interactive Bash and the standalone c command.

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
    # Wait for the clipboard writer before a short-lived shell exits.
    local tee_status copy_pid copy_status
    tee >(copy_stdin >/dev/null)
    tee_status=$? copy_pid=$!
    wait "$copy_pid"
    copy_status=$?
    [ "$tee_status" -eq 0 ] && [ "$copy_status" -eq 0 ]
  fi
}
