# Managed by hendrix shell-setup; interactive shells only.
[[ $- == *i* ]] || return 0
[[ ${HENDRIX_SHELL_READY:-} != 1 ]] || return 0
HENDRIX_SHELL_READY=1

if [[ -z ${BASH_COMPLETION_VERSINFO:-} && -r /usr/share/bash-completion/bash_completion ]]; then
    # shellcheck disable=SC1091
    source /usr/share/bash-completion/bash_completion
fi

# Keep input on its own line, with no colour escapes to confuse cursor widths.
PS1='\u@\h:\W\n\$ '
shopt -s checkwinsize histappend
HISTSIZE=20000
HISTFILESIZE=40000
HISTCONTROL=ignoreboth

bind 'set completion-ignore-case on'
bind 'set show-all-if-ambiguous on'
bind 'set menu-complete-display-prefix on'
bind 'set horizontal-scroll-mode off'
bind 'set enable-bracketed-paste on'
for hendrix_keymap in emacs-standard vi-insert; do
    bind -m "$hendrix_keymap" '"\C-i": menu-complete'
    bind -m "$hendrix_keymap" '"\e[Z": menu-complete-backward'
    bind -m "$hendrix_keymap" '"\e[A": history-search-backward'
    bind -m "$hendrix_keymap" '"\e[B": history-search-forward'
done
unset hendrix_keymap

case :$PATH: in
    *:"$HOME/.local/bin":*) ;;
    *) export PATH="$HOME/.local/bin:$PATH" ;;
esac
if command -v zoxide >/dev/null 2>&1; then
    eval "$(zoxide init bash --cmd cd)"
fi
