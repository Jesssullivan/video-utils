use std::env;
use std::ffi::{OsStr, OsString};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};

use std::collections::BTreeMap;
use std::fs::File;
use std::io::Read;

use video_utils::hash;
use video_utils::json::{self, Value};
use video_utils::run_record::{self, VerifyOptions};
use video_utils::timeline::{self, Edl, EdlFailure, Kind, Timeline};

const HELP: &str = "video-utils — local guitar video restoration and analysis

Usage: video-utils <COMMAND> [ARGS...]

Commands:
  probe    Inspect source streams, timeline and audio measurements
  clean    Create a conservative processed audio/video iteration
  demo     Run the reproducible demo pipeline
  export   Export processed audio or video
  analyze  Estimate periodicity and candidate rhythm events
  pipeline Evaluate phrase/rhythm DAG evidence and an optional approved reference
  markers  Export generic source-time review markers
  mcp      Serve typed agent tools and skill prompts over stdio
  report   Generate a report from measured run artifacts
  hash     Stream SHA-256 of files (native; shasum -a 256 line format)
  verify-run Verify a run directory's manifest hashes and typed fields (native,
           metadata-only, read-only; no decode or subprocess)
  timeline Validate a condense EDL, map source and output times, quantise
           segments to whole frames (native)
  help     Show this help

Use video-utils <COMMAND> --help for worker options.
Analyze: video-utils analyze INPUT [--run-dir DIR] [--backend stdlib|librosa] [--bpm BPM]
Hash: video-utils hash [--] FILE...
Verify: video-utils verify-run [--require-source] RUN_DIR
Timeline: video-utils timeline validate|table|map|quantise ...

hash, verify-run and timeline are implemented in Rust; FFmpeg/ffprobe orchestration
remains owned by the Python workers that the other commands dispatch.

Environment:
  VIDEO_UTILS_ROOT    Repository root containing scripts/ (default: build source root)
  VIDEO_UTILS_PYTHON  Python executable path (default: python3)
";

fn main() -> ExitCode {
    match run() {
        Ok(code) => ExitCode::from(code),
        Err(error) => {
            eprintln!("video-utils: {error}");
            ExitCode::from(2)
        }
    }
}

fn run() -> Result<u8, String> {
    let mut args = env::args_os().skip(1);
    let Some(command) = args.next() else {
        print!("{HELP}");
        return Ok(0);
    };
    if command == "--version" || command == "-V" {
        println!("video-utils {}", env!("CARGO_PKG_VERSION"));
        return Ok(0);
    }
    if command == "help" || command == "--help" || command == "-h" {
        print!("{HELP}");
        return Ok(0);
    }
    match command.to_str() {
        Some("hash") => return Ok(hash_command(args.collect())),
        Some("verify-run") => return verify_run_command(args.collect()),
        Some("timeline") => return timeline_command(args.collect()),
        _ => {}
    }
    let (script, prefix): (&str, Option<&OsStr>) = match command.to_str() {
        Some("probe" | "clean" | "export") => ("media.py", Some(&command)),
        Some("demo") => ("run_demo.py", None),
        Some("analyze") => ("rhythm.py", None),
        Some("report") => ("report.py", None),
        Some("pipeline") => ("dag.py", None),
        Some("markers") => ("markers.py", None),
        Some("mcp") => ("mcp_server.py", None),
        _ => {
            return Err(format!(
                "unknown command {:?}; use video-utils --help",
                command
            ));
        }
    };
    let root = match env::var_os("VIDEO_UTILS_ROOT") {
        Some(value) if value.is_empty() => return Err("VIDEO_UTILS_ROOT is empty".into()),
        Some(value) => PathBuf::from(value),
        None => PathBuf::from(env!("CARGO_MANIFEST_DIR")),
    };
    let worker = root.join("scripts").join(script);
    if !worker.is_file() {
        return Err(format!(
            "worker missing at {}; set VIDEO_UTILS_ROOT to the repository root",
            worker.display()
        ));
    }
    let python = env::var_os("VIDEO_UTILS_PYTHON").unwrap_or_else(|| OsString::from("python3"));
    if python.is_empty() {
        return Err("VIDEO_UTILS_PYTHON is empty".into());
    }
    let mut child = Command::new(&python);
    child.arg(&worker);
    if let Some(prefix) = prefix {
        child.arg(prefix);
    }
    child.args(args);
    let status = child.status().map_err(|error| {
        format!(
            "could not launch {:?} for {}: {error}",
            python,
            worker.display()
        )
    })?;
    if status.success() {
        return Ok(0);
    }
    let code = status.code().unwrap_or(1);
    eprintln!("video-utils: {script} failed ({status})");
    Ok(u8::try_from(code).unwrap_or(1))
}

