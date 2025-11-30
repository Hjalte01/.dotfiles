#!/bin/bash
# --- CONFIGURE BASH ---
echo "Configuring Bash..."

# 1. Define where your custom file lives
MY_BASH_CONFIG="$HOME/.mybashrc.sh"
MAIN_BASHRC="$HOME/.bashrc"

# 2. Check if your custom file actually exists
if [ -f "$MY_BASH_CONFIG" ]; then
    
    # 3. Check if we have already added the source line to .bashrc
    # grep -Fq searches for the fixed string silently
    if grep -Fq "source $MY_BASH_CONFIG" "$MAIN_BASHRC"; then
        echo "✔ .bashrc is already sourcing your custom config."
    else
        # 4. Append the source command to the END of .bashrc
        echo "" >> "$MAIN_BASHRC"
        echo "# Load custom Omarchy configuration" >> "$MAIN_BASHRC"
        echo "source \"$MY_BASH_CONFIG\"" >> "$MAIN_BASHRC"
        
        echo "✔ Added source command to .bashrc"
    fi
else
    echo "❌ Error: Could not find $MY_BASH_CONFIG"
fi
