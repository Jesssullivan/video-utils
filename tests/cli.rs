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

// ---------------------------------------------------------------------------
// S2 rust_core: native `hash` and `verify-run` (docs/spec/sprints/RUST_CORE_S2.md).

use std::collections::BTreeMap;
use std::path::Path;
use video_utils::hash::digest;
use video_utils::run_record::json::{Value, parse_object};

const ABC_SHA256: &str = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
const MILLION_A_SHA256: &str = "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0";

fn external_sha256_tool() -> Option<Vec<&'static str>> {
    if Path::new("/usr/bin/shasum").is_file() {
        Some(vec!["/usr/bin/shasum", "-a", "256"])
    } else if Path::new("/usr/bin/sha256sum").is_file() {
        Some(vec!["/usr/bin/sha256sum"])
    } else {
        None
    }
}

#[cfg(unix)]
#[test]
fn hash_matches_fips_digest_and_shasum_for_unicode_space_paths() {
    let fixture = Fixture::new();
    let dir = fixture.0.join("take 3.38\u{202f}PM $(x);");
    fs::create_dir_all(&dir).unwrap();
    let small = dir.join("Movie on 10-5-26 at 3.38\u{202f}PM $(x); abc.txt");
    let large = dir.join("Movie on 10-5-26 at 3.38\u{202f}PM $(x); million a.bin");
    fs::write(&small, b"abc").unwrap();
    fs::write(&large, vec![b'a'; 1_000_000]).unwrap();

    let output = fixture
        .command()
        .args(["hash"])
        .arg(&small)
        .arg(&large)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let expected = format!(
        "{ABC_SHA256}  {}\n{MILLION_A_SHA256}  {}\n",
        small.display(),
        large.display()
    );
    assert_eq!(String::from_utf8(output.stdout.clone()).unwrap(), expected);
    println!("MEASURED M2 fips_digest_matches=2/2");

    match external_sha256_tool() {
        Some(tool) => {
            let external = Command::new(tool[0])
                .args(&tool[1..])
                .arg(&small)
                .arg(&large)
                .output()
                .unwrap();
            assert!(external.status.success());
            assert_eq!(output.stdout, external.stdout, "differs from {}", tool[0]);
            println!("MEASURED M2 external_agreement=2/2 tool={}", tool[0]);
        }
        None => println!("MEASURED M2 external_agreement=skipped reason=no_shasum_or_sha256sum"),
    }

    // A directory is a typed error on stderr; remaining files are still hashed.
    let output = fixture
        .command()
        .args(["hash"])
        .arg(&dir)
        .arg(&small)
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&output.stderr).contains("is_directory"));
    assert_eq!(
        String::from_utf8(output.stdout).unwrap(),
        format!("{ABC_SHA256}  {}\n", small.display())
    );
    let output = fixture
        .command()
        .args(["hash"])
        .arg(dir.join("missing file"))
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&output.stderr).contains("not_found"));
    let output = fixture.command().args(["hash"]).output().unwrap();
    assert_eq!(output.status.code(), Some(2));
}

fn json_string(text: &str) -> String {
    Value::string(text).to_pretty().trim_end().to_owned()
}

struct RunFixture {
    root: PathBuf,
    run_dir: PathBuf,
    source: PathBuf,
}

const OUTPUTS: [(&str, &[u8]); 3] = [
    ("cleaned.wav", b"RIFF cleaned fixture bytes"),
    ("processed.wav", b"RIFF processed fixture bytes"),
    ("baseline.wav", b"RIFF baseline fixture bytes"),
];

