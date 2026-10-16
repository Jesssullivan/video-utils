# livecode

`livecode` records or streams a practice or live-coding session with plain
FFmpeg. It captures the screen (with cursor), puts the built-in camera in one
corner at a quarter of the frame width, adds the macOS default audio input, and
either records to MKV (crash-safe) or streams FLV to RTMP. `livecode preview`
shows one frame of the composed output in Quick Look first. Encoding is
`h264_videotoolbox`, and the filter graph is one scale per input plus one
overlay. It runs on macOS only, because it needs the avfoundation input,
VideoToolbox and `diskutil`.

## Where it fits

livecode is a capture source for the practice/clip workflow in the product
axioms. It turns a woodshedding or practice take, with the hands on camera and
the tab, DAW or editor on screen, into one MKV, which goes to take intake (`just
take-plan`) like any other recording. livecode does no restoration or analysis,
and it never writes into the checkout, so original recordings stay out of Git.

It is an operator tool, not an agent tool. It has a skill
(`.agents/skills/livecode/`) and no MCP hook, because agents never start screen,
camera or microphone capture (AGENTS.md, "Practice capture").

## Install

- Nix: `pkgs.callPackage ./livecode/package.nix { }`, optionally with your own
  `ffmpeg`, or the flake's `packages.<system>.livecode`. FFmpeg comes from
  `runtimeInputs`.
- Anywhere else: run `livecode/livecode.sh` with bash 4 or newer and an `ffmpeg`
  on `PATH` (or set `LIVECODE_FFMPEG`). The ffmpeg needs avfoundation and
  `h264_videotoolbox`; nixpkgs' `ffmpeg` on Darwin has both.

## Use

```sh
livecode devices                # avfoundation devices and what the defaults pick
livecode preview [--watch [S]]  # one 960 px composed frame in Quick Look; needs LIVECODE_DIR
livecode rec [FILE]             # needs LIVECODE_DIR
livecode stream [URL]           # URL from the argument, the environment or a file pointer
livecode --version
```

Stop `rec` or `stream` with `q` or Ctrl-C. livecode finalises the file and
prints its path. `livecode -h` lists every knob: camera corner and size, screen
and camera patterns, output width, frame rate and bitrates.

The audio input is always the macOS system default input (System Settings >
Sound > Input), read from `system_profiler` each time livecode starts. There is
no audio knob. If livecode can't match the default input to an avfoundation
device, it stops rather than picking another microphone. Bluetooth earphones
work once they are selected as the default input, but macOS then switches them
to the lower-quality headset profile.

## Storage

- `LIVECODE_DIR` is required. Recordings go to `LIVECODE_DIR/recordings`, and
  FFmpeg's `TMPDIR` to `LIVECODE_DIR/scratch`. There is no default and no
  fallback to `~/Movies`.
- A target on the internal disk is refused. That covers a mount point of `/`, a
  volume that `diskutil` reports as internal, and the mount point of a volume
  that isn't mounted. `LIVECODE_ALLOW_INTERNAL=1` is the only opt-out.
- `LIVECODE_VOLUME_UUID`, when set, pins the volume. A target on any other
  volume is refused, even when internal targets are allowed.
- Every check runs before anything is created. livecode warns when free space
  drops below `LIVECODE_MIN_FREE_GIB` (default 50).

This package carries no host's paths or volume identity. The deploying side, for
example a Home Manager module that wraps the package, supplies `LIVECODE_DIR`
and `LIVECODE_VOLUME_UUID`.

## Stream keys

The RTMP URL is the first one set of: the argument, `LIVECODE_RTMP_URL`, the file
named by `LIVECODE_RTMP_URL_FILE`, or `~/.config/livecode/rtmp-url`. livecode
never prints it, and it redacts the URL and its key segment from FFmpeg's
output.

## Permissions

On the first live run, macOS asks for Screen Recording, Camera and Microphone
permission for the terminal app. Granting them is an operator click; livecode
never touches TCC.

## Tests

```sh
just livecode-check
bazel test //livecode:livecode_test
nix build .#checks.<system>.livecode
```

`tests/test_livecode.py` gets the script from `LIVECODE_UNDER_TEST`. It stubs
`ffmpeg`, `df`, `diskutil`, `system_profiler` and `qlmanage` through their
`LIVECODE_*` hooks, so it needs no camera, FFmpeg or macOS. It pins:

- the filter graph and the encoder
- device and default-input resolution
- the preview frame
- every storage refusal
- stream-key redaction

Bazel runs the test against the source script, and the Nix check runs it against
the built package. Building the package also runs shellcheck.

## Version

The shard version is `passthru.version` in `package.nix`, independent of the
root crate. The script's `--version` and the CHANGELOG row carry the same
number, and `tests/test_bazel_graph_s3.py` holds the three together.
