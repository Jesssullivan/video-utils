{
  description = "Local-first guitar video restoration and rhythm analysis";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  # Talk condensing keeps the revision its edits were made with: ffmpeg 8.1.2, whisper-cpp 1.8.4.
  inputs.nixpkgs-condense.url = "github:NixOS/nixpkgs/7c8764b7c7b09b34f632464276218ef9090eaa11";

  outputs = { nixpkgs, nixpkgs-condense, ... }: let
    systems = [ "aarch64-darwin" "x86_64-linux" "aarch64-linux" ];
    forAllSystems = nixpkgs.lib.genAttrs systems;
  in {
    devShells = forAllSystems (system: let
      pkgs = import nixpkgs { inherit system; };
      core = with pkgs; [ rustc cargo rustfmt clippy ffmpeg-headless just jq python3 uv git gh gitleaks shellcheck ];
      analysisPython = pkgs.python3.withPackages (ps: with ps; [ numpy scipy librosa soundfile ]);
      # nixpkgs pairs quarto 1.10.x with pandoc 3.7.x, which rejects the
      # `syntax-highlighting` option quarto writes. Extract the pandoc that
      # upstream ships for this quarto from the same hash-pinned release
      # tarball nixpkgs already uses (pkgs.quarto.src). Report shell only.
      quartoBundledPandoc = pkgs.runCommand "quarto-${pkgs.quarto.version}-bundled-pandoc" {
        src = pkgs.quarto.src;
      } ''
        mkdir unpack "$out" "$out/bin"
        tar -xzf "$src" -C unpack
        t=$(find unpack -path "*/bin/tools/${pkgs.stdenv.hostPlatform.parsed.cpu.name}/pandoc" | head -n 1)
        [ -n "$t" ] || { echo "bundled pandoc not found in quarto tarball" >&2; exit 1; }
        [ -d "$t" ] && t="$t/pandoc"
        install -m 0755 "$t" "$out/bin/pandoc"
      '';
    in {
      # dhall and dhall-json render the narrate types (narrate/dhall, `just narrate-dhall-check`).
      default = pkgs.mkShell { packages = core ++ [ pkgs.dhall pkgs.dhall-json ]; CARGO_BUILD_JOBS = "1"; };
      analysis = pkgs.mkShell {
        packages = builtins.filter (p: p != pkgs.python3) core ++ [ analysisPython ];
        OMP_NUM_THREADS = "2";
        OPENBLAS_NUM_THREADS = "2";
      };
      # Web app checks (svelte-check, vitest, build, Playwright). pnpm switches itself to the
      # version pinned by web/package.json `packageManager`; no browser is provided here.
      web = pkgs.mkShell { packages = [ pkgs.nodejs_22 pkgs.pnpm pkgs.just pkgs.git ]; };
      # Talk condensing (condense/). The whisper model is registered in program/models.json and
      # fetched only by `just condense-model`; the shell never downloads it.
      condense = let
        cpkgs = import nixpkgs-condense { inherit system; };
      in cpkgs.mkShell {
        packages = with cpkgs; [
          ffmpeg-headless whisper-cpp just ruff git gitleaks rustc cargo
          # dhall and dhall-json: `just narrate-dhall-check` runs in the shell the narrate recipes use.
          dhall dhall-json
          (python3.withPackages (ps: with ps; [ numpy pytest ]))
        ] ++ cpkgs.lib.optional (cpkgs ? untrunc-anthwlock
          && cpkgs.lib.meta.availableOn cpkgs.stdenv.hostPlatform cpkgs.untrunc-anthwlock) cpkgs.untrunc-anthwlock;
        TALK_FONT = "${cpkgs.dejavu_fonts}/share/fonts/truetype/DejaVuSans-Bold.ttf";
        CARGO_BUILD_JOBS = "1";
      };
      report = pkgs.mkShell {
        packages = core ++ [ pkgs.R pkgs.quarto ];
        QUARTO_PANDOC = "${quartoBundledPandoc}/bin/pandoc";
      };
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
