# livecode as a Nix package: `pkgs.callPackage ./livecode/package.nix { }`.
#
# A consumer calls this file with its own package set (and may pass its own
# `ffmpeg`), so it never needs this flake's nixpkgs. The flake exposes the same
# derivation as packages.<system>.livecode, and checks.<system>.livecode runs
# livecode/tests against it. writeShellApplication runs shellcheck on the body.
# The ffmpeg must carry the avfoundation input and h264_videotoolbox (nixpkgs'
# `ffmpeg` on Darwin does). There is no meta.platforms, so Linux builds and
# checks it against stubs; capture itself works only on macOS.
{
  lib,
  writeShellApplication,
  ffmpeg,
  coreutils,
  gawk,
  gnugrep,
  gnused,
}:
let
  version = "0.1.0";
  source = builtins.readFile ./livecode.sh;
  shebang = "#!/usr/bin/env bash\n";
in
assert lib.assertMsg (lib.hasPrefix shebang source) "livecode.sh must start with ${shebang}";
writeShellApplication {
  name = "livecode";
  runtimeInputs = [ ffmpeg coreutils gawk gnugrep gnused ];
  # writeShellApplication writes its own shebang and `set -o` line.
  text = lib.removePrefix shebang source;
  passthru = { inherit version; };
  meta = {
    description = "Screen + camera corner + mic recorder and RTMP streamer with plain ffmpeg (macOS)";
    license = lib.licenses.mit;
    mainProgram = "livecode";
  };
}