const HASH_USAGE: &str = "Usage: video-utils hash [--] FILE...
Print `<sha256>  <FILE>` per file in `shasum -a 256` text-mode format.
Names containing a backslash or newline use the shasum escape (leading \\).
Directories and unreadable paths report a typed error and exit 1; the
remaining files are still hashed.
";

const VERIFY_USAGE: &str = "Usage: video-utils verify-run [--require-source] RUN_DIR
Metadata-only, read-only verification of RUN_DIR/manifest.json: typed
schema-1 fields and SHA-256 of every output_sha256 file and of the source.
Prints one JSON receipt. Exit 0 verified, 1 failed (typed reason), 2 usage.
--require-source  treat an absent source file as failure source_missing
";

fn name_bytes(name: &OsStr) -> Vec<u8> {
    #[cfg(unix)]
    {
        use std::os::unix::ffi::OsStrExt;
        name.as_bytes().to_vec()
    }
    #[cfg(not(unix))]
    {
        name.to_string_lossy().into_owned().into_bytes()
    }
}

fn hash_command(args: Vec<OsString>) -> u8 {
    let mut files = args.as_slice();
    match files.first().and_then(|arg| arg.to_str()) {
        Some("--help" | "-h") if files.len() == 1 => {
            print!("{HASH_USAGE}");
            return 0;
        }
        Some("--") => files = &files[1..],
        Some(flag) if flag.starts_with('-') && flag.len() > 1 => {
            eprintln!("video-utils: hash: unknown option {flag:?}; use -- before such file names");
            return 2;
        }
        _ => {}
    }
    if files.is_empty() {
        eprint!("video-utils: hash requires at least one FILE\n{HASH_USAGE}");
        return 2;
    }
    let stdout = io::stdout();
    let mut out = stdout.lock();
    let mut status = 0;
    for file in files {
        match hash::hash_file(Path::new(file)) {
            Ok((digest, _)) => {
                let mut line = hash::shasum_line(&digest, &name_bytes(file));
                line.push(b'\n');
                if out.write_all(&line).and_then(|()| out.flush()).is_err() {
                    return 1;
                }
            }
            Err(error) => {
                eprintln!("video-utils: hash: {}: {error}", Path::new(file).display());
                status = 1;
            }
        }
    }
    status
}

fn verify_run_command(args: Vec<OsString>) -> Result<u8, String> {
    let mut options = VerifyOptions::default();
    let mut run_dir: Option<OsString> = None;
    let mut positional_only = false;
    for arg in args {
        match arg.to_str() {
            Some("--help" | "-h") if !positional_only => {
                print!("{VERIFY_USAGE}");
                return Ok(0);
            }
            Some("--require-source") if !positional_only => options.require_source = true,
            Some("--") if !positional_only => positional_only = true,
            Some(flag) if !positional_only && flag.starts_with('-') && flag.len() > 1 => {
                return Err(format!(
                    "verify-run: unknown option {flag:?}\n{VERIFY_USAGE}"
                ));
            }
            _ if run_dir.is_some() => {
                return Err(format!(
                    "verify-run takes exactly one RUN_DIR\n{VERIFY_USAGE}"
                ));
            }
            _ => run_dir = Some(arg),
        }
    }
    let Some(run_dir) = run_dir else {
        return Err(format!("verify-run requires RUN_DIR\n{VERIFY_USAGE}"));
    };
    let verification = run_record::verify_run(Path::new(&run_dir), options);
    let verifier = format!("video-utils {} verify-run", env!("CARGO_PKG_VERSION"));
    let text = run_record::receipt(&verification, &verifier).to_pretty();
    let mut out = io::stdout().lock();
    out.write_all(text.as_bytes())
        .and_then(|()| out.flush())
        .map_err(|error| format!("verify-run: could not write receipt: {error}"))?;
    match &verification.failure {
        None => Ok(0),
        Some(failure) => {
            eprintln!("video-utils: verify-run failed: {failure}");
            Ok(1)
        }
    }
}

