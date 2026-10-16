#!/usr/bin/env bash
# livecode: screen + camera overlay + mic, recorded to MKV or streamed to RTMP,
# with plain ffmpeg (avfoundation input, h264_videotoolbox). macOS only.
# livecode/README.md describes the package; `livecode -h` is the usage.
set -o errexit -o nounset -o pipefail

LIVECODE_VERSION="0.1.0"
# Host probes are hooks, so a wrapper's PATH can never shadow a test stub.
FFMPEG="${LIVECODE_FFMPEG:-ffmpeg}"
DISKUTIL="${LIVECODE_DISKUTIL:-/usr/sbin/diskutil}"
DF="${LIVECODE_DF:-df}"
SYSTEM_PROFILER="${LIVECODE_SYSTEM_PROFILER:-/usr/sbin/system_profiler}"
QLMANAGE="${LIVECODE_QLMANAGE:-/usr/bin/qlmanage}"
PREVIEW_WIDTH=960
# Recordings and scratch go under LIVECODE_DIR, which has no default: the
# caller (a Home Manager module, a wrapper or the shell) sets it, so no host's
# paths or volume identity live in this file. An internal disk is refused
# unless LIVECODE_ALLOW_INTERNAL=1; LIVECODE_VOLUME_UUID, when set, pins the
# volume.
LIVECODE_DIR="${LIVECODE_DIR:-}"
VOLUME_UUID="${LIVECODE_VOLUME_UUID:-}"
ALLOW_INTERNAL="${LIVECODE_ALLOW_INTERNAL:-0}"
MIN_FREE_GIB="${LIVECODE_MIN_FREE_GIB:-50}"

