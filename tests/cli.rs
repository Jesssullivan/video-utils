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
        "video-utils 0.2.0"
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
    let filename = "Take on 1-2-03 at 4.56 PM $(unexpected);.mov";
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
    let small = dir.join("Take on 1-2-03 at 4.56\u{202f}PM $(x); abc.txt");
    let large = dir.join("Take on 1-2-03 at 4.56\u{202f}PM $(x); million a.bin");
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
        let source = root.join("Take on 1-2-03 at 4.56\u{202f}PM.mov");
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
        Some("video-utils 0.2.0 verify-run")
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

/// The default receipt for the identity fixture, with its temporary paths, sizes and manifest hash replaced.
/// It must not change when the manifest contract grows (docs/spec/TIMELINE_CONTRACT.md).
const IDENTITY_RECEIPT_GOLDEN: &str = r#"{
  "bytes_hashed": "<BYTES_HASHED>",
  "canonical_run_dir": "<CANONICAL_RUN_DIR>",
  "claim_scope": "byte identity of listed files and typed manifest-field validity only; not media quality, decoded PCM extent, timing accuracy, export integrity or listening acceptance",
  "detail": null,
  "dsp_latency": {
    "denoise_delay_samples": null,
    "denoise_status": null
  },
  "export_receipt_verified": "not_checked",
  "kind": "video_utils_verify_run_receipt",
  "listening_accepted": null,
  "manifest_bytes": "<MANIFEST_BYTES>",
  "manifest_schema_version": 1,
  "manifest_sha256": "<MANIFEST_SHA256>",
  "manifest_status": "rendered_unreviewed",
  "media_decoded": false,
  "outputs": {
    "files": [
      {
        "actual_sha256": "cf787b5c7be77ef6a5de4ead7480f83b4d31c0a904a8d95ba8091f0432445adb",
        "bytes": 27,
        "expected_sha256": "cf787b5c7be77ef6a5de4ead7480f83b4d31c0a904a8d95ba8091f0432445adb",
        "name": "baseline.wav",
        "status": "verified"
      },
      {
        "actual_sha256": "ee9a852900168740cde5ba5023caf47ab5af3e0bc3080af94c0b73652b9a3bc1",
        "bytes": 26,
        "expected_sha256": "ee9a852900168740cde5ba5023caf47ab5af3e0bc3080af94c0b73652b9a3bc1",
        "name": "cleaned.wav",
        "status": "verified"
      },
      {
        "actual_sha256": "228676581713a660d3d9564f4937d83006632c63112d6c30afba1008a109b320",
        "bytes": 28,
        "expected_sha256": "228676581713a660d3d9564f4937d83006632c63112d6c30afba1008a109b320",
        "name": "processed.wav",
        "status": "verified"
      }
    ],
    "total": 3,
    "verified": 3
  },
  "pcm": {
    "channels": 1,
    "codec": "pcm_f32le",
    "sample_count": 6657385,
    "sample_rate": 44100
  },
  "pcm_extent_basis": "metadata_only_no_decode",
  "pcm_extent_verified": false,
  "physical_audio_video_sync_verified": null,
  "read_budget_bytes": 8589934592,
  "reason": null,
  "run_dir": "<RUN_DIR>",
  "run_id": "20261006T000000Z-fixture run 3.38 PM",
  "schema_version": 1,
  "source": {
    "actual_sha256": "f3216c010c3f0d9264d7e49f91666473d58c2aecee32a2ec538dd9d93bee9adf",
    "bytes": 26,
    "expected_sha256": "f3216c010c3f0d9264d7e49f91666473d58c2aecee32a2ec538dd9d93bee9adf",
    "path": "<SOURCE>",
    "status": "verified"
  },
  "status": "verified",
  "subprocesses_launched": 0,
  "timeline": {
    "audio_start_seconds": 0.0,
    "format_start_seconds": 0.0,
    "no_time_stretch": true
  },
  "verifier": "video-utils 0.2.0 verify-run"
}
"#;

