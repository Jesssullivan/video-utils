"""Render the EDL.

1. Mezzanine per clip: constant frame rate, one frame size, mono 48 kHz PCM, near-lossless x264. It keeps
   the source's clock. The video is padded with its last frame to the audio's end. The audio is padded
   from time 0, so sample n is at n / 48000 s.
2. Parts: the segments are split into parts of 220. Each part seeks its own window of the mezzanine and runs
   one filter graph. Each segment comes out as exactly its EDL frames: that many video frames and that many
   frame-lengths of audio. So the sound cannot drift from the picture. Parts render in parallel.
3. Final: the parts are joined. Loudness is measured in one pass and applied linearly in a second
   (-16 LUFS, -1.5 dBTP). The encode is HEVC CRF 35 tagged hvc1, so QuickTime, Safari and iOS play it,
   with AAC.
4. Upload, with `[encode] upload = "h264"`: the same frames once more as H.264 without B-frames and a
   keyframe every 2 s, with the edit's audio copied. One video site scrambled the first keyframe interval
   of the HEVC file, whose negative CTS offsets stand in for an edit list. The copy is refused unless its
   moov box precedes its mdat box (+faststart) and its first video packet has pts and dts 0 (upload_facts).

Sync rules. The first render broke each of them, and its sound ran up to 107 ms off the picture.
- Video is never retimed with setpts=(PTS-STARTPTS)/speed. Frames are picked evenly and renumbered.
- Audio samples are never counted from a seek point. A seek lands mid-packet, so the count starts wrong.
  The part seeks 1 s early, pads the audio from time 0 and then counts.
- atempo is never trusted for length. Its output runs up to 30 ms short or long. It gets 0.2 s of extra
  source, and its output is cut or padded to the exact length.
- The source's two clocks are not assumed equal. See audio.shift.
"""

import json
import re
import textwrap
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import audio
from .config import FF, run

SR = 48000
MEZZ = ("-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-g", "60", "-pix_fmt", "yuv420p")
MEZZ += ("-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709")
MEZZ += ("-c:a", "pcm_s16le", "-ar", str(SR), "-ac", "1")
# HLG to SDR bt709 (hable), after the downscale so the float tone-map works on small frames
TONEMAP = "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,"
PREROLL = 1.0  # a part seeks this far before its first segment, so the seek's ragged audio start is never used
LOOKAHEAD = 0.2  # output seconds of extra source fed to atempo, then trimmed off: its tail runs 30 ms short or long
TAIL = 4.0  # input read past a part's last segment, for the lookahead


def mezzanine(cfg, clip, total):
    """total: seconds on the source's clock, the analysis length plus the clip's shift."""
    out = cfg.f(clip, "mezz.mkv")
    if out.exists() and out.stat().st_mtime > Path(clip["file"]).stat().st_mtime:
        return
    e = cfg.encode
    w, h = e["width"], e["height"]
    pad = max(0.0, total - audio.duration(clip["file"], "v:0")) + 1
    graph = (
        f"[0:v:0]fps={cfg.fps}:start_time=0,scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos,"
        f"{TONEMAP if clip['tonemap'] else ''}format=yuv420p,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,"
        f"tpad=stop_mode=clone:stop_duration={pad:.3f},trim=duration={total}[v];"
        f"[0:a:0]{audio.FROM_ZERO},aresample={SR},apad,atrim=duration={total}[a]"
    )
    run(*FF, "-v", "error", "-i", clip["file"], "-filter_complex", graph, "-map", "[v]", "-map", "[a]", *MEZZ, out)


def atempo(speed):
    """atempo takes at most 2x per stage, so 8x is three stages."""
    stages = []
    while speed > 2.0 + 1e-9:
        stages.append(2.0)
        speed /= 2.0
    if abs(speed - 1.0) > 1e-9:
        stages.append(speed)
    return ",".join(f"atempo={x:.6g}" for x in stages) or "anull"


def pick(nf, m):
    """Keep nf of m frames evenly: output frame j shows the source frame nearest j * m / nf."""
    return f"select='gt(floor((2*n+1)*{nf}/{2 * m}),floor((2*n-1)*{nf}/{2 * m}))'"


