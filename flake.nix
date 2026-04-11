{
  description = "My reproducible NixOS system";

  inputs = {
    # The main NixOS repository
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable"; # or "nixos-23.11" for stable

    # Home Manager, for handling dotfiles
    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, home-manager, ... }@inputs: {
    nixosConfigurations = {
      # REPLACE "myhostname" with your actual PC's hostname!
      myhostname = nixpkgs.lib.nixosSystem {
        system = "x86_64-linux";
        modules = [
          ./nixos/hardware-configuration.nix
          ./nixos/configuration.nix
          
          # Setup Home Manager as a module
          home-manager.nixosModules.home-manager
          {
            home-manager.useGlobalPkgs = true;
            home-manager.useUserPackages = true;
            # REPLACE "yourusername" with your actual linux username!
            home-manager.users.yourusername = import ./home-manager/home.nix;
          }
        ];
      };
    };
  };
}
