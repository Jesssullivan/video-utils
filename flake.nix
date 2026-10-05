{
  description = "Local-first guitar video restoration and rhythm analysis";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { nixpkgs, ... }: let
    systems = [ "aarch64-darwin" "x86_64-linux" "aarch64-linux" ];
    forAllSystems = nixpkgs.lib.genAttrs systems;
  in {
    devShells = forAllSystems (system: let
      pkgs = import nixpkgs { inherit system; };
      core = with pkgs; [ rustc cargo rustfmt clippy ffmpeg-headless just jq python3 uv git gh gitleaks shellcheck ];
      analysisPython = pkgs.python3.withPackages (ps: with ps; [ numpy scipy librosa soundfile ]);
    in {
      default = pkgs.mkShell { packages = core; CARGO_BUILD_JOBS = "1"; };
      analysis = pkgs.mkShell {
        packages = builtins.filter (p: p != pkgs.python3) core ++ [ analysisPython ];
        OMP_NUM_THREADS = "2";
        OPENBLAS_NUM_THREADS = "2";
      };
      report = pkgs.mkShell { packages = core ++ [ pkgs.R pkgs.quarto ]; };
    } // pkgs.lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux {
      # Heavy optional dependencies are excluded from ordinary development.
      ml = pkgs.mkShell {
        packages = builtins.filter (p: p != pkgs.python3) core ++ [
          (pkgs.python3.withPackages (ps: with ps; [ numpy scipy librosa soundfile torch torchaudio ]))
        ];
        OMP_NUM_THREADS = "2";
        OPENBLAS_NUM_THREADS = "2";
        MKL_NUM_THREADS = "2";
      };
    });
    formatter = forAllSystems (system: nixpkgs.legacyPackages.${system}.alejandra);
  };
}