impl RunFixture {
    fn new(fixture: &Fixture, label: &str) -> Self {
        let root = fixture.0.join(format!("case {label}"));
        let run_dir = root
            .join("runs")
            .join("20261006T000000Z-fixture run 3.38\u{202f}PM");
        fs::create_dir_all(&run_dir).unwrap();
        let source = root.join("Movie on 10-5-26 at 3.38\u{202f}PM.mov");
        fs::write(&source, b"fixture source media bytes").unwrap();
        for (name, bytes) in OUTPUTS {
            fs::write(run_dir.join(name), bytes).unwrap();
        }
        let fixture = Self {
            root,
            run_dir,
            source,
        };
        fs::write(fixture.manifest_path(), fixture.manifest()).unwrap();
        fixture
    }

    fn manifest_path(&self) -> PathBuf {
        self.run_dir.join("manifest.json")
    }

    fn manifest(&self) -> String {
        let outputs: Vec<String> = OUTPUTS
            .iter()
            .map(|(name, bytes)| {
                format!("    {}: \"{}\"", json_string(name), digest(bytes).to_hex())
            })
            .collect();
        format!(
            "{{\n  \"schema_version\": 1,\n  \"run_id\": {},\n  \"run_dir\": {},\n  \"source\": {{\"path\": {}, \"sha256\": \"{}\"}},\n  \"output_sha256\": {{\n{}\n  }},\n  \"timeline\": {{\"no_time_stretch\": true, \"audio_start_seconds\": 0.0, \"format_start_seconds\": 0.0}},\n  \"pcm\": {{\"sample_rate\": 44100, \"channels\": 1, \"sample_count\": 6657385, \"codec\": \"pcm_f32le\"}},\n  \"status\": \"rendered_unreviewed\"\n}}\n",
            json_string(self.run_dir.file_name().unwrap().to_str().unwrap()),
            json_string(self.run_dir.to_str().unwrap()),
            json_string(self.source.to_str().unwrap()),
            digest(b"fixture source media bytes").to_hex(),
            outputs.join(",\n")
        )
    }

    /// Byte snapshot of every entry under the fixture root (symlinks by target).
    fn snapshot(&self) -> BTreeMap<PathBuf, Vec<u8>> {
        fn walk(dir: &Path, out: &mut BTreeMap<PathBuf, Vec<u8>>) {
            let mut entries: Vec<_> = fs::read_dir(dir)
                .unwrap()
                .map(|e| e.unwrap().path())
                .collect();
            entries.sort();
            for path in entries {
                let meta = fs::symlink_metadata(&path).unwrap();
                if meta.file_type().is_symlink() {
                    let target = fs::read_link(&path).unwrap();
                    out.insert(path, format!("symlink:{}", target.display()).into_bytes());
                } else if meta.is_dir() {
                    out.insert(path.clone(), b"dir".to_vec());
                    walk(&path, out);
                } else {
                    out.insert(path.clone(), fs::read(&path).unwrap());
                }
            }
        }
        let mut out = BTreeMap::new();
        walk(&self.root, &mut out);
        out
    }

    fn rewrite_manifest(&self, edit: impl FnOnce(String) -> String) {
        let text = edit(self.manifest());
        fs::write(self.manifest_path(), text).unwrap();
    }
}

fn receipt_of(stdout: &[u8]) -> Value {
    parse_object(stdout).unwrap_or_else(|error| {
        panic!(
            "receipt is not strict JSON ({error}): {}",
            String::from_utf8_lossy(stdout)
        )
    })
}

fn field<'a>(value: &'a Value, path: &[&str]) -> &'a Value {
    path.iter().fold(value, |node, key| {
        node.get(key)
            .unwrap_or_else(|| panic!("receipt lacks {path:?}"))
    })
}

fn as_u64(value: &Value) -> u64 {
    value
        .as_number()
        .and_then(|n| n.as_u64())
        .expect("exact integer")
}

