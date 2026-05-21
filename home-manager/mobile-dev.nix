{...}: {
  imports = [
    ./common.nix
  ];

  home.file = {
    ".bash_mobile_dev.sh".source = ../bash/mobile-dev.sh;
  };

  programs.bash.initExtra = ''
    if [ -f ~/.bash_mobile_dev.sh ]; then
      source ~/.bash_mobile_dev.sh
    fi
  '';
}
