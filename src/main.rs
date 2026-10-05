use std::env;
use std::ffi::{OsStr, OsString};
use std::path::PathBuf;
use std::process::{Command, ExitCode};

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
  help     Show this help

Use video-utils <COMMAND> --help for worker options.
Analyze: video-utils analyze INPUT [--run-dir DIR] [--backend stdlib|librosa] [--bpm BPM]

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
