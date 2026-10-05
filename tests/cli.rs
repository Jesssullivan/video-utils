use std::fs;
use std::path::PathBuf;
use std::process::Command;
use std::sync::atomic::{AtomicUsize, Ordering};

static NEXT_FIXTURE: AtomicUsize = AtomicUsize::new(0);

struct Fixture(PathBuf);

impl Fixture {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "video utils cli {} {}",
            std::process::id(),
            NEXT_FIXTURE.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(path.join("scripts")).unwrap();
        Self(path)
    }

    fn command(&self) -> Command {
        let mut command = Command::new(env!("CARGO_BIN_EXE_video-utils"));
        command.env("VIDEO_UTILS_ROOT", &self.0);
        command.env("VIDEO_UTILS_PYTHON", "/bin/sh");
        command
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[test]
fn help_and_version_do_not_require_workers() {
    let fixture = Fixture::new();
    let output = fixture.command().arg("--help").output().unwrap();
    assert!(output.status.success());
    assert!(String::from_utf8_lossy(&output.stdout).contains("analyze"));
    let output = fixture.command().arg("--version").output().unwrap();
    assert!(output.status.success());
    assert_eq!(
        String::from_utf8_lossy(&output.stdout).trim(),
        "video-utils 0.1.0"
    );
}

#[test]
fn unknown_command_and_missing_worker_report_actionable_errors() {
    let fixture = Fixture::new();
    for (args, expected) in [
        (vec!["wrong"], "unknown command"),
        (vec!["probe", "take.mov"], "worker missing"),
    ] {
        let output = fixture.command().args(args).output().unwrap();
        assert_eq!(output.status.code(), Some(2));
        assert!(String::from_utf8_lossy(&output.stderr).contains(expected));
    }
}

#[cfg(unix)]
#[test]
fn filenames_and_arguments_are_forwarded_without_shell_interpretation() {
    let fixture = Fixture::new();
    fs::write(
        fixture.0.join("scripts/media.py"),
        "printf '%s\\n' \"$@\"\n",
    )
    .unwrap();
    let filename = "Movie on 10-5-26 at 3.38 PM $(unexpected);.mov";
    let output = fixture
        .command()
        .args(["probe", filename])
        .output()
        .unwrap();
    assert!(output.status.success());
    assert_eq!(
        String::from_utf8_lossy(&output.stdout),
        format!("probe\n{filename}\n")
    );

    fs::write(
        fixture.0.join("scripts/rhythm.py"),
        "printf '%s\\n' \"$@\"\n",
    )
    .unwrap();
    let output = fixture
        .command()
        .args(["analyze", filename])
        .output()
        .unwrap();
    assert!(output.status.success());
    assert_eq!(
        String::from_utf8_lossy(&output.stdout),
        format!("{filename}\n")
    );
}

#[cfg(unix)]
#[test]
fn worker_exit_status_reaches_the_caller() {
    let fixture = Fixture::new();
    fs::write(fixture.0.join("scripts/report.py"), "exit 23\n").unwrap();
    let output = fixture.command().args(["report", "run"]).output().unwrap();
    assert_eq!(output.status.code(), Some(23));
    assert!(String::from_utf8_lossy(&output.stderr).contains("report.py failed"));
}