usage() {
  cat <<'EOF'
livecode: minimal live-coding capture (screen + camera corner + mic) with ffmpeg

Usage:
  livecode devices                 list avfoundation devices and what the defaults pick
  livecode rec [FILE]              record; default $LIVECODE_DIR/recordings/livecode-<UTC stamp>.mkv
  livecode stream [RTMP-URL]       stream to RTMP (FLV)
  livecode preview [--watch [S]]   one 960 px frame of the composed output, shown in
                                   Quick Look; --watch re-grabs every S seconds [5]
  livecode --version
  livecode -h | --help

Stop rec/stream with q or Ctrl-C; the file is finalised and its path printed.
Stop preview --watch with Ctrl-C. The preview is $LIVECODE_DIR/scratch/preview.png.

Operator use only: rec, stream and preview capture the screen and camera, and
preview opens a Quick Look window. Agents never start them (video-utils
AGENTS.md, "Practice capture").

Audio input: the macOS system default input device at each start (System
Settings > Sound > Input, or the menu bar). AirPods work when selected there,
but macOS then uses the Bluetooth headset profile, so audio quality drops.
There is no audio knob; if the default input cannot be matched to an
avfoundation device, livecode stops instead of picking another mic.

Stream URL, first one set wins (never printed; redacted from ffmpeg output):
  the RTMP-URL argument, $LIVECODE_RTMP_URL, the file named by
  $LIVECODE_RTMP_URL_FILE, ~/.config/livecode/rtmp-url

Storage (LIVECODE_DIR is required for rec, stream and preview; no default):
  LIVECODE_DIR=PATH                recordings go to PATH/recordings, ffmpeg's TMPDIR to PATH/scratch
  LIVECODE_VOLUME_UUID=UUID        if set, every target must be on the volume with this UUID
  LIVECODE_ALLOW_INTERNAL=1        allow a target on the internal disk [refused]
  LIVECODE_MIN_FREE_GIB=N          warn under N GiB free [50]
livecode checks every target before it creates anything. A target on the
internal disk (or under an unmounted volume's mount point) is refused, and so
is another volume when LIVECODE_VOLUME_UUID is set. There is no fallback to
~/Movies.

Hooks for the host tools: LIVECODE_FFMPEG [ffmpeg], LIVECODE_DF [df],
LIVECODE_DISKUTIL [/usr/sbin/diskutil], LIVECODE_SYSTEM_PROFILER
[/usr/sbin/system_profiler], LIVECODE_QLMANAGE [/usr/bin/qlmanage].

Environment (defaults in brackets):
  LIVECODE_CAM=br|bl|tr|tl         camera corner [br]
  LIVECODE_CAM_FRAC=N              camera width = output width / N [4]
  LIVECODE_MARGIN=PX               camera margin from the edges [24]
  LIVECODE_SCREEN=IDX|REGEX        screen device [Capture screen 0]
  LIVECODE_CAMERA=IDX|REGEX|none   camera device [FaceTime|MacBook.*Camera|Built-in.*Camera]
  LIVECODE_CAM_SIZE=WxH            camera capture size [1280x720]
  LIVECODE_WIDTH=PX                output width [1920]
  LIVECODE_FPS=N                   frame rate [30]
  LIVECODE_REC_BITRATE / LIVECODE_STREAM_BITRATE  video bitrate [6M / 4500k]
  A name REGEX is an extended regex matched against `livecode devices` names;
  iPhone Continuity and Desk View devices are skipped unless named exactly.

First run: macOS asks for Screen Recording, Camera and Microphone permission
for the terminal app; grant them, quit and reopen that app, then rerun.
EOF
}

die() { printf 'livecode: %s\n' "$*" >&2; exit 1; }
warn() { printf 'livecode: warning: %s\n' "$*" >&2; }

# Value after <key>KEY</key> in `diskutil info -plist` output: a string, true or false.
plist_value() {
  awk -v k="<key>$1</key>" '
    found { gsub(/^[ \t]+|[ \t]+$/, ""); sub(/^<string>/, ""); sub(/<\/string>$/, "")
            sub(/^</, ""); sub(/\/>$/, ""); print; exit }
    index($0, k) { found = 1 }'
}

# check_target DIR: DIR (existing or not) must not be on the internal disk
# (unless allowed) and, when VOLUME_UUID is set, must be on that volume.
# Checked BEFORE mkdir, so an unmounted volume's mount point can never be
# recreated as a plain directory on the internal disk.
check_target() {
  local dir="$1" probe mnt info uuid internal avail
  probe="$dir"
  while [ ! -e "$probe" ]; do probe="$(dirname "$probe")"; done
  mnt="$("$DF" -P "$probe" | awk 'NR == 2 { print $NF }')"
  [ -n "$mnt" ] || die "refusing $dir: cannot find the mount point of $probe"
  if [ "$ALLOW_INTERNAL" != 1 ] || [ -n "$VOLUME_UUID" ]; then
    if [ "$ALLOW_INTERNAL" != 1 ] && [ "$mnt" = / ]; then
      die "refusing $dir: it is on the internal disk (mount /). Is the capture volume mounted? (LIVECODE_ALLOW_INTERNAL=1 allows it)"
    fi
    info="$("$DISKUTIL" info -plist "$mnt" 2>/dev/null)" || die "refusing $dir: cannot identify the volume mounted at $mnt"
    internal="$(printf '%s\n' "$info" | plist_value Internal)"
    uuid="$(printf '%s\n' "$info" | plist_value VolumeUUID)"
    if [ "$ALLOW_INTERNAL" != 1 ] && [ "$internal" != false ]; then
      die "refusing $dir: the volume at $mnt is an internal disk, or diskutil did not say (LIVECODE_ALLOW_INTERNAL=1 allows it)"
    fi
    if [ -n "$VOLUME_UUID" ] && [ "$uuid" != "$VOLUME_UUID" ]; then
      die "refusing $dir: the volume at $mnt is '$uuid', expected $VOLUME_UUID (LIVECODE_VOLUME_UUID)"
    fi
  fi
  avail="$("$DF" -Pk "$mnt" | awk 'NR == 2 { print $4 }')"
  case "$avail" in ''|*[!0-9]*) warn "could not read free space on $mnt" ;;
    *) [ "$avail" -ge $(( MIN_FREE_GIB * 1024 * 1024 )) ] || warn "only $(( avail / 1024 / 1024 )) GiB free on $mnt (under $MIN_FREE_GIB GiB)" ;;
  esac
}