#[cfg(unix)]
#[test]
fn verify_run_accepts_matching_temp_run_dir() {
    let fixture = Fixture::new();
    let run = RunFixture::new(&fixture, "positive");
    let before = run.snapshot();
    let output = fixture
        .command()
        .arg("verify-run")
        .arg(&run.run_dir)
        .output()
        .unwrap();
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert_eq!(output.status.code(), Some(0), "stderr: {stderr}");
    let receipt = receipt_of(&output.stdout);
    assert_eq!(field(&receipt, &["status"]).as_str(), Some("verified"));
    assert_eq!(field(&receipt, &["reason"]), &Value::Null);
    assert_eq!(as_u64(field(&receipt, &["schema_version"])), 1);
    assert_eq!(as_u64(field(&receipt, &["manifest_schema_version"])), 1);
    assert_eq!(as_u64(field(&receipt, &["outputs", "verified"])), 3);
    assert_eq!(as_u64(field(&receipt, &["outputs", "total"])), 3);
    assert_eq!(
        field(&receipt, &["source", "status"]).as_str(),
        Some("verified")
    );
    assert_eq!(
        field(&receipt, &["source", "path"]).as_str(),
        Some(run.source.to_str().unwrap())
    );
    assert_eq!(
        field(&receipt, &["run_id"]).as_str(),
        Some("20261006T000000Z-fixture run 3.38\u{202f}PM")
    );
    assert_eq!(
        field(&receipt, &["manifest_sha256"]).as_str(),
        Some(digest(run.manifest().as_bytes()).to_hex().as_str())
    );
    assert_eq!(as_u64(field(&receipt, &["pcm", "sample_count"])), 6_657_385);
    assert_eq!(
        field(&receipt, &["timeline", "no_time_stretch"]),
        &Value::Bool(true)
    );
    // Declared unknown/unverified fields are present with their declared values.
    assert_eq!(
        field(&receipt, &["pcm_extent_verified"]),
        &Value::Bool(false)
    );
    assert_eq!(
        field(&receipt, &["pcm_extent_basis"]).as_str(),
        Some("metadata_only_no_decode")
    );
    assert_eq!(
        field(&receipt, &["export_receipt_verified"]).as_str(),
        Some("not_checked")
    );
    assert_eq!(field(&receipt, &["listening_accepted"]), &Value::Null);
    assert_eq!(
        field(&receipt, &["physical_audio_video_sync_verified"]),
        &Value::Null
    );
    assert_eq!(
        field(&receipt, &["dsp_latency", "denoise_delay_samples"]),
        &Value::Null
    );
    assert_eq!(field(&receipt, &["media_decoded"]), &Value::Bool(false));
    assert_eq!(as_u64(field(&receipt, &["subprocesses_launched"])), 0);
    assert_eq!(
        field(&receipt, &["verifier"]).as_str(),
        Some("video-utils 0.1.0 verify-run")
    );
    assert_eq!(run.snapshot(), before, "verify-run modified the fixture");

    // An absent source is reported, not hidden, and only fails on request.
    fs::remove_file(&run.source).unwrap();
    let output = fixture
        .command()
        .arg("verify-run")
        .arg(&run.run_dir)
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(0));
    let receipt = receipt_of(&output.stdout);
    assert_eq!(
        field(&receipt, &["source", "status"]).as_str(),
        Some("absent_unverified")
    );
    let output = fixture
        .command()
        .args(["verify-run", "--require-source"])
        .arg(&run.run_dir)
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    assert_eq!(
        field(&receipt_of(&output.stdout), &["reason"]).as_str(),
        Some("source_missing")
    );
    let output = fixture.command().arg("verify-run").output().unwrap();
    assert_eq!(output.status.code(), Some(2));
    println!("MEASURED M5 exit=0 outputs=3/3 source=verified");
}

type Mutation = fn(&RunFixture);

