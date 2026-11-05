# The Cade render worker image (docs/spec/RENDER_STAGE.md, "Worker image"; Linear TIN-7788, demo DAG P9):
#
#   nix build .#cade-render-worker-image      -> result, a docker-archive (dockerTools.buildLayeredImage)
#
# It runs the CPU phases of the render stage: intake, the AudioCppBatch plan, the prerendered render, the voice
# adoption, the stage graph to deliver_check and the result. It holds no GPU binary, no model, no record, no voice
# clip, no consent, no denylist, no kitpip binary and no credential: every private input mounts read-only at
# /inputs/<sha256> and the render stage re-hashes it there. The GPU window does not run in this image
# (docs/spec/RENDER_STAGE.md, "Lease protocol").
#
# The narrate and condense sources and program/ come from this repository at the flake's revision. `commit` is that
# revision, baked into VIDEO_UTILS_COMMIT, which the render stage compares with the request's video_utils_commit. A
# dirty tree has no revision, so the image sets no commit and verify_inputs and every result refuse commit_unknown.
#
# FFmpeg and whisper.cpp come from the condense nixpkgs pin (ffmpeg 8.1.2, whisper-cpp 1.8.4), the same tools the
# condense dev shell gives the narrate recipes. Built on demand, never by `just check`; nothing here pushes it.
{
  lib,
  dockerTools,
  runCommand,
  bash,
  coreutils,
  findutils,
  gnutar,
  util-linux,
  ffmpeg-headless,
  whisper-cpp,
  python3,
  src,
  commit ? null,
}: let
  fs = lib.fileset;
  tree = fs.toSource {
    root = src;
    fileset = fs.unions [
      (fs.fileFilter (f: f.name != "BUILD.bazel") (src + "/narrate"))
      (fs.fileFilter (f: f.hasExt "py") (src + "/condense"))
      (src + "/program")
    ];
  };
  share = runCommand "cade-render-worker-share" {} ''
    mkdir -p "$out/share"
    cp -r ${tree} "$out/share/video-utils"
    chmod -R u+w "$out/share/video-utils"
    rm -rf "$out/share/video-utils/narrate/tests"
  '';
  passwd = runCommand "cade-render-worker-passwd" {} ''
    mkdir -p "$out/etc"
    echo 'render:x:10001:10001:render:/work:/bin/sh' > "$out/etc/passwd"
    echo 'render:x:10001:' > "$out/etc/group"
  '';
in
  dockerTools.buildLayeredImage {
    name = "cade-render-worker";
    tag = if commit == null then "dirty" else commit;
    contents = [bash coreutils findutils gnutar util-linux ffmpeg-headless whisper-cpp python3 share passwd];
    extraCommands = ''
      mkdir -p work tmp inputs out
      chmod 1777 tmp
    '';
    # The customisation layer is root-owned unless fakeroot says otherwise. /work (HOME and the stage store) and
    # /out (the --export target) belong to the worker user, so user 10001 can write them without a volume. A volume
    # mounted over either must be writable by 10001 too. /inputs stays root-owned: its mounts are read-only.
    fakeRootCommands = ''
      chown 10001:10001 work out
      chmod 0755 work out inputs
    '';
    config = {
      User = "10001:10001";
      WorkingDir = "/work";
      # -s and PYTHONSAFEPATH keep user site-packages and the working directory off sys.path; PYTHONPATH names
      # the one tree. (-I would also drop PYTHONPATH.)
      Entrypoint = ["${python3}/bin/python3" "-s" "-B" "-m" "narrate" "video" "render-stage"];
      Env =
        [
          "PYTHONPATH=/share/video-utils"
          "PYTHONDONTWRITEBYTECODE=1"
          "PYTHONSAFEPATH=1"
          "NARRATED_VIDEO_ROOT=/work/narrated"
          "HOME=/work"
          "TMPDIR=/tmp"
        ]
        ++ lib.optional (commit != null) "VIDEO_UTILS_COMMIT=${commit}";
      Labels = {
        "org.opencontainers.image.source" = "https://github.com/Jesssullivan/video-utils";
        "org.opencontainers.image.revision" = if commit == null then "dirty" else commit;
      };
    };
  }
