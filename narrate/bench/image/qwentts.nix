# qwentts.cpp at the commit narrate/bench/sources.json pins, with its ggml submodule at the commit that
# qwentts.cpp records, built with the Vulkan backend for the GPU-host bench arm A2-gpu-alt (Qwen3-TTS
# 1.7B Base, ICL cloning with ref_audio and ref_text).
#
# Two source edits, both mechanical:
# - tools/version.cmake asks git for the commit, which the sandbox has no repository for; the pinned commit
#   is written instead, so `qt_version()` still names it.
# - src/backend.h sizes the GGML CPU thread pool from hardware_concurrency()/2, which inside a pod is the
#   whole host. QWENTTS_CPU_THREADS bounds it, the same rule as the CPU engine lane's patch.
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
}: let
  rev = "5916bf7c79dbb4e66fc059cdc507a79a23a28bb4";
  ggml = fetchFromGitHub {
    owner = "ServeurpersoCom";
    repo = "ggml";
    rev = "cc5df49a6b878db2b68b9a7b45976e279594627d";
    hash = "sha256-3c0ou6N2Nf7ao125jPW9EnOvX2hT76h7fDM7GFrr2Ls=";
  };
in
  stdenv.mkDerivation {
    pname = "qwentts-vulkan";
    version = "0-unstable-5916bf7c";

    src = fetchFromGitHub {
      owner = "ServeurpersoCom";
      repo = "qwentts.cpp";
      inherit rev;
      hash = "sha256-7WxZPJ8SSNXqFqqCAjHt2RgfWOWrlBkdSCHzIjmxRe4=";
    };

    postPatch = ''
      cat > tools/version.cmake <<'EOF'
      file(WRITE "''${OUTPUT}" "#pragma once\n#define QWEN_VERSION \"${builtins.substring 0 7 rev} (pinned)\"\n")
      EOF
      substituteInPlace src/backend.h --replace-fail \
        'static int backend_cpu_n_threads(void) {' \
        'static int backend_cpu_n_threads(void) {
          if (const char * env = std::getenv("QWENTTS_CPU_THREADS")) { int v = std::atoi(env); if (v > 0) { return v; } }'
    '';

    nativeBuildInputs = [cmake ninja pkg-config python3 shaderc glslang];
    buildInputs = [vulkan-headers vulkan-loader spirv-headers];

    cmakeFlags = [
      "-DCMAKE_BUILD_TYPE=Release"
      "-DGGML_SOURCE_DIR=${ggml}"
      # Static ggml: the tools then carry no RPATH into the build tree.
      "-DBUILD_SHARED_LIBS=OFF"
      "-DGGML_VULKAN=ON"
      "-DGGML_NATIVE=OFF"
      "-DGGML_CUDA=OFF"
      "-DGGML_METAL=OFF"
      "-DGGML_BLAS=OFF"
    ];

    ninjaFlags = ["tts-server" "qwen-tts" "qwen-codec"];

    installPhase = ''
      runHook preInstall
      for b in tts-server qwen-tts qwen-codec; do install -Dm755 "$b" "$out/bin/$b"; done
      runHook postInstall
    '';

    meta = {
      description = "qwentts.cpp (Qwen3-TTS) tts-server and CLI with the Vulkan backend, pinned for the narrate bench";
      homepage = "https://github.com/ServeurpersoCom/qwentts.cpp";
      license = lib.licenses.mit;
      platforms = lib.platforms.linux;
      mainProgram = "tts-server";
    };
  }
