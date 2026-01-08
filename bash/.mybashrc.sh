# ==========================================
# 1. STANDARD BASH SETTINGS
# ==========================================
HISTCONTROL=ignoreboth
shopt -s histappend
HISTSIZE=1000
HISTFILESIZE=2000
shopt -s checkwinsize
[ -x /usr/bin/lesspipe ] && eval "$(SHELL=/bin/sh lesspipe)"

# Enable colors
if [ -x /usr/bin/dircolors ]; then
    test -r ~/.dircolors && eval "$(dircolors -b ~/.dircolors)" || eval "$(dircolors -b)"
    alias ls='ls --color=auto'
    alias grep='grep --color=auto'
    alias fgrep='fgrep --color=auto'
    alias egrep='egrep --color=auto'
fi

# Standard ls aliases
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'
alias cl="clear"

# Set bash editor to Vi
set -o vi

# ==========================================
# 2. PROMPT (Green User / Blue Path)
# ==========================================
PS1='\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ '

# ==========================================
# 3. CLIPBOARD (Wayland)
# ==========================================
alias c='wl-copy'
alias v='wl-paste'

# ==========================================
# 4. CUSTOM ALIASES
# ==========================================
alias python='python3'

# Navigation Shortcuts (.. ... ....)
alias_str=".."
cmd_str="cd .."
for i in $(seq 1 10); do
    alias ${alias_str}="$cmd_str"
    alias_str="$alias_str."
    cmd_str="$cmd_str/.."
done

# Config & Project Shortcuts
alias brc="nvim $HOME/.mybashrc.sh"
alias brc.=". $HOME/.bashrc"
alias cd.="cd $HOME/.dotfiles"

# Wifi Toggle
alias oo="nmcli radio wifi off && sleep 1 && nmcli radio wifi on"

# Set Default Editor
export EDITOR="nvim"
export VISUAL="nvim"

export MANPAGER='nvim +Man!'

# Add HOME/.local/bin to PATH to place user scripts
export PATH="$HOME/.local/bin:$PATH"
# ==========================================
# 5. FUNCTIONS
# ==========================================

# tldrf (tldr flags) e.g. ls -alF -> it will show line by line those flags
tldrf () {
  # curl the explanation API with your command
  curl -Gs "https://www.mankier.com/api/explain/?cols=$(tput cols)" --data-urlencode "q=$*"
}

# Smart CD with Preview
cdd() {
    local dir
    local find_cmd="find . -maxdepth 4 -type d -not -path '*/.*'"
    
    # Check for fd (Arch) or fdfind (Debian)
    if command -v fd &> /dev/null; then 
        find_cmd="fd . $HOME --type d --hidden --exclude .git" 
    elif command -v fdfind &> /dev/null; then 
        find_cmd="fdfind . $HOME --type d --hidden --exclude .git" 
    fi

    dir=$(eval "$find_cmd" | fzf --preview 'eza --tree --level=1 --color=always {}' --preview-window=right:50%)

    if [[ -n "$dir" ]]; then
        cd "$dir"
    fi
}

# The Magic Install Function
function yaya() {
    local INSTALL_SCRIPT="$HOME/omarchy-supplement/install-all.sh" 
    local MARKER="# INSERT_HERE"
    
    for PACKAGE in "$@"; do
        echo "---------------------------------"
        echo "Attempting to install: $PACKAGE"
        yay -S "$PACKAGE"
        
        if pacman -Qi "$PACKAGE" &> /dev/null; then
            if grep -q "\"$PACKAGE\"" "$INSTALL_SCRIPT"; then
                echo "✅ Installed, but '$PACKAGE' is already in your install list."
            else
                sed -i "/$MARKER/i \    \"$PACKAGE\"" "$INSTALL_SCRIPT"
                echo "🎉 Success! Added '$PACKAGE' to your automation script."
            fi
        else
            echo "❌ Installation failed. NOT added to script."
        fi
    done
}

# Wacom Touchscreen Toggle (Arch Compatible)
WACOM_TOUCH_ID="0018:056A:5367.0003"
WACOM_DRIVER_PATH="/sys/bus/hid/drivers/wacom"

function ts_disable() {
    echo "Disabling Wacom Touchscreen..."
    if [ -d "$WACOM_DRIVER_PATH/$WACOM_TOUCH_ID" ]; then
        echo "$WACOM_TOUCH_ID" | sudo tee "$WACOM_DRIVER_PATH/unbind" >/dev/null
        echo "Touchscreen Disabled."
    else
        echo "Touchscreen already disabled."
    fi
}

function ts_enable() {
    echo "Enabling Wacom Touchscreen..."
    if [ ! -d "$WACOM_DRIVER_PATH/$WACOM_TOUCH_ID" ]; then
        echo "$WACOM_TOUCH_ID" | sudo tee "$WACOM_DRIVER_PATH/bind" >/dev/null
        echo "Touchscreen Enabled."
    else
        echo "Touchscreen already enabled."
    fi
}

# Fuzzy-find history and copy the selected command to the clipboard
history() {
  # This function avoids the complex quoting issues of an alias.
  builtin history | fzf --bind 'enter:execute-silent(echo {+} | awk '\''{$1=""; sub(/^ /, ""); print}'\'' | wl-copy)+abort'
}



# testt to see if ssh-agent and ssh-add is needed before adding
# --- SSH AGENT AUTOSTART ---
# if [ -z "$SSH_AUTH_SOCK" ]; then
#    # Check for a currently running instance of the agent
#    RUNNING_AGENT="`ps -ax | grep 'ssh-agent -s' | grep -v grep | wc -l | tr -d '[:space:]'`"
#    if [ "$RUNNING_AGENT" = "0" ]; then
#         # Launch a new instance of the agent
#         ssh-agent -s &> .ssh-agent
#    fi
#    eval `cat .ssh-agent` > /dev/null
#    ssh-add ~/.ssh/id_ed25519 2>/dev/null
# fi
