# The GPU-host narrate bench image (TIN-7088, plan docs/agent-notes/2026-10-22-narrate-bench-plan.md):
# audio.cpp and qwentts.cpp at their pinned commits with the Vulkan backend, the Vulkan loader, Mesa (RADV for
# the card, lavapipe for a software smoke test), Python for the bench entrypoint and for staging weights with
# narrate/bench/fetch.py, and a non-root user. Every package comes from the flake-locked nixpkgs, so the lock
# pins Mesa; the image records its version in /etc/narrate-bench.json.
#
#   nix build .#narrate-bench-image      -> docker-archive .tar.gz, loadable with skopeo or `docker load`
#
# The image holds no weights, voices or bench text: the weights, the chunk list, the consented reference clip
# and the job files arrive on the GPU host's models volume under bench/narrate/ (deploy/narrate-bench/README.md).
# The pod contract asks for sh and tar: bash provides /bin/sh, GNU tar /bin/tar (kubectl exec tar, kubectl cp).
{pkgs}: let
  inherit (pkgs) lib;
  audiocpp = pkgs.callPackage ./audiocpp.nix {};
  qwentts = pkgs.callPackage ./qwentts.nix {};
  mesa = pkgs.mesa;
  icd = name: "${mesa}/share/vulkan/icd.d/${name}_icd.${pkgs.stdenv.hostPlatform.uname.processor}.json";
  python = pkgs.python3;

  # The bench files, copied from the repository so the image needs no checkout.
  bench = pkgs.runCommand "narrate-bench-files" {} ''
    mkdir -p $out/share/narrate-bench $out/bin
    cp ${./bench_arm.py} $out/share/narrate-bench/bench_arm.py
    cp ${../fetch.py} $out/share/narrate-bench/fetch.py
    cp ${../sources.json} $out/share/narrate-bench/sources.json
    cat > $out/bin/narrate-bench-arm <<EOF
    #!${pkgs.runtimeShell}
    exec ${python}/bin/python3 -I $out/share/narrate-bench/bench_arm.py "\$@"
    EOF
    cat > $out/bin/narrate-fetch <<EOF
    #!${pkgs.runtimeShell}
    exec ${python}/bin/python3 -I $out/share/narrate-bench/fetch.py --sources $out/share/narrate-bench/sources.json "\$@"
    EOF
    # The window pod's command (deploy/narrate-bench/bench-pod.yaml): the GPU host's window runner waits for
    # the NARRATE-BENCH-DONE line, streams /out with tar, then deletes the pod, so the pod lingers after it.
    cat > $out/bin/narrate-bench-window <<EOF
    #!${pkgs.runtimeShell}
    $out/bin/narrate-bench-arm run "\$@"
    rc=\$?
    echo "NARRATE-BENCH-DONE rc=\$rc"
    exec ${pkgs.coreutils}/bin/sleep "\''${NARRATE_LINGER_S:-600}"
    EOF
    chmod +x $out/bin/*
  '';

  uid = "10001";
  # A non-root user and group, and the render group the pod adds as a supplementary group.
  etc = pkgs.runCommand "narrate-bench-etc" {} ''
    mkdir -p $out/etc
    cat > $out/etc/passwd <<EOF
    root:x:0:0:root:/root:/bin/sh
    narrate:x:${uid}:${uid}:narrate bench:/tmp:/bin/sh
    nobody:x:65534:65534:nobody:/var/empty:/bin/sh
    EOF
    cat > $out/etc/group <<EOF
    root:x:0:
    narrate:x:${uid}:
    nobody:x:65534:
    EOF
    cat > $out/etc/narrate-bench.json <<EOF
    {"audiocpp": "47c2756ec72c4e67cad7fb762fd0d5f2798096fd",
     "qwentts": "5916bf7c79dbb4e66fc059cdc507a79a23a28bb4",
     "mesa": "${mesa.version}", "vulkan_loader": "${pkgs.vulkan-loader.version}",
     "python": "${python.version}", "user": ${uid}}
    EOF
  '';

  image = pkgs.dockerTools.buildLayeredImage {
    name = "narrate-bench";
    tag = "47c2756e-5916bf7c";
    contents = [
      audiocpp
      qwentts
      bench
      etc
      pkgs.vulkan-loader
      pkgs.vulkan-tools
      python
      pkgs.coreutils
      pkgs.bashInteractive
      pkgs.gnutar # kubectl cp needs tar in the container
      pkgs.cacert
    ];
    extraCommands = ''
      mkdir -p tmp out models
      chmod 1777 tmp
    '';
    config = {
      User = "${uid}:${uid}";
      WorkingDir = "/tmp";
      Entrypoint = ["/bin/narrate-bench-arm"];
      Cmd = ["versions"];
      Env = [
        "HOME=/tmp"
        "XDG_CACHE_HOME=/tmp/cache"
        "PATH=/bin"
        "SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.crt"
        # The bench chooses the ICD per job (vulkan_icd); RADV is the default for the card.
        "NARRATE_ICD_RADV=${icd "radeon"}"
        "NARRATE_ICD_LAVAPIPE=${icd "lvp"}"
        "VK_DRIVER_FILES=${icd "radeon"}"
        "MESA_SHADER_CACHE_DIR=/tmp/mesa-shader-cache"
      ];
      Labels = {
        "org.opencontainers.image.source" = "https://github.com/Jesssullivan/video-utils";
        "org.opencontainers.image.description" = "narrate GPU-host bench: audio.cpp + qwentts.cpp, Vulkan (RADV)";
      };
    };
  };
in {
  inherit audiocpp qwentts bench image;
}
