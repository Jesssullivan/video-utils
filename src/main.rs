use std::env;
use std::ffi::{OsStr, OsString};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};

use video_utils::hash;
use video_utils::run_record::{self, VerifyOptions};

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
  help     Show this help

Use video-utils <COMMAND> --help for worker options.
Analyze: video-utils analyze INPUT [--run-dir DIR] [--backend stdlib|librosa] [--bpm BPM]
Hash: video-utils hash [--] FILE...
Verify: video-utils verify-run [--require-source] RUN_DIR

hash and verify-run are implemented in Rust; FFmpeg/ffprobe orchestration
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
