---
name: livecode
description: Set up and explain livecode, the operator's screen + camera + mic practice capture.
---

# Help the operator set up and use livecode for practice and live-coding capture.

**Hook:** none, by design. livecode has no MCP tool and no `program/tools.json` entry. Agents never start screen, camera or microphone capture: not through livecode, not through ffmpeg, and not through a wrapper. The operator starts every capture. The reason is recorded in AGENTS.md, "Practice capture".

**Capability:** The operator runs `livecode preview`, `livecode rec` or `livecode stream` in a terminal on macOS. livecode captures the screen with the cursor, puts the built-in camera in one corner, and adds the macOS default audio input. It either records MKV under `LIVECODE_DIR/recordings` or streams FLV to RTMP, encoding with `h264_videotoolbox`. The MKV is a practice take for take intake.

## What an agent may do

- Explain usage from `livecode -h` and `livecode/README.md`.
- Run `livecode --version` and `livecode -h`. Neither opens a device.
- Help write the deploying side's configuration: `LIVECODE_DIR` and, optionally, `LIVECODE_VOLUME_UUID`, set by a Home Manager module or a shell profile. A UUID comes from the operator, who reads it from `diskutil info <mount>`.
- After the operator has recorded, hand the file to take intake (`just take-plan SOURCE`). Do not copy it into the checkout.
- Run the contract test: `just livecode-check`, or `bazel test //livecode:livecode_test`.

## What an agent must not do

- Run `livecode rec`, `livecode stream`, `livecode preview` or `livecode devices`. `preview` captures a frame and opens a Quick Look window, and `devices` opens avfoundation, which can raise privacy prompts.
- Run ffmpeg with an avfoundation input.
- Grant, reset or edit Screen Recording, Camera or Microphone permission.
- Set `LIVECODE_ALLOW_INTERNAL=1` on the operator's behalf.
- Read, print or store a stream URL or key.

## Setup checklist for the operator

1. Install it. With Nix, use `pkgs.callPackage <video-utils>/livecode/package.nix { }` or the flake's `packages.<system>.livecode`. Otherwise use bash 4 or newer plus an ffmpeg with avfoundation and VideoToolbox.
2. Set `LIVECODE_DIR` to a directory on an external volume. Optionally pin that volume with `LIVECODE_VOLUME_UUID`.
3. Run `livecode devices` once and check the screen, camera and audio input it picks. The `LIVECODE_SCREEN` and `LIVECODE_CAMERA` patterns override the first two. Audio is always the macOS default input, chosen in System Settings > Sound > Input; Bluetooth earphones work there, at headset-profile quality. Then run `livecode preview` to check the composed frame.
4. On the first `livecode rec`, macOS asks for Screen Recording, Camera and Microphone permission for the terminal app. Grant them, quit and reopen that app, then run it again.
5. For streaming, put the RTMP URL in a file with mode 600 and point `LIVECODE_RTMP_URL_FILE` at it, or use `~/.config/livecode/rtmp-url`.

## Limits

- macOS only. On Linux it builds and passes its stub tests, but it cannot capture.
- livecode refuses the internal disk, an unmounted volume and, when pinned, any other volume. It refuses before it creates anything, and there is no fallback location.
- The stub tests prove the ffmpeg argv, the refusals and the redaction. Only an operator's live run proves capture, encoding and permissions.

## Agent iteration

When a recording looks wrong, read the operator's `livecode devices` output and the ffmpeg stderr they paste. Propose a knob change: the device pattern, `LIVECODE_CAM_SIZE`, `LIVECODE_WIDTH`, `LIVECODE_FPS` or the bitrates. The operator runs the next capture.