def concat_filter(segs, z, fps, xfade_frames, shift=0.0, probe=False):
    """One part's graph: per segment exactly s["frames"] video frames and as many frame-lengths of audio.

    z is the part's input seek point on the source's clock, and shift moves analysis times onto that clock.
    Video: trim by time with a half-frame guard (mkv timestamps are whole ms), keep frames evenly, renumber
    on the frame grid. Audio: padded from pts 0, so a sample's index is its time, then cut by sample. A sped
    segment runs atempo at source frames / output frames and is cut or padded to its length. A cut keeps
    two edges: a hard video cut, and audio crossfaded over the join.
    probe: for avsync. A plain resample stands in for atempo and the gain is left out, so coded audio
    survives the graph.
    """

    def smp(t):
        return int(round(t * SR))

    n, cuts = len(segs), [i for i, s in enumerate(segs) if s["kind"] == "cut"]
    labels = "".join(f"[ai{i}]" for i in range(n)) + "".join(f"[aj{i}]" for i in cuts)
    lines = [
        f"[0:v]split={n}" + "".join(f"[vi{i}]" for i in range(n)) + ";",
        f"[0:a]{audio.FROM_ZERO},asplit={n + len(cuts)}{labels};",
    ]
    h, guard, per = xfade_frames / fps / 2, 0.5 / fps, SR // fps
    for i, s in enumerate(segs):
        a, b, nf = s["inp"] + shift - z, s["out"] + shift - z, s["frames"]
        m, ns = round((b - a) * fps), s["frames"] * per
        video = f"[vi{i}]trim=start={max(a - guard, 0):.6f}:end={b - guard:.6f}"
        fit = f"apad=whole_len={ns},atrim=end_sample={ns}[a{i}];"
        if s["kind"] == "cut":
            (a0, a1), (b0, b1) = [[x + shift - z for x in r] for r in s["keep"]]
            k0, k1 = round((a1 - a0) * fps), round((b0 - a0) * fps)
            assert nf == k0 + m - k1, s
            lines += [
                f"{video},select='lt(n,{k0})+gte(n,{k1})',setpts=N/({fps}*TB)[v{i}];",
                f"[ai{i}]atrim=start_sample={smp(a0)}:end_sample={smp(a1 + h)},asetpts=PTS-STARTPTS[ax{i}];",
                f"[aj{i}]atrim=start_sample={smp(b0 - h)}:end_sample={smp(b1)},asetpts=PTS-STARTPTS[ay{i}];",
                f"[ax{i}][ay{i}]acrossfade=ns={smp(2 * h)}:c1=tri:c2=tri,{fit}",
            ]
            continue
        assert 0 < nf <= m, s
        gain = "" if s["gain"] == 1.0 or probe else f",volume={s['gain']}"
        if nf == m:
            lines.append(f"{video},setpts=N/({fps}*TB)[v{i}];")
            lines.append(f"[ai{i}]atrim=start_sample={smp(a)}:end_sample={smp(b)},asetpts=PTS-STARTPTS{gain}[a{i}];")
            continue
        cut = f"atrim=start_sample={smp(a)}:end_sample={smp(b + LOOKAHEAD * m / nf)},asetpts=PTS-STARTPTS"
        lines.append(f"{video},{pick(nf, m)},setpts=N/({fps}*TB)[v{i}];")
        faster = f"asetrate={round(SR * m / nf)},aresample={SR}" if probe else atempo(m / nf)
        lines.append(f"[ai{i}]{cut},{faster}{gain},{fit}")
    lines.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[vc][ac];")
    lines += [f"[vc]fps={fps},format=yuv420p[v];", f"[ac]aresample={SR}[a]"]
    return "\n".join(lines) + "\n"


