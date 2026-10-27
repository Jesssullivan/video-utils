# audio.cpp at the commit narrate/bench/sources.json pins, built with the Vulkan backend:
#
#   nix build .#narrate-bench-audiocpp      -> result/bin/audiocpp_cli
#
# It is the reproducible source of the binary that narrate/serve/audiocpp_batch.py hashes against
# --binary-sha256: the `audiocpp_cli` entry of an AudioCppBatch engine record (docs/spec/NARRATE.md,
# "Out-of-process batch engines") and the host bench's NARRATE_BENCH_AUDIOCPP_CLI. Only the CLI is built,
# with the ming3_tts and voxcpm2 targets; one process per voice runs a --request-sequence.
#
# Portable CPU code (ENGINE_ENABLE_NATIVE_CPU=OFF): the build host is not the GPU host, so host ISA flags
# would risk an illegal instruction there. Model specs are compiled in (AUDIOCPP_DEPLOYMENT_BUILD), so the
# binary needs no model_specs directory beside it. The server-frontends submodule is not fetched;
# AUDIOCPP_BUILD_SERVER_FRONTENDS stays OFF and the CLI does not use it.
{
  lib,
  stdenv,
  fetchFromGitHub,
  cmake,
  ninja,
  pkg-config,
  python3,
  vulkan-headers,
  vulkan-loader,
  glslang,
  shaderc,
  spirv-headers,
  llvmPackages,
}:
stdenv.mkDerivation {
  pname = "audiocpp-vulkan";
  version = "0-unstable-47c2756e";

  src = fetchFromGitHub {
    owner = "0xShug0";
    repo = "audio.cpp";
    rev = "47c2756ec72c4e67cad7fb762fd0d5f2798096fd";
    hash = "sha256-zPfI1I5MduGtM6FjG7cL1ri/w0VL+91GNp2QtPGb1yk=";
  };

  nativeBuildInputs = [cmake ninja pkg-config python3 shaderc glslang];
  buildInputs = [vulkan-headers vulkan-loader spirv-headers] ++ lib.optional stdenv.cc.isClang llvmPackages.openmp;

  cmakeFlags = [
    "-DCMAKE_BUILD_TYPE=Release"
    "-DAUDIOCPP_VERSION=47c2756e"
    "-DAUDIOCPP_DEPLOYMENT_BUILD=ON"
    "-DAUDIOCPP_MODEL_SET=custom"
    "-DAUDIOCPP_MODELS=ming3_tts,voxcpm2"
    "-DAUDIOCPP_BUILD_NATIVE_MODEL_MANAGER=OFF"
    "-DAUDIOCPP_BUILD_SERVER_FRONTENDS=OFF"
    "-DENGINE_ENABLE_VULKAN=ON"
    "-DENGINE_ENABLE_NATIVE_CPU=OFF"
    "-DENGINE_ENABLE_CUDA=OFF"
    "-DENGINE_ENABLE_HIP=OFF"
  ];

  # The CLI only; the server, converter and model manager are not built.
  ninjaFlags = ["audiocpp_cli"];

  installPhase = ''
    runHook preInstall
    install -Dm755 bin/audiocpp_cli $out/bin/audiocpp_cli
    runHook postInstall
  '';

  meta = {
    description = "audio.cpp CLI (ming3_tts, voxcpm2) with the Vulkan backend, pinned for narrate";
    homepage = "https://github.com/0xShug0/audio.cpp";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "audiocpp_cli";
  };
}
