# Compatibility loader for older aliases such as `brc.`.
#
# Home Manager now links and sources these files directly:
# - ~/.bash_common.sh
# - ~/.bash_desktop.sh on the desktop host
# - ~/.bash_mobile_dev.sh on the mobile-dev host

if [ -f "$HOME/.bash_common.sh" ]; then
  source "$HOME/.bash_common.sh"
fi

if [ -f "$HOME/.bash_desktop.sh" ]; then
  source "$HOME/.bash_desktop.sh"
fi

if [ -f "$HOME/.bash_mobile_dev.sh" ]; then
  source "$HOME/.bash_mobile_dev.sh"
fi