# prepare_storage [DIR...]: check scratch plus any output dirs, then create
# them and point ffmpeg's TMPDIR at scratch.
prepare_storage() {
  local d
  [ -n "$LIVECODE_DIR" ] || die "set LIVECODE_DIR to a directory on the capture volume (see livecode -h)"
  case "$LIVECODE_DIR" in /*) ;; *) die "LIVECODE_DIR must be an absolute path" ;; esac
  case "$MIN_FREE_GIB" in ''|*[!0-9]*) die "LIVECODE_MIN_FREE_GIB must be an integer" ;; esac
  for d in "$LIVECODE_DIR/scratch" "$@"; do check_target "$d"; done
  for d in "$LIVECODE_DIR/scratch" "$@"; do mkdir -p "$d"; done
  export TMPDIR="$LIVECODE_DIR/scratch"
}

DEVICE_LIST=""
device_list() {
  # ffmpeg exits non-zero after listing (there is no real input); that is expected.
  if [ -z "$DEVICE_LIST" ]; then
    DEVICE_LIST="$("$FFMPEG" -hide_banner -f avfoundation -list_devices true -i "" 2>&1 || true)"
  fi
  printf '%s\n' "$DEVICE_LIST"
}

# devices_of video|audio -> "IDX<TAB>NAME" lines
devices_of() {
  device_list | awk -v want="$1" '
    /AVFoundation video devices:/ { section = "video"; next }
    /AVFoundation audio devices:/ { section = "audio"; next }
    section == want && match($0, /\] \[[0-9]+\] /) {
      entry = substr($0, RSTART + 2)
      idx = entry; sub(/\].*/, "", idx); sub(/^\[/, "", idx)
      name = entry; sub(/^\[[0-9]+\] /, "", name)
      print idx "\t" name
    }'
}

# resolve video|audio SPEC -> index (or "none")
resolve() {
  local kind="$1" spec="$2" idx name
  case "$spec" in
    none) echo none; return 0 ;;
    *[!0-9]*|"") ;;
    *) echo "$spec"; return 0 ;;
  esac
  while IFS="$(printf '\t')" read -r idx name; do
    if [ "$name" = "$spec" ]; then echo "$idx"; return 0; fi
  done < <(devices_of "$kind")
  while IFS="$(printf '\t')" read -r idx name; do
    case "$name" in *iPhone*|*"Desk View"*) continue ;; esac
    if printf '%s\n' "$name" | grep -Eiq -- "$spec"; then echo "$idx"; return 0; fi
  done < <(devices_of "$kind")
  return 1
}

SCREEN_SPEC="${LIVECODE_SCREEN:-Capture screen 0}"
CAMERA_SPEC="${LIVECODE_CAMERA:-FaceTime|MacBook.*Camera|Built-in.*Camera}"

# Name of the macOS system default input device, from system_profiler's JSON
# (keys are sorted, so each device's "_name" precedes its other keys).
default_input_name() {
  "$SYSTEM_PROFILER" -json SPAudioDataType 2>/dev/null | awk '
    /"_name" : "/ { name = $0; sub(/^[^:]*: "/, "", name); sub(/",?[ \t]*$/, "", name) }
    /"coreaudio_default_audio_input_device" : "spaudio_yes"/ { print name; found = 1; exit }
    END { if (!found) exit 1 }'
}

# MIC_INDEX / MIC_NAME: the avfoundation audio index of the system default input.
MIC_INDEX="" MIC_NAME=""
resolve_mic() {
  local idx name
  MIC_NAME="$(default_input_name)" || die "could not read the macOS default input device (system_profiler SPAudioDataType)"
  while IFS="$(printf '\t')" read -r idx name; do
    if [ "$name" = "$MIC_NAME" ]; then MIC_INDEX="$idx"; return 0; fi
  done < <(devices_of audio)
  die "the macOS default input '$MIC_NAME' has no avfoundation audio device (see: livecode devices); choose another input in System Settings > Sound"
}

cmd_devices() {
  devices_of video | sed 's/^/video  /'
  devices_of audio | sed 's/^/audio  /'
  printf 'defaults: screen=%s camera=%s audio input=%s\n' \
    "$(resolve video "$SCREEN_SPEC" || echo '?')" \
    "$(resolve video "$CAMERA_SPEC" || echo '?')" \
    "$( (resolve_mic && printf '%s (%s, macOS default input)' "$MIC_INDEX" "$MIC_NAME") 2>&1 || true)"
}