def card_filter(cfg, name, seg):
    """The whole clip sped to the card's frames, blurred and dimmed, under white text with a soft shadow.

    The picture is cropped out of the mezzanine's pad and scaled up, so the blur fills the frame.
    """
    e, fps, n = cfg.encode, cfg.fps, seg["frames"]
    w, h = e["width"], e["height"]
    sw, sh = audio.size(cfg.clip(name)["file"])
    cw = min(w, h * sw / sh, min(h, w * sh / sw) * w / h)  # the widest w:h box inside the picture
    fill = f"crop={2 * round(cw / 2)}:{2 * round(cw * h / w / 2)},scale={w}:{h},"
    size, d = e["height"] // 16, seg["frames"] / cfg.fps
    lines = cfg.clip(name)["card"]
    font = f"fontfile={cfg.font}:" if cfg.font else ""

    def text(color, dy):
        out = []
        for k, line in enumerate(lines):
            cfg.f(name, f"card{k}.txt").write_text("\n".join(textwrap.wrap(line, 48)))
            y = f"(h-{len(lines)}*{size}*1.5)/2+{k}*{size}*1.5+{dy}"
            out.append(
                f"drawtext={font}textfile={name}.card{k}.txt:expansion=none:fontsize={size}:fontcolor={color}"
                f":x=(w-text_w)/2:y={y}"
            )
        return ",".join(out)

    fade, afade = (f"{f}=t=in:st=0:d=0.5,{f}=t=out:st={d - 0.5}:d=0.5" for f in ("fade", "afade"))
    return (
        f"[0:v]fps={fps},{pick(n, round(seg['out'] * fps))},setpts=N/({fps}*TB),"
        f"{fill}gblur=sigma=18,eq=brightness=-0.25:saturation=0.5,"
        f"tpad=stop_mode=clone:stop=2,trim=end_frame={n},format=yuv420p[bg];"
        f"color=c=black@0.0:s={e['width']}x{e['height']}:r={fps}:d={d},format=rgba,{text('black', 3)},"
        f"format=yuva420p,gblur=sigma=5:planes=15[sh];"
        f"[bg][sh]overlay=shortest=1,{text('white', 0)},{fade},format=yuv420p[v];"
        f"[0:a]{atempo(seg['speed'])},volume={seg['gain']},{afade},apad,atrim=end_sample={n * SR // fps}[a]\n"
    )


def parts(edl):
    """[(part name, clip name, segments)] in output order."""
    per = edl["rules"]["chunk_segs"]
    return [
        (f"{c['name']}.part{k // per:02d}", c["name"], c["segments"][k : k + per])
        for c in edl["clips"]
        for k in range(0, len(c["segments"]), per)
    ]


def render_part(cfg, edl, name, clip, segs, kind="mezz", codec=MEZZ):
    """Render one part from work/<clip>.<kind>.mkv to work/<name>.<kind>.mkv. avsync passes kind="probe"."""
    graph, window = cfg.f(name, f"{kind}.filter"), ()
    if segs[0]["kind"] == "card":
        graph.write_text(card_filter(cfg, clip, segs[0]))
    else:
        shift = next(c["shift"] for c in edl["clips"] if c["name"] == clip)
        z = max(0.0, round((segs[0]["inp"] + shift - PREROLL) * cfg.fps) / cfg.fps)
        graph.write_text(concat_filter(segs, z, cfg.fps, edl["rules"]["xfade_frames"], shift, kind == "probe"))
        window = ("-ss", f"{z:.6f}", "-t", f"{segs[-1]['out'] + shift - z + TAIL:.6f}")
    out = cfg.f(name, f"{kind}.mkv")
    args = (*window, "-i", cfg.f(clip, f"{kind}.mkv"), "-/filter_complex", graph, "-map", "[v]", "-map", "[a]")
    run(*FF, "-v", "error", *args, *codec, out, cwd=cfg.work)
    want, got = sum(s["frames"] for s in segs), audio.frames(out)
    if got != want:
        raise RuntimeError(f"{name}: {got} frames rendered, the EDL says {want}")
    return name


def joined(cfg, names, kind="mezz"):
    """ffmpeg inputs and a filter graph that joins the named parts into [v][a0].

    Each part's audio is cut or padded to its video frames, so every part starts on the frame grid.
    """
    inputs, graph = [], ""
    for i, name in enumerate(names):
        inputs += ["-i", cfg.f(name, f"{kind}.mkv")]
        samples = audio.frames(cfg.f(name, f"{kind}.mkv")) * SR // cfg.fps
        # mkv timestamps are whole ms: renumber the frames, or concat pads each part's audio by a few samples
        graph += f"[{i}:v]setpts=N/({cfg.fps}*TB),setsar=1[v{i}];[{i}:a]apad,atrim=end_sample={samples}[p{i}];"
    return inputs, graph + "".join(f"[v{i}][p{i}]" for i in range(len(names))) + f"concat=n={len(names)}:v=1:a=1[v][a0]"


COLOR = ("-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709")


def video_codec(cfg):
    e = cfg.encode
    codec = ("-c:v", "libx265", "-preset", e["preset"], "-crf", e["crf"], "-tag:v", "hvc1", "-pix_fmt", "yuv420p")
    return (*codec, "-x265-params", "log-level=error", *COLOR)