#[cfg(unix)]
#[test]
fn verify_run_refuses_tamper_with_typed_reasons() {
    let cases: [(&str, Mutation, &str); 11] = [
        (
            "output byte flipped",
            |run| {
                let path = run.run_dir.join("processed.wav");
                let mut bytes = fs::read(&path).unwrap();
                bytes[5] ^= 0x01;
                fs::write(path, bytes).unwrap();
            },
            "output_hash_mismatch",
        ),
        (
            "no_time_stretch false",
            |run| {
                run.rewrite_manifest(|m| {
                    m.replace("\"no_time_stretch\": true", "\"no_time_stretch\": false")
                })
            },
            "time_stretch_not_excluded",
        ),
        (
            "no_time_stretch missing",
            |run| run.rewrite_manifest(|m| m.replace("\"no_time_stretch\": true, ", "")),
            "time_stretch_not_excluded",
        ),
        (
            "schema_version 2",
            |run| {
                run.rewrite_manifest(|m| {
                    m.replace("\"schema_version\": 1", "\"schema_version\": 2")
                })
            },
            "schema_version_unsupported",
        ),
        (
            "source changed",
            |run| fs::write(&run.source, b"fixture source media bytes, edited").unwrap(),
            "source_hash_mismatch",
        ),
        (
            "output replaced by symlink",
            |run| {
                let path = run.run_dir.join("baseline.wav");
                let elsewhere = run.root.join("baseline elsewhere.wav");
                fs::rename(&path, &elsewhere).unwrap();
                std::os::unix::fs::symlink(&elsewhere, &path).unwrap();
            },
            "output_not_regular",
        ),
        (
            "traversal output key",
            |run| run.rewrite_manifest(|m| m.replace("\"cleaned.wav\":", "\"../x\":")),
            "unsafe_output_name",
        ),
        (
            "duplicate key",
            |run| {
                run.rewrite_manifest(|m| {
                    m.replace(
                        "\"schema_version\": 1,",
                        "\"schema_version\": 1, \"schema_version\": 1,",
                    )
                })
            },
            "manifest_invalid_json",
        ),
        (
            "NaN literal",
            |run| {
                run.rewrite_manifest(|m| {
                    m.replace(
                        "\"audio_start_seconds\": 0.0",
                        "\"audio_start_seconds\": NaN",
                    )
                })
            },
            "manifest_invalid_json",
        ),
        (
            "manifest over 2 MiB",
            |run| {
                run.rewrite_manifest(|m| {
                    let pad = 2 * 1024 * 1024 + 1 - m.len();
                    m + &" ".repeat(pad)
                })
            },
            "manifest_too_large",
        ),
        (
            "wrong run_dir",
            |run| {
                let wrong = run.root.join("runs");
                let original = json_string(run.run_dir.to_str().unwrap());
                let replacement = json_string(wrong.to_str().unwrap());
                run.rewrite_manifest(|m| m.replacen(&original, &replacement, 1));
            },
            "run_dir_mismatch",
        ),
    ];
    let fixture = Fixture::new();
    let mut refused = 0;
    let mut unchanged = 0;
    for (index, (label, mutate, reason)) in cases.iter().enumerate() {
        let run = RunFixture::new(&fixture, &format!("tamper {index}"));
        mutate(&run);
        let before = run.snapshot();
        let output = fixture
            .command()
            .arg("verify-run")
            .arg(&run.run_dir)
            .output()
            .unwrap();
        let stderr = String::from_utf8_lossy(&output.stderr).into_owned();
        assert_eq!(output.status.code(), Some(1), "{label}: stderr {stderr}");
        let receipt = receipt_of(&output.stdout);
        assert_eq!(
            field(&receipt, &["status"]).as_str(),
            Some("failed"),
            "{label}"
        );
        assert_eq!(
            field(&receipt, &["reason"]).as_str(),
            Some(*reason),
            "{label}: {stderr}"
        );
        assert!(
            stderr.contains(&format!("video-utils: verify-run failed: {reason}: ")),
            "{label}: {stderr}"
        );
        refused += 1;
        assert_eq!(
            run.snapshot(),
            before,
            "{label}: verify-run modified the fixture"
        );
        unchanged += 1;
    }
    println!(
        "MEASURED M6 typed_refusals={refused}/{} byte_identical={unchanged}/{}",
        cases.len(),
        cases.len()
    );
}