fn normalised_identity_receipt(run: &RunFixture, stdout: Vec<u8>, manifest: &str) -> String {
    let canonical = fs::canonicalize(&run.run_dir).unwrap();
    let hashed = 2 * manifest.len()
        + OUTPUTS.iter().map(|(_, bytes)| bytes.len()).sum::<usize>()
        + b"fixture source media bytes".len();
    String::from_utf8(stdout)
        .unwrap()
        .replace(
            &format!(
                "\"canonical_run_dir\": {}",
                json_string(canonical.to_str().unwrap())
            ),
            "\"canonical_run_dir\": \"<CANONICAL_RUN_DIR>\"",
        )
        .replace(
            &format!(
                "\"run_dir\": {}",
                json_string(run.run_dir.to_str().unwrap())
            ),
            "\"run_dir\": \"<RUN_DIR>\"",
        )
        .replace(&json_string(run.source.to_str().unwrap()), "\"<SOURCE>\"")
        .replace(&digest(manifest.as_bytes()).to_hex(), "<MANIFEST_SHA256>")
        .replace(
            &format!("\"manifest_bytes\": {}", manifest.len()),
            "\"manifest_bytes\": \"<MANIFEST_BYTES>\"",
        )
        .replace(
            &format!("\"bytes_hashed\": {hashed}"),
            "\"bytes_hashed\": \"<BYTES_HASHED>\"",
        )
}

#[cfg(unix)]
#[test]
fn verify_run_identity_receipt_is_byte_identical_to_the_golden() {
    let fixture = Fixture::new();
    let run = RunFixture::new(&fixture, "golden");
    let output = fixture
        .command()
        .arg("verify-run")
        .arg(&run.run_dir)
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(0));
    let text = normalised_identity_receipt(&run, output.stdout, &run.manifest());
    assert_eq!(text, IDENTITY_RECEIPT_GOLDEN);
}

// ---------------------------------------------------------------------------
// Native `timeline`: the condense EDL contract (src/timeline.rs).

use video_utils::timeline::{Edl, Timeline};

const TIMELINE_EDL: &str = r#"{"fps": 30, "rules": {}, "expected_total_s": 1.633, "clips": [{
  "name": "talk", "duration": 6.0, "shift": 0.1, "speed": 2.0, "welcome": null,
  "expected_s": 1.633, "out_s_by_kind": {"speech": 1.333, "cut": 0.3},
  "segments": [
    {"src": "talk", "inp": 0.0, "out": 2.0, "speed": 2.0, "kind": "speech", "frames": 30, "out_dur": 1.0, "gain": 1.0},
    {"src": "talk", "inp": 2.0, "out": 4.0, "speed": 1.0, "kind": "cut", "frames": 9, "out_dur": 0.3, "gain": 1.0,
     "keep": [[2.0, 2.1666666666666665], [3.8666666666666667, 4.0]]},
    {"src": "talk", "inp": 4.0, "out": 6.0, "speed": 6.0, "kind": "speech", "frames": 10, "out_dur": 0.333333, "gain": 1.0}]}]}"#;