def upload_codec(cfg):
    """H.264 with no B-frames, so every pts equals its dts and none is negative, and a keyframe every 2 s."""
    e, gop = cfg.encode, 2 * cfg.fps
    codec = ("-c:v", "libx264", "-preset", e["preset"], "-crf", e["upload_crf"], "-profile:v", "high")
    gops = ("-bf", "0", "-g", gop, "-keyint_min", gop, "-sc_threshold", "0", "-pix_fmt", "yuv420p")
    return (*codec, *gops, *COLOR)


def upload(cfg, edl, draw="", suffix=""):
    """Write <out><suffix>.upload.mp4: the picture of <out><suffix>.mp4 as H.264, the audio of <out> copied.

    draw: the overlay's drawtext chain, for the corrected copy. The picture comes from the lossless parts
    when they are still in work/, else from the edit. Plain +faststart: no negative CTS offsets, and the
    video's only edit list is none at all, because its first pts is 0.
    """
    names = [name for name, _, _ in parts(edl)]
    if all(cfg.f(name, "mezz.mkv").exists() for name in names):
        inputs, graph = joined(cfg, names)
        graph += f";[a0]anullsink;[v]{video_filter(cfg)}{draw and ','}{draw}[vo]"
    else:
        print(f"warning: no parts in {cfg.work}, so the upload copy re-encodes {cfg.out}, a second generation of loss")
        inputs, graph = ["-i", cfg.out], f"[0:v]{draw or 'null'}[vo]"
    out = cfg.out.with_suffix(f"{suffix}.upload.mp4")
    graph_file = cfg.f(f"upload{suffix}", "filter")
    graph_file.write_text(graph)
    maps = ("-map", "[vo]", "-map", f"{len(inputs) // 2}:a", "-map_metadata", "-1", "-c:a", "copy")
    args = (*inputs, "-i", cfg.out, "-/filter_complex", graph_file, *maps, *upload_codec(cfg))
    run(*FF, "-v", "error", *args, "-movflags", "+faststart", out, cwd=cfg.work)
    if audio.frames(out) != audio.frames(cfg.out):
        raise RuntimeError(f"{out}: {audio.frames(out)} frames, the edit has {audio.frames(cfg.out)}")
    facts = upload_facts(out)
    first = f"{facts['audio_first_pts']} x {facts['audio_time_base']} s"
    print(f"{out}: moov at byte {facts['moov_offset']}, before mdat; audio first pts {first}")
    return out


MAX_BOXES = 64  # top-level boxes read before moov and mdat must both have appeared, as verify-run reads


def boxes(path):
    """(moov offset, mdat offset): the first top-level moov and mdat boxes, None for one not found.

    ISO/IEC 14496-12 box headers only: a 32-bit size and a type; size 1 means a 64-bit size follows, size 0
    runs to the end of the file. A size that overruns the file raises. `video-utils verify-run` reads the
    same headers the same way.
    """
    found, offset = {}, 0
    with open(path, "rb") as f:
        length = f.seek(0, 2)
        for _ in range(MAX_BOXES):
            if offset >= length or len(found) == 2:
                break
            f.seek(offset)
            head = f.read(8)
            if len(head) < 8:
                raise RuntimeError(f"{path}: a truncated box header at byte {offset}")
            size, kind, used = int.from_bytes(head[:4], "big"), head[4:], 8
            if size == 1:
                large = f.read(8)
                if len(large) < 8:
                    raise RuntimeError(f"{path}: a truncated box header at byte {offset}")
                size, used = int.from_bytes(large, "big"), 16
            elif size == 0:
                size = length - offset
            if size < used or size > length - offset:
                raise RuntimeError(
                    f"{path}: the {kind!r} box at byte {offset} claims {size} of {length - offset} bytes"
                )
            if kind in (b"moov", b"mdat"):
                found.setdefault(kind.decode(), offset)
            offset += size
    return found.get("moov"), found.get("mdat")


def first_packet(path, stream):
    """The stream's time_base, start_pts (after any edit list) and has_b_frames, and its first packet's pts and dts."""
    entries = "stream=time_base,start_pts,has_b_frames:packet=pts,dts"
    out = run(
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        stream,
        "-show_entries",
        entries,
        "-read_intervals",
        "%+#1",
        "-of",
        "json",
        path,
    ).stdout
    found = json.loads(out)
    return found["streams"][0], found["packets"][0]


def audio_packets(path):
    """sha256 of the first audio stream's coded packets, copied, not decoded: equal for a stream copied unchanged."""
    out = run(*FF, "-v", "error", "-i", path, "-map", "0:a:0", "-c", "copy", "-f", "streamhash", "-hash", "sha256", "-")
    return out.stdout.strip().rsplit("=", 1)[-1].lower()