# build_args av|preview: fills the global ARGS array with ffmpeg input, filter
# and (for av) encoder args. preview is the same composition at PREVIEW_WIDTH,
# video only, with no encoder settings.
ARGS=()
build_args() {
  local mode="${1:-av}" screen camera mic=none fps width frac margin cam_w pos
  screen="$(resolve video "$SCREEN_SPEC")" || die "no screen device matches '$SCREEN_SPEC' (see: livecode devices)"
  camera="$(resolve video "$CAMERA_SPEC")" || die "no camera matches '$CAMERA_SPEC' (set LIVECODE_CAMERA=none to skip)"
  [ "$screen" != none ] || die "a screen device is required"
  resolve_mic
  printf 'livecode: audio input: %s (macOS default input)\n' "$MIC_NAME" >&2
  [ "$mode" = preview ] || mic="$MIC_INDEX"
  fps="${LIVECODE_FPS:-30}"
  width="${LIVECODE_WIDTH:-1920}"
  frac="${LIVECODE_CAM_FRAC:-4}"
  margin="${LIVECODE_MARGIN:-24}"
  case "$fps$width$frac$margin" in *[!0-9]*) die "LIVECODE_FPS/WIDTH/CAM_FRAC/MARGIN must be integers" ;; esac
  [ "$frac" -ge 1 ] || die "LIVECODE_CAM_FRAC must be >= 1"
  if [ "$mode" = preview ]; then
    margin=$(( margin * PREVIEW_WIDTH / width ))
    width="$PREVIEW_WIDTH"
  fi
  cam_w=$(( width / frac / 2 * 2 ))
  case "${LIVECODE_CAM:-br}" in
    br) pos="x=W-w-${margin}:y=H-h-${margin}" ;;
    bl) pos="x=${margin}:y=H-h-${margin}" ;;
    tr) pos="x=W-w-${margin}:y=${margin}" ;;
    tl) pos="x=${margin}:y=${margin}" ;;
    *) die "LIVECODE_CAM must be br, bl, tr or tl" ;;
  esac

  ARGS=(-hide_banner -thread_queue_size 1024
    -f avfoundation -capture_cursor 1 -framerate "$fps" -pixel_format nv12
    -i "${screen}:${mic}")
  if [ "$camera" = none ]; then
    ARGS+=(-filter_complex "[0:v]scale=${width}:-2:flags=bilinear[v]")
  else
    ARGS+=(-thread_queue_size 1024
      -f avfoundation -framerate "$fps" -video_size "${LIVECODE_CAM_SIZE:-1280x720}" -pixel_format nv12
      -i "${camera}:none"
      -filter_complex "[0:v]scale=${width}:-2:flags=bilinear[s];[1:v]scale=${cam_w}:-2:flags=bilinear[c];[s][c]overlay=${pos}:eof_action=pass[v]")
  fi
  ARGS+=(-map "[v]")
  [ "$mode" != preview ] || return 0
  ARGS+=(-map 0:a -c:a aac -b:a 160k -ar 48000 -ac 2)
  ARGS+=(-fps_mode cfr -r "$fps" -c:v h264_videotoolbox -realtime 1 -profile:v high
    -force_key_frames "expr:gte(t,n_forced*2)" -g $(( fps * 2 )))
}

cmd_rec() {
  local out="${1:-$LIVECODE_DIR/recordings/livecode-$(date -u +%Y%m%dT%H%M%SZ).mkv}"
  local rate="${LIVECODE_REC_BITRATE:-6M}" rc=0
  prepare_storage "$(dirname "$out")"
  build_args
  printf 'livecode: recording to %s (q or Ctrl-C to stop)\n' "$out" >&2
  # A trap command (not an ignore) lets ffmpeg take Ctrl-C itself and finish
  # the file; the script then continues to report the path.
  trap ':' INT
  "$FFMPEG" "${ARGS[@]}" -b:v "$rate" -maxrate "$rate" -bufsize "$rate" -f matroska "$out" || rc=$?
  trap - INT
  if [ -s "$out" ]; then
    printf 'livecode: saved %s (%s)\n' "$out" "$(du -h "$out" | cut -f1)"
  else
    die "ffmpeg exited $rc and wrote nothing to $out"
  fi
}

# Replace every occurrence of the URL (and its key segment) in ffmpeg's stderr.
# Records split on \r so ffmpeg's in-place stats line keeps updating.
redact() {
  trap '' INT
  exec awk 'BEGIN { RS = "\r"; u = ENVIRON["LIVECODE_REDACT_URL"]; k = ENVIRON["LIVECODE_REDACT_KEY"] }
    function scrub(s, t, r,    i) {
      if (t == "") return s
      while ((i = index(s, t)) > 0) s = substr(s, 1, i - 1) r substr(s, i + length(t))
      return s
    }
    { printf "%s\r", scrub(scrub($0, u, "<rtmp-url>"), k, "<stream-key>"); fflush() }'
}

