{ config, pkgs, ... }:

{
  home.username = "hjalte"; 
  home.homeDirectory = "/home/hjalte/"; 

  # Packages you want installed just for your user
  home.packages = with pkgs; [
    neovim
    git
    ripgrep  # LazyVim needs this
    fd       # LazyVim needs this
    gcc      # Needed for Treesitter
    xclip    # Clipboard support
  ];

  # This tells Home Manager to take your LazyVim folder and symlink it
  # into ~/.config/nvim.
  home.file.".config/nvim" = {
    source = ./nvim; # We will put your LazyVim config in ~/.dotfiles/nvim
    recursive = true;
  };

  # Let Home Manager install and manage itself.
  programs.home-manager.enable = true;

  # Don't change this without reading the Home Manager release notes!
  home.stateVersion = "23.11"; 
}