def upload_facts(path):
    """What an upload copy must be, measured: raise unless moov precedes mdat and the video starts at pts and dts 0
    with no B-frames. The audio's first packet pts is recorded, not judged: AAC's encoder delay puts the copied
    edit's first packet at -1024 (1/48000), before 0, and the mp4 edit list starts playback at 0."""
    moov, mdat = boxes(path)
    if moov is None or mdat is None or moov > mdat:
        raise RuntimeError(f"{path}: moov at byte {moov}, mdat at byte {mdat}; an upload copy is +faststart")
    video, vfirst = first_packet(path, "v:0")
    sound, afirst = first_packet(path, "a:0")
    starts = (int(vfirst["pts"]), int(vfirst["dts"]))
    if starts != (0, 0) or int(video.get("has_b_frames", 0)):
        raise RuntimeError(
            f"{path}: video pts/dts {starts}, B-frames {video.get('has_b_frames')}; want (0, 0) and none"
        )
    return {
        "faststart": True,
        "moov_offset": moov,
        "mdat_offset": mdat,
        "video_first_pts": 0,
        "video_first_dts": 0,
        "video_b_frames": 0,
        "audio_first_pts": int(afirst["pts"]),
        "audio_start_pts": int(sound["start_pts"]),
        "audio_time_base": sound["time_base"],
    }


def video_filter(cfg):
    """The delivery chain: frame rate, a light denoise (camera grain is most of the bitrate) and 8-bit 4:2:0."""
    return ",".join(x for x in (f"fps={cfg.fps}", cfg.encode["denoise"], "format=yuv420p") if x)


def final(cfg, edl):
    e = cfg.encode
    inputs, graph = joined(cfg, [name for name, _, _ in parts(edl)])
    # Speech peaks sit about 22 dB over its loudness. Gain into a limiter trims them first, so loudnorm
    # reaches the target with one linear gain and AAC overshoot stays under 0 dBTP.
    pre = f"volume={e['pre_gain_db']}dB,alimiter=limit={e['limit']}:attack=5:release=50:level=false:latency=1"
    norm = f"loudnorm=I={e['loudness']}:TP={e['true_peak']}:LRA=11"
    measure = f"{graph};[v]nullsink;[a0]{pre},{norm}:print_format=json[a]"
    log = run(*FF, *inputs, "-filter_complex", measure, "-map", "[a]", "-f", "null", "-").stderr
    m = json.loads(re.findall(r"\{[^{}]*\}", log)[-1])
    if float(m["input_tp"]) + e["loudness"] - float(m["input_i"]) > e["true_peak"]:
        print("loudnorm cannot stay linear: the peak would pass the ceiling. Lower encode.limit.")
    norm += (
        f":measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
        f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,aresample={SR}"
    )
    cfg.out.parent.mkdir(parents=True, exist_ok=True)
    graph += f";[v]{video_filter(cfg)}[vo];[a0]{pre},{norm}[a]"
    # -aac_pns 0: the encoder's noise substitution turned one transient into a +4.0 dBTP spike at 64 kb/s
    sound = ("-c:a", "aac", "-aac_pns", "0", "-b:a", e["audio_bitrate"], "-ac", "1", "-ar", SR)
    maps = ("-map", "[vo]", "-map", "[a]", "-map_metadata", "-1")
    # negative_cts_offsets: the video starts at 0 with no edit list, which some players ignore
    flags = ("-movflags", "+faststart+negative_cts_offsets")
    run(*FF, "-v", "error", *inputs, "-filter_complex", graph, *maps, *video_codec(cfg), *sound, *flags, cfg.out)


def render(cfg):
    edl = json.loads(cfg.f("edl", "json").read_text())
    for clip, entry in zip(cfg.clips, edl["clips"], strict=True):
        mezzanine(cfg, clip, entry["duration"] + entry["shift"])
    with ThreadPoolExecutor(cfg.encode["jobs"]) as pool:
        names = list(pool.map(lambda p: render_part(cfg, edl, *p), parts(edl)))
    final(cfg, edl)
    print(f"{cfg.out}: {edl['expected_total_s']} s in {len(names)} parts")
    if cfg.encode["upload"]:
        print(f"{upload(cfg, edl)}: H.264, no B-frames, a keyframe every {2 * cfg.fps} frames")