cmd_stream() {
  local url="${1:-${LIVECODE_RTMP_URL:-}}" file key rest rc=0
  local rate="${LIVECODE_STREAM_BITRATE:-4500k}"
  if [ -z "$url" ]; then
    file="${LIVECODE_RTMP_URL_FILE:-$HOME/.config/livecode/rtmp-url}"
    [ -r "$file" ] || die "no stream URL: pass one, or set LIVECODE_RTMP_URL / LIVECODE_RTMP_URL_FILE"
    url="$(tr -d '[:space:]' < "$file")"
  fi
  case "$url" in rtmp://*|rtmps://*) ;; *) die "stream URL must start with rtmp:// or rtmps://" ;; esac
  key="${url##*/}"
  [ "${#key}" -ge 8 ] || key=""
  prepare_storage
  build_args
  rest="${url#*://}"
  printf 'livecode: streaming to %s://%s/<redacted> (q or Ctrl-C to stop)\n' "${url%%://*}" "${rest%%/*}" >&2
  trap ':' INT
  "$FFMPEG" "${ARGS[@]}" -b:v "$rate" -maxrate "$rate" -bufsize "$rate" \
      -f flv -flvflags no_duration_filesize "$url" 2> >(LIVECODE_REDACT_URL="$url" LIVECODE_REDACT_KEY="$key" redact >&2) || rc=$?
  trap - INT
  printf '\nlivecode: stream ended (ffmpeg exit %s)\n' "$rc" >&2
}

# grab_preview: one composed frame to scratch/preview.png, written via a temp
# file and renamed, so Quick Look never sees a half-written PNG.
grab_preview() {
  local out="$LIVECODE_DIR/scratch/preview.png" tmp="$LIVECODE_DIR/scratch/.preview-next.png"
  # -ss skips the camera's first, still-exposing frames; one frame, no encoder settings.
  "$FFMPEG" "${ARGS[@]}" -loglevel error -ss 0.6 -frames:v 1 -update 1 -y "$tmp" </dev/null >&2 \
    || die "ffmpeg could not grab a preview frame"
  [ -s "$tmp" ] || die "ffmpeg wrote no preview frame"
  mv -f "$tmp" "$out" || die "could not write $out"
  printf '%s\n' "$out"
}

# show_preview fg|bg|stop [PNG]: Quick Look in the foreground, or (re)started in
# the background for --watch. Only the qlmanage this script started is closed.
QL_PID=""
show_preview() {
  if [ -n "$QL_PID" ]; then kill "$QL_PID" 2>/dev/null || true; wait "$QL_PID" 2>/dev/null || true; QL_PID=""; fi
  case "$1" in
    fg) "$QLMANAGE" -p "$2" >/dev/null 2>&1 || printf 'livecode: Quick Look failed; preview is %s\n' "$2" >&2 ;;
    bg) "$QLMANAGE" -p "$2" >/dev/null 2>&1 & QL_PID=$! ;;
    stop) ;;
  esac
}

cmd_preview() {
  local watch="" secs=5 png
  if [ "${1:-}" = --watch ]; then
    watch=1
    if [ -n "${2:-}" ]; then secs="$2"; fi
    case "$secs" in ''|*[!0-9]*|0) die "preview --watch takes whole seconds >= 1" ;; esac
  elif [ -n "${1:-}" ]; then
    die "usage: livecode preview [--watch [SECONDS]]"
  fi
  prepare_storage
  build_args preview
  png="$(grab_preview)" || exit 1
  printf 'livecode: preview %s\n' "$png" >&2
  if [ -z "$watch" ]; then show_preview fg "$png"; return 0; fi
  trap 'show_preview stop; exit 0' INT TERM
  printf 'livecode: re-grabbing every %ss (Ctrl-C to stop)\n' "$secs" >&2
  while :; do
    show_preview bg "$png"
    sleep "$secs"
    png="$(grab_preview)" || { show_preview stop; exit 1; }
  done
}

case "${1:-}" in
  devices) cmd_devices ;;
  preview) shift; cmd_preview "$@" ;;
  rec) shift; cmd_rec "$@" ;;
  stream) shift; cmd_stream "$@" ;;
  --version) printf 'livecode %s\n' "$LIVECODE_VERSION" ;;
  -h|--help|help) usage ;;
  "") usage; exit 2 ;;
  *) usage >&2; exit 2 ;;
esac