const TIMELINE_USAGE: &str = "Usage: video-utils timeline <SUBCOMMAND> ...
  validate EDL                  check an edl.json against the EDL contract
  table EDL                     every segment's place on the output clock
  map EDL QUERIES|-             answer to_out, to_src and row queries in one batch
  quantise --fps N SEGMENTS|-   give segments whole output frames
QUERIES is {\"queries\": [{\"op\": \"to_out\", \"clip\": C, \"source_s\": T, \"snap\": B},
{\"op\": \"to_src\", \"output_s\": T}, {\"op\": \"row\", \"clip\": C, \"source_s\": T}]}.
SEGMENTS is {\"segments\": [...]}; - reads standard input.
Prints one JSON receipt. Exit 0 ok, 1 failed (typed reason), 2 usage.
";

/// A typed timeline failure: a stable reason code and a detail.
struct Failed(&'static str, String);

impl From<EdlFailure> for Failed {
    fn from(failure: EdlFailure) -> Self {
        Self(failure.reason.code(), failure.detail)
    }
}

type Fields = BTreeMap<String, Value>;

fn read_input(path: &OsStr, what: &'static str) -> Result<Vec<u8>, Failed> {
    let unreadable =
        |error: io::Error| Failed(what, format!("{}: {error}", Path::new(path).display()));
    let mut bytes = Vec::new();
    if path == "-" {
        io::stdin()
            .lock()
            .take(timeline::MAX_EDL_BYTES + 1)
            .read_to_end(&mut bytes)
            .map_err(unreadable)?;
    } else {
        let file = File::open(path).map_err(unreadable)?;
        if !file.metadata().map_err(unreadable)?.is_file() {
            return Err(Failed(
                what,
                format!("{} is not a regular file", Path::new(path).display()),
            ));
        }
        file.take(timeline::MAX_EDL_BYTES + 1)
            .read_to_end(&mut bytes)
            .map_err(unreadable)?;
    }
    if bytes.len() as u64 > timeline::MAX_EDL_BYTES {
        return Err(Failed(
            "too_large",
            format!("input exceeds {} bytes", timeline::MAX_EDL_BYTES),
        ));
    }
    Ok(bytes)
}

fn load_edl(path: &OsStr) -> Result<(Edl, timeline::Report, String), Failed> {
    let bytes = read_input(path, "edl_unreadable")?;
    let edl = Edl::parse(&bytes)?;
    let report = edl.validate()?;
    Ok((edl, report, hash::digest(&bytes).to_hex()))
}

fn report_fields(report: &timeline::Report, sha256: String) -> Fields {
    Fields::from([
        ("edl_sha256".into(), Value::String(sha256)),
        ("fps".into(), Value::u64(report.fps)),
        ("clips".into(), Value::u64(report.clips as u64)),
        ("segments".into(), Value::u64(report.segments as u64)),
        ("total_frames".into(), Value::u64(report.total_frames)),
        ("total_seconds".into(), Value::f64(report.total_seconds)),
        (
            "max_drift_frames".into(),
            Value::f64(report.max_drift_frames),
        ),
    ])
}

fn row_json(edl: &Edl, tl: &Timeline, row: usize) -> Fields {
    let r = &tl.rows()[row];
    Fields::from([
        ("clip".into(), Value::string(&edl.clips[r.clip].name)),
        ("clip_index".into(), Value::u64(r.clip as u64)),
        ("segment_index".into(), Value::u64(r.segment as u64)),
        ("kind".into(), Value::string(tl.segment(row).kind.as_str())),
        ("start_frame".into(), Value::u64(r.start_frame)),
        ("end_frame".into(), Value::u64(r.end_frame)),
        ("start_s".into(), Value::f64(r.start_s)),
        ("end_s".into(), Value::f64(r.end_s)),
    ])
}

fn table(edl: &Edl) -> Fields {
    let tl = Timeline::new(edl);
    let rows = (0..tl.rows().len()).map(|r| Value::Object(row_json(edl, &tl, r)));
    let mut first = 0;
    let clips = edl.clips.iter().map(|clip| {
        let range = (first, first + clip.segments.len());
        first = range.1;
        Value::Object(Fields::from([
            ("name".into(), Value::string(&clip.name)),
            ("shift".into(), Value::f64(clip.shift)),
            ("first_row".into(), Value::u64(range.0 as u64)),
            ("end_row".into(), Value::u64(range.1 as u64)),
        ]))
    });
    Fields::from([
        ("fps".into(), Value::u64(edl.fps)),
        ("total_frames".into(), Value::u64(tl.total_frames())),
        ("total_seconds".into(), Value::f64(tl.total_seconds())),
        ("clips".into(), Value::Array(clips.collect())),
        ("rows".into(), Value::Array(rows.collect())),
    ])
}

fn query_number(query: &Value, key: &str, at: &str) -> Result<f64, Failed> {
    query
        .get(key)
        .and_then(Value::as_number)
        .map(json::Number::as_f64)
        .ok_or_else(|| Failed("query_invalid", format!("{at} needs a number `{key}`")))
}

fn query_clip<'q>(query: &'q Value, tl: &Timeline, at: &str) -> Result<&'q str, Failed> {
    let clip = query
        .get("clip")
        .and_then(Value::as_str)
        .ok_or_else(|| Failed("query_invalid", format!("{at} needs a string `clip`")))?;
    if !tl.has_clip(clip) {
        return Err(Failed("clip_unknown", format!("{at}: no clip `{clip}`")));
    }
    Ok(clip)
}

fn answer(edl: &Edl, tl: &Timeline, query: &Value, at: &str) -> Result<Value, Failed> {
    let map = query
        .as_object()
        .ok_or_else(|| Failed("query_invalid", format!("{at} must be an object")))?;
    let op = map.get("op").and_then(Value::as_str).unwrap_or("");
    let allowed: &[&str] = match op {
        "to_out" => &["op", "clip", "source_s", "snap"],
        "row" => &["op", "clip", "source_s"],
        "to_src" => &["op", "output_s"],
        _ => {
            return Err(Failed(
                "query_invalid",
                format!("{at}: op must be to_out, to_src or row"),
            ));
        }
    };
    if let Some(key) = map.keys().find(|k| !allowed.contains(&k.as_str())) {
        return Err(Failed(
            "query_invalid",
            format!("{at}: unknown key `{key}`"),
        ));
    }
    Ok(match op {
        "to_out" => {
            let snap = match map.get("snap") {
                None | Some(Value::Bool(false)) => false,
                Some(Value::Bool(true)) => true,
                Some(_) => {
                    return Err(Failed(
                        "query_invalid",
                        format!("{at}: snap must be a boolean"),
                    ));
                }
            };
            let clip = query_clip(query, tl, at)?;
            tl.to_out(clip, query_number(query, "source_s", at)?, snap)
                .map_or(Value::Null, Value::f64)
        }
        "row" => {
            let clip = query_clip(query, tl, at)?;
            tl.row(clip, query_number(query, "source_s", at)?)
                .map_or(Value::Null, |row| Value::Object(row_json(edl, tl, row)))
        }
        _ => match tl.to_src(query_number(query, "output_s", at)?) {
            None => Value::Null,
            Some((source_s, row)) => {
                let mut fields = row_json(edl, tl, row);
                fields.insert("source_s".into(), Value::f64(source_s));
                Value::Object(fields)
            }
        },
    })
}

fn map_queries(edl_path: &OsStr, queries_path: &OsStr) -> Result<Fields, Failed> {
    let (edl, _, _) = load_edl(edl_path)?;
    let bytes = read_input(queries_path, "queries_unreadable")?;
    let root = json::parse_object(&bytes).map_err(|e| Failed("invalid_json", e.to_string()))?;
    let Some(Value::Array(queries)) = root.get("queries") else {
        return Err(Failed(
            "query_invalid",
            "QUERIES needs a `queries` array".into(),
        ));
    };
    let tl = Timeline::new(&edl);
    let results = queries
        .iter()
        .enumerate()
        .map(|(i, query)| answer(&edl, &tl, query, &format!("query {i}")))
        .collect::<Result<Vec<_>, _>>()?;
    Ok(Fields::from([("results".into(), Value::Array(results))]))
}

fn quantise_segments(fps: u64, path: &OsStr) -> Result<Fields, Failed> {
    timeline::check_fps(fps)?;
    let bytes = read_input(path, "segments_unreadable")?;
    let root = json::parse_object(&bytes).map_err(|e| Failed("invalid_json", e.to_string()))?;
    let Some(items) = root.get("segments") else {
        return Err(Failed(
            "field_invalid",
            "SEGMENTS needs a `segments` array".into(),
        ));
    };
    let segments = timeline::segments_from_json(items, false, "segments")?;
    for (i, s) in segments.iter().enumerate() {
        if !(s.out > s.inp && s.speed > 0.0) || (s.kind == Kind::Card) {
            return Err(Failed(
                "field_invalid",
                format!("segments[{i}]: needs out > inp, a positive speed and no card"),
            ));
        }
        if let Some(keep) = s.keep
            && !(keep.head.0 < keep.head.1
                && keep.head.1 <= keep.tail.0
                && keep.tail.0 < keep.tail.1)
        {
            return Err(Failed(
                "cut_keep_invalid",
                format!("segments[{i}]: keep edges are out of order"),
            ));
        }
    }
    let out = timeline::quantise(segments, fps);
    Ok(Fields::from([
        ("fps".into(), Value::u64(fps)),
        (
            "segments".into(),
            Value::Array(out.iter().map(timeline::Segment::to_json).collect()),
        ),
    ]))
}

fn timeline_command(args: Vec<OsString>) -> Result<u8, String> {
    let words: Vec<Option<&str>> = args.iter().map(|a| a.to_str()).collect();
    let outcome = match words.as_slice() {
        [Some("--help" | "-h")] => {
            print!("{TIMELINE_USAGE}");
            return Ok(0);
        }
        [Some("validate"), _] => {
            load_edl(&args[1]).map(|(_, report, sha)| report_fields(&report, sha))
        }
        [Some("table"), _] => load_edl(&args[1]).map(|(edl, _, _)| table(&edl)),
        [Some("map"), _, _] => map_queries(&args[1], &args[2]),
        [Some("quantise"), Some("--fps"), Some(fps), _] => {
            let fps = fps.parse::<u64>().map_err(|_| {
                format!("timeline quantise: --fps needs a whole number\n{TIMELINE_USAGE}")
            })?;
            quantise_segments(fps, &args[3])
        }
        _ => {
            return Err(format!(
                "timeline: unknown or incomplete subcommand\n{TIMELINE_USAGE}"
            ));
        }
    };
    let command = words[0].unwrap_or_default();
    let mut receipt = Fields::from([
        ("schema_version".into(), Value::u64(1)),
        ("command".into(), Value::string(command)),
    ]);
    let code = match outcome {
        Ok(fields) => {
            receipt.extend(fields);
            receipt.insert("status".into(), Value::string("ok"));
            receipt.insert("reason".into(), Value::Null);
            0
        }
        Err(Failed(reason, detail)) => {
            eprintln!("video-utils: timeline {command} failed: {reason}: {detail}");
            receipt.insert("status".into(), Value::string("failed"));
            receipt.insert("reason".into(), Value::string(reason));
            receipt.insert("detail".into(), Value::String(detail));
            1
        }
    };
    let text = Value::Object(receipt).to_pretty();
    let mut out = io::stdout().lock();
    out.write_all(text.as_bytes())
        .and_then(|()| out.flush())
        .map_err(|error| format!("timeline: could not write receipt: {error}"))?;
    Ok(code)
}