fn timeline_run(
    fixture: &Fixture,
    args: &[&str],
    stdin: Option<&str>,
) -> (Option<i32>, Value, String) {
    use std::io::Write as _;
    use std::process::Stdio;
    let mut child = fixture
        .command()
        .arg("timeline")
        .args(args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let mut input = child.stdin.take().unwrap();
    if let Err(error) = input.write_all(stdin.unwrap_or("").as_bytes()) {
        // A refusal can exit before it reads stdin.
        assert_eq!(error.kind(), std::io::ErrorKind::BrokenPipe, "{error}");
    }
    drop(input);
    let output = child.wait_with_output().unwrap();
    let stderr = String::from_utf8_lossy(&output.stderr).into_owned();
    let receipt = if output.stdout.is_empty() {
        Value::Null
    } else {
        receipt_of(&output.stdout)
    };
    (output.status.code(), receipt, stderr)
}

fn number(value: &Value) -> f64 {
    value.as_number().expect("a number").as_f64()
}

#[test]
fn timeline_validate_prints_a_receipt_with_the_edl_hash() {
    let fixture = Fixture::new();
    let edl = fixture.0.join("edl.json");
    fs::write(&edl, TIMELINE_EDL).unwrap();
    let (code, receipt, stderr) =
        timeline_run(&fixture, &["validate", edl.to_str().unwrap()], None);
    assert_eq!(code, Some(0), "{stderr}");
    assert_eq!(field(&receipt, &["status"]).as_str(), Some("ok"));
    assert_eq!(field(&receipt, &["reason"]), &Value::Null);
    assert_eq!(as_u64(field(&receipt, &["total_frames"])), 49);
    assert_eq!(as_u64(field(&receipt, &["segments"])), 3);
    assert_eq!(
        field(&receipt, &["edl_sha256"]).as_str(),
        Some(digest(TIMELINE_EDL.as_bytes()).to_hex().as_str())
    );
    let (code, receipt, _) = timeline_run(&fixture, &["validate", "-"], Some(TIMELINE_EDL));
    assert_eq!(
        (code, field(&receipt, &["status"]).as_str()),
        (Some(0), Some("ok"))
    );
}

#[test]
fn timeline_map_answers_a_batch_exactly_like_the_library() {
    let fixture = Fixture::new();
    let edl_path = fixture.0.join("edl.json");
    fs::write(&edl_path, TIMELINE_EDL).unwrap();
    let edl = Edl::parse(TIMELINE_EDL.as_bytes()).unwrap();
    let tl = Timeline::new(&edl);
    let times = [-1.0, 0.0, 0.7, 1.999, 2.1, 2.5, 3.9, 4.0, 5.3, 6.0];
    let mut queries = Vec::new();
    for t in times {
        queries.push(format!(
            r#"{{"op": "to_out", "clip": "talk", "source_s": {t:?}}}"#
        ));
        queries.push(format!(
            r#"{{"op": "to_out", "clip": "talk", "source_s": {t:?}, "snap": true}}"#
        ));
        queries.push(format!(
            r#"{{"op": "row", "clip": "talk", "source_s": {t:?}}}"#
        ));
        queries.push(format!(r#"{{"op": "to_src", "output_s": {:?}}}"#, t / 4.0));
    }
    let batch = format!(r#"{{"queries": [{}]}}"#, queries.join(","));
    let (code, receipt, stderr) = timeline_run(
        &fixture,
        &["map", edl_path.to_str().unwrap(), "-"],
        Some(&batch),
    );
    assert_eq!(code, Some(0), "{stderr}");
    let Value::Array(results) = field(&receipt, &["results"]) else {
        panic!("results")
    };
    assert_eq!(results.len(), times.len() * 4);
    let mut answered = 0;
    for (i, t) in times.iter().enumerate() {
        let got = &results[i * 4..i * 4 + 4];
        for (snap, value) in [(false, &got[0]), (true, &got[1])] {
            match tl.to_out("talk", *t, snap) {
                None => assert_eq!(value, &Value::Null, "to_out {t} snap {snap}"),
                Some(out) => assert_eq!(number(value).to_bits(), out.to_bits(), "to_out {t}"),
            }
        }
        match tl.row("talk", *t) {
            None => assert_eq!(&got[2], &Value::Null),
            Some(row) => {
                assert_eq!(as_u64(field(&got[2], &["segment_index"])), row as u64);
                assert_eq!(
                    field(&got[2], &["kind"]).as_str(),
                    Some(tl.segment(row).kind.as_str())
                );
            }
        }
        match tl.to_src(t / 4.0) {
            None => assert_eq!(&got[3], &Value::Null),
            Some((source, row)) => {
                assert_eq!(
                    number(field(&got[3], &["source_s"])).to_bits(),
                    source.to_bits()
                );
                assert_eq!(as_u64(field(&got[3], &["segment_index"])), row as u64);
            }
        }
        answered += 4;
    }
    assert_eq!(answered, 40);
    assert_eq!(tl.to_out("talk", 2.5, false), None, "the cut drops 2.5 s");
}

#[test]
fn timeline_table_and_quantise_reproduce_the_condense_rules() {
    let fixture = Fixture::new();
    let edl = fixture.0.join("edl.json");
    fs::write(&edl, TIMELINE_EDL).unwrap();
    let (code, receipt, _) = timeline_run(&fixture, &["table", edl.to_str().unwrap()], None);
    assert_eq!(code, Some(0));
    let Value::Array(rows) = field(&receipt, &["rows"]) else {
        panic!("rows")
    };
    let frames: Vec<(u64, u64)> = rows
        .iter()
        .map(|r| {
            (
                as_u64(field(r, &["start_frame"])),
                as_u64(field(r, &["end_frame"])),
            )
        })
        .collect();
    assert_eq!(frames, [(0, 30), (30, 39), (39, 49)]);
    let Value::Array(clips) = field(&receipt, &["clips"]) else {
        panic!("clips")
    };
    assert_eq!(number(field(&clips[0], &["shift"])), 0.1);
    // talk-condense tests/test_edl.py: a blip too short for a frame joins its neighbour
    let segments = r#"{"segments": [
      {"src": "x", "inp": 0.0, "out": 2.0, "speed": 2.0, "kind": "speech"},
      {"src": "x", "inp": 2.0, "out": 2.1, "speed": 8.0, "kind": "filler"},
      {"src": "x", "inp": 2.1, "out": 4.0, "speed": 1.0, "kind": "cut", "keep": [[2.1, 2.2], [3.9, 4.0]]},
      {"src": "x", "inp": 4.0, "out": 6.0, "speed": 2.0, "kind": "speech"}]}"#;
    let (code, receipt, stderr) =
        timeline_run(&fixture, &["quantise", "--fps", "30", "-"], Some(segments));
    assert_eq!(code, Some(0), "{stderr}");
    let Value::Array(out) = field(&receipt, &["segments"]) else {
        panic!("segments")
    };
    let got: Vec<(String, u64)> = out
        .iter()
        .map(|s| {
            (
                field(s, &["kind"]).as_str().unwrap().to_owned(),
                as_u64(field(s, &["frames"])),
            )
        })
        .collect();
    assert_eq!(
        got,
        [
            ("speech".to_owned(), 31),
            ("cut".to_owned(), 6),
            ("speech".to_owned(), 30)
        ]
    );
    assert_eq!(number(field(&out[0], &["out"])), 2.1);
}

#[test]
fn timeline_refusals_are_typed_and_usage_errors_exit_2() {
    let fixture = Fixture::new();
    let edl = fixture.0.join("edl.json");
    fs::write(&edl, TIMELINE_EDL).unwrap();
    let edl = edl.to_str().unwrap();
    let missing = fixture.0.join("missing.json");
    let cases: [(&[&str], Option<&str>, &str); 8] = [
        (
            &["validate", missing.to_str().unwrap()],
            None,
            "edl_unreadable",
        ),
        (&["validate", "-"], Some("{\"fps\": 30"), "invalid_json"),
        (
            &["validate", "-"],
            Some(&TIMELINE_EDL.replace("\"fps\": 30", "\"fps\": 7")),
            "fps_invalid",
        ),
        (
            &["validate", "-"],
            Some(&TIMELINE_EDL.replace("\"frames\": 9", "\"frames\": 8")),
            "frames_invalid",
        ),
        (
            &["map", edl, "-"],
            Some(r#"{"queries": [{"op": "to_out", "clip": "other", "source_s": 1.0}]}"#),
            "clip_unknown",
        ),
        (
            &["map", edl, "-"],
            Some(r#"{"queries": [{"op": "jump", "output_s": 1.0}]}"#),
            "query_invalid",
        ),
        (
            &["map", edl, "-"],
            Some(r#"{"queries": [{"op": "to_src"}]}"#),
            "query_invalid",
        ),
        (
            &["quantise", "--fps", "7", "-"],
            Some(r#"{"segments": []}"#),
            "fps_invalid",
        ),
    ];
    for (args, stdin, reason) in cases {
        let (code, receipt, stderr) = timeline_run(&fixture, args, stdin);
        assert_eq!(code, Some(1), "{args:?}: {stderr}");
        assert_eq!(
            field(&receipt, &["status"]).as_str(),
            Some("failed"),
            "{args:?}"
        );
        assert_eq!(
            field(&receipt, &["reason"]).as_str(),
            Some(reason),
            "{args:?}: {stderr}"
        );
        assert!(
            stderr.contains(&format!("failed: {reason}: ")),
            "{args:?}: {stderr}"
        );
    }
    for args in [
        &[][..],
        &["validate"][..],
        &["frob", edl][..],
        &["map", edl][..],
        &["quantise", "--fps", "thirty", "-"][..],
    ] {
        let (code, receipt, _) = timeline_run(&fixture, args, None);
        assert_eq!((code, &receipt), (Some(2), &Value::Null), "{args:?}");
    }
    let help = fixture
        .command()
        .args(["timeline", "--help"])
        .output()
        .unwrap();
    assert!(help.status.success());
    assert!(String::from_utf8_lossy(&help.stdout).contains("quantise --fps N"));
}

// ---------------------------------------------------------------------------
// `verify-run --timeline edl_v1`: condense runs (docs/spec/TIMELINE_CONTRACT.md).

struct CondenseFixture {
    run_dir: PathBuf,
    source: PathBuf,
}

const CONDENSE_SOURCE: &[u8] = b"fixture talk recording bytes";

impl CondenseFixture {
    fn new(fixture: &Fixture, label: &str) -> Self {
        let root = fixture.0.join(format!("condense {label}"));
        let run_dir = root
            .join("condense")
            .join("20261015T000000Z-talk 3.38\u{202f}PM");
        fs::create_dir_all(&run_dir).unwrap();
        let source = root.join("talk recording.mov");
        fs::write(&source, CONDENSE_SOURCE).unwrap();
        fs::write(run_dir.join("edl.json"), TIMELINE_EDL).unwrap();
        fs::write(run_dir.join("talk.mp4"), b"fixture delivered talk bytes").unwrap();
        fs::write(
            run_dir.join("talk.srt"),
            b"1\n00:00:00,000 --> 00:00:01,000\nHello\n",
        )
        .unwrap();
        let run = Self { run_dir, source };
        run.rewrite_manifest(|m| m);
        run
    }

    fn digest_of(&self, name: &str) -> String {
        digest(&fs::read(self.run_dir.join(name)).unwrap()).to_hex()
    }

    /// The manifest for the files as they are on disk now.
    fn manifest(&self) -> String {
        let outputs: Vec<String> = ["edl.json", "talk.mp4", "talk.srt"]
            .iter()
            .map(|name| format!("    {}: \"{}\"", json_string(name), self.digest_of(name)))
            .collect();
        format!(
            "{{\n  \"schema_version\": 1,\n  \"kind\": \"condense_edit\",\n  \"status\": \"rendered_unreviewed\",\n  \"run_id\": {},\n  \"run_dir\": {},\n  \"sources\": [{{\"clip\": \"talk\", \"path\": {}, \"sha256\": \"{}\"}}],\n  \"output_sha256\": {{\n{}\n  }},\n  \"timeline\": {{\"mapping\": \"edl_v1\", \"no_time_stretch\": false, \"edl\": {{\"file\": \"edl.json\", \"sha256\": \"{}\"}}, \"fps\": 30, \"total_frames\": 49, \"clips\": [{{\"name\": \"talk\", \"shift_seconds\": 0.1}}]}},\n  \"delivery\": {{\"file\": \"talk.mp4\", \"audio_sample_rate\": 48000, \"audio_channels\": 1, \"video_frames\": 49}}\n}}\n",
            json_string(self.run_dir.file_name().unwrap().to_str().unwrap()),
            json_string(self.run_dir.to_str().unwrap()),
            json_string(self.source.to_str().unwrap()),
            digest(CONDENSE_SOURCE).to_hex(),
            outputs.join(",\n"),
            self.digest_of("edl.json"),
        )
    }

    fn rewrite_manifest(&self, edit: impl FnOnce(String) -> String) {
        fs::write(self.run_dir.join("manifest.json"), edit(self.manifest())).unwrap();
    }

    fn snapshot(&self) -> BTreeMap<PathBuf, Vec<u8>> {
        let mut out = BTreeMap::new();
        for entry in fs::read_dir(&self.run_dir).unwrap() {
            let path = entry.unwrap().path();
            out.insert(path.clone(), fs::read(&path).unwrap());
        }
        out.insert(self.source.clone(), fs::read(&self.source).unwrap());
        out
    }
}

fn verify(fixture: &Fixture, args: &[&str], run_dir: &Path) -> (Option<i32>, Value, String) {
    let output = fixture
        .command()
        .arg("verify-run")
        .args(args)
        .arg(run_dir)
        .output()
        .unwrap();
    let stderr = String::from_utf8_lossy(&output.stderr).into_owned();
    let receipt = if output.stdout.is_empty() {
        Value::Null
    } else {
        receipt_of(&output.stdout)
    };
    (output.status.code(), receipt, stderr)
}

#[cfg(unix)]
#[test]
fn verify_run_edl_v1_accepts_a_matching_condense_run() {
    let fixture = Fixture::new();
    let run = CondenseFixture::new(&fixture, "positive");
    let before = run.snapshot();
    let (code, receipt, stderr) = verify(&fixture, &["--timeline", "edl_v1"], &run.run_dir);
    assert_eq!(code, Some(0), "{stderr}");
    assert_eq!(field(&receipt, &["status"]).as_str(), Some("verified"));
    assert_eq!(field(&receipt, &["reason"]), &Value::Null);
    assert_eq!(
        field(&receipt, &["manifest_kind"]).as_str(),
        Some("condense_edit")
    );
    assert_eq!(
        field(&receipt, &["timeline", "mapping"]).as_str(),
        Some("edl_v1")
    );
    assert_eq!(
        field(&receipt, &["timeline", "no_time_stretch"]),
        &Value::Bool(false)
    );
    assert_eq!(
        field(&receipt, &["timeline", "edl_sha256"]).as_str(),
        Some(digest(TIMELINE_EDL.as_bytes()).to_hex().as_str())
    );
    assert_eq!(as_u64(field(&receipt, &["timeline", "total_frames"])), 49);
    assert_eq!(as_u64(field(&receipt, &["timeline", "edl_segments"])), 3);
    assert_eq!(as_u64(field(&receipt, &["outputs", "verified"])), 3);
    assert_eq!(
        field(&receipt, &["sources", "status"]).as_str(),
        Some("verified")
    );
    assert_eq!(as_u64(field(&receipt, &["subprocesses_launched"])), 0);
    assert_eq!(
        run.snapshot(),
        before,
        "verify-run modified the condense run"
    );

    // An absent recording is reported, and fails only on request.
    fs::remove_file(&run.source).unwrap();
    let (code, receipt, _) = verify(&fixture, &["--timeline", "edl_v1"], &run.run_dir);
    assert_eq!(code, Some(0));
    assert_eq!(
        field(&receipt, &["sources", "status"]).as_str(),
        Some("absent_unverified")
    );
    let (code, receipt, _) = verify(
        &fixture,
        &["--require-source", "--timeline", "edl_v1"],
        &run.run_dir,
    );
    assert_eq!(code, Some(1));
    assert_eq!(
        field(&receipt, &["reason"]).as_str(),
        Some("source_missing")
    );
}

type CondenseMutation = fn(&CondenseFixture);

#[cfg(unix)]
#[test]
fn verify_run_edl_v1_refuses_tamper_with_typed_reasons() {
    let cases: [(&str, CondenseMutation, &str); 13] = [
        (
            "no_time_stretch true",
            |run| {
                run.rewrite_manifest(|m| {
                    m.replace("\"no_time_stretch\": false", "\"no_time_stretch\": true")
                })
            },
            "timeline_mapping_invalid",
        ),
        (
            "no_time_stretch absent",
            |run| run.rewrite_manifest(|m| m.replace("\"no_time_stretch\": false, ", "")),
            "timeline_mapping_invalid",
        ),
        (
            "unknown mapping",
            |run| run.rewrite_manifest(|m| m.replace("\"edl_v1\"", "\"edl_v2\"")),
            "timeline_mapping_invalid",
        ),
        (
            "kind absent",
            |run| run.rewrite_manifest(|m| m.replace("  \"kind\": \"condense_edit\",\n", "")),
            "manifest_field_invalid",
        ),
        (
            "edl digest differs from output_sha256",
            |run| {
                let listed = run.digest_of("edl.json");
                run.rewrite_manifest(|m| {
                    m.replacen(&listed, &"0".repeat(64), 2)
                        .replacen(&"0".repeat(64), &listed, 1)
                })
            },
            "manifest_field_invalid",
        ),
        (
            "edl byte changed",
            |run| {
                let path = run.run_dir.join("edl.json");
                let text = fs::read_to_string(&path).unwrap();
                fs::write(path, text.replace("\"speed\": 6.0", "\"speed\": 6.5")).unwrap();
            },
            "output_hash_mismatch",
        ),
        (
            "edl invalid with matching hashes",
            |run| {
                let path = run.run_dir.join("edl.json");
                let text = fs::read_to_string(&path).unwrap();
                fs::write(path, text.replace("\"frames\": 10", "\"frames\": 0")).unwrap();
                run.rewrite_manifest(|m| m);
            },
            "edl_invalid",
        ),
        (
            "fps differs",
            |run| run.rewrite_manifest(|m| m.replace("\"fps\": 30", "\"fps\": 25")),
            "edl_invalid",
        ),
        (
            "total_frames differs",
            |run| {
                run.rewrite_manifest(|m| m.replace("\"total_frames\": 49", "\"total_frames\": 50"))
            },
            "edl_invalid",
        ),
        (
            "delivered frames differ",
            |run| {
                run.rewrite_manifest(|m| m.replace("\"video_frames\": 49", "\"video_frames\": 48"))
            },
            "edl_invalid",
        ),
        (
            "shift differs",
            |run| {
                run.rewrite_manifest(|m| {
                    m.replace("\"shift_seconds\": 0.1", "\"shift_seconds\": 0.2")
                })
            },
            "edl_invalid",
        ),
        (
            "segment source not in sources",
            |run| {
                run.rewrite_manifest(|m| m.replace("[{\"clip\": \"talk\"", "[{\"clip\": \"other\""))
            },
            "edl_invalid",
        ),
        (
            "recording changed",
            |run| fs::write(&run.source, b"fixture talk recording bytes, edited").unwrap(),
            "source_hash_mismatch",
        ),
    ];
    let fixture = Fixture::new();
    for (index, (label, mutate, reason)) in cases.iter().enumerate() {
        let run = CondenseFixture::new(&fixture, &format!("tamper {index}"));
        mutate(&run);
        let before = run.snapshot();
        let (code, receipt, stderr) = verify(&fixture, &["--timeline", "edl_v1"], &run.run_dir);
        assert_eq!(code, Some(1), "{label}: {stderr}");
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
        assert_eq!(
            run.snapshot(),
            before,
            "{label}: verify-run modified the run"
        );
    }
}

#[cfg(unix)]
#[test]
fn each_verifier_refuses_the_other_mapping() {
    let fixture = Fixture::new();
    let condense = CondenseFixture::new(&fixture, "mismatch");
    let (code, receipt, _) = verify(&fixture, &[], &condense.run_dir);
    assert_eq!(code, Some(1));
    assert_eq!(
        field(&receipt, &["reason"]).as_str(),
        Some("time_stretch_not_excluded")
    );
    assert!(
        field(&receipt, &["detail"])
            .as_str()
            .unwrap()
            .contains("requires --timeline edl_v1")
    );

    let take = RunFixture::new(&fixture, "mismatch");
    let (code, receipt, _) = verify(&fixture, &["--timeline", "edl_v1"], &take.run_dir);
    assert_eq!(code, Some(1));
    assert_eq!(
        field(&receipt, &["reason"]).as_str(),
        Some("timeline_mapping_mismatch")
    );

    // An explicit identity mapping is a guitar take: verified by default and by --timeline identity,
    // refused by edl_v1.
    take.rewrite_manifest(|m| {
        m.replace(
            "\"timeline\": {\"no_time_stretch\": true",
            "\"timeline\": {\"mapping\": \"identity\", \"no_time_stretch\": true",
        )
    });
    for args in [&[][..], &["--timeline", "identity"][..]] {
        let (code, receipt, stderr) = verify(&fixture, args, &take.run_dir);
        assert_eq!(code, Some(0), "{args:?}: {stderr}");
        assert_eq!(field(&receipt, &["status"]).as_str(), Some("verified"));
    }
    let (_, receipt, _) = verify(&fixture, &["--timeline", "edl_v1"], &take.run_dir);
    assert_eq!(
        field(&receipt, &["reason"]).as_str(),
        Some("timeline_mapping_mismatch")
    );

    // A non-string or unknown mapping is never read as identity.
    take.rewrite_manifest(|m| {
        m.replace(
            "\"timeline\": {\"no_time_stretch\": true",
            "\"timeline\": {\"mapping\": null, \"no_time_stretch\": true",
        )
    });
    let (code, receipt, _) = verify(&fixture, &[], &take.run_dir);
    assert_eq!(code, Some(1));
    assert_eq!(
        field(&receipt, &["reason"]).as_str(),
        Some("time_stretch_not_excluded")
    );

    let (code, receipt, stderr) = verify(&fixture, &["--timeline", "edl_v2"], &take.run_dir);
    assert_eq!((code, receipt), (Some(2), Value::Null));
    assert!(
        stderr.contains("--timeline takes identity or edl_v1"),
        "{stderr}"
    );
}
