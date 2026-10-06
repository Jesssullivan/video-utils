//! Typed run-manifest subset and metadata-only, read-only run verification.
//!
//! The subset mirrors what `scripts/run_demo.py` (`validate_existing`,
//! `snapshot_existing`) and `scripts/rhythm.py` (`input_timeline`) consume.
//! Verification never decodes media, never launches FFmpeg/ffprobe or any
//! other subprocess, never writes, and bounds every read. A `verified`
//! receipt establishes byte identity and typed field validity only; it does
//! not establish media quality, timing accuracy, decoded PCM extent, export
//! integrity or listening acceptance.
//!
//! No external crates are used: `serde_json` is absent from the offline Cargo
//! cache, so a minimal strict RFC 8259 reader lives in [`json`].

use crate::hash::{self, Digest};
use std::collections::BTreeMap;
use std::fmt;
use std::fs::{self, File};
use std::io::{self, Read};
use std::path::{Path, PathBuf};

/// Manifest size bound, equal to `MAX_MANIFEST_BYTES` in `scripts/run_demo.py`.
pub const MAX_MANIFEST_BYTES: u64 = 2 * 1024 * 1024;
/// Maximum container nesting accepted by the JSON reader.
pub const MAX_JSON_DEPTH: usize = 128;
/// Maximum number of `output_sha256` entries.
pub const MAX_OUTPUTS: usize = 64;
/// Total bytes hashed by one verification (outputs + source + manifest).
pub const MAX_VERIFY_READ_BYTES: u64 = 8 * 1024 * 1024 * 1024;
/// Only supported manifest schema.
pub const SUPPORTED_SCHEMA_VERSION: u64 = 1;
/// Receipt schema emitted by `verify-run`.
pub const RECEIPT_SCHEMA_VERSION: u64 = 1;

pub mod json {
    //! Strict RFC 8259 reader with an object-root requirement, a nesting
    //! bound, duplicate-key rejection and exact integer access, plus a
    //! deterministic pretty serializer (sorted keys).

    use super::MAX_JSON_DEPTH;
    use std::collections::BTreeMap;
    use std::fmt;

    #[derive(Debug, Clone, PartialEq)]
    pub struct Number {
        raw: String,
        value: f64,
    }

    impl Number {
        /// Finite f64 value (always finite once parsed).
        pub fn as_f64(&self) -> f64 {
            self.value
        }

        /// Exact unsigned integer from the raw text (no fraction, exponent or sign).
        pub fn as_u64(&self) -> Option<u64> {
            if self.raw.bytes().all(|b| b.is_ascii_digit()) {
                self.raw.parse().ok()
            } else {
                None
            }
        }

        pub fn raw(&self) -> &str {
            &self.raw
        }

        pub fn from_u64(value: u64) -> Self {
            Self {
                raw: value.to_string(),
                value: value as f64,
            }
        }

        /// Finite values only; callers map non-finite to `Value::Null`.
        pub fn from_f64(value: f64) -> Option<Self> {
            value.is_finite().then(|| Self {
                raw: format!("{value:?}"),
                value,
            })
        }
    }

    #[derive(Debug, Clone, PartialEq)]
    pub enum Value {
        Null,
        Bool(bool),
        Number(Number),
        String(String),
        Array(Vec<Value>),
        Object(BTreeMap<String, Value>),
    }

    impl Value {
        pub fn get(&self, key: &str) -> Option<&Value> {
            match self {
                Self::Object(map) => map.get(key),
                _ => None,
            }
        }

        pub fn as_object(&self) -> Option<&BTreeMap<String, Value>> {
            match self {
                Self::Object(map) => Some(map),
                _ => None,
            }
        }

        pub fn as_str(&self) -> Option<&str> {
            match self {
                Self::String(text) => Some(text),
                _ => None,
            }
        }

        pub fn as_number(&self) -> Option<&Number> {
            match self {
                Self::Number(number) => Some(number),
                _ => None,
            }
        }

        pub fn string(text: impl Into<String>) -> Self {
            Self::String(text.into())
        }

        pub fn u64(value: u64) -> Self {
            Self::Number(Number::from_u64(value))
        }

        pub fn f64(value: f64) -> Self {
            Number::from_f64(value).map_or(Self::Null, Self::Number)
        }

        pub fn opt_string(value: Option<&str>) -> Self {
            value.map_or(Self::Null, Self::string)
        }

        pub fn opt_bool(value: Option<bool>) -> Self {
            value.map_or(Self::Null, Self::Bool)
        }

        /// Two-space indented JSON with sorted keys and a trailing newline.
        pub fn to_pretty(&self) -> String {
            let mut out = String::new();
            write_value(self, 0, &mut out);
            out.push('\n');
            out
        }
    }

    fn write_string(text: &str, out: &mut String) {
        out.push('"');
        for ch in text.chars() {
            match ch {
                '"' => out.push_str("\\\""),
                '\\' => out.push_str("\\\\"),
                '\n' => out.push_str("\\n"),
                '\r' => out.push_str("\\r"),
                '\t' => out.push_str("\\t"),
                c if (c as u32) < 0x20 || c == '\u{7f}' => {
                    out.push_str(&format!("\\u{:04x}", c as u32));
                }
                c => out.push(c),
            }
        }
        out.push('"');
    }

    fn indent(level: usize, out: &mut String) {
        for _ in 0..level {
            out.push_str("  ");
        }
    }

    fn write_value(value: &Value, level: usize, out: &mut String) {
        match value {
            Value::Null => out.push_str("null"),
            Value::Bool(flag) => out.push_str(if *flag { "true" } else { "false" }),
            Value::Number(number) => out.push_str(number.raw()),
            Value::String(text) => write_string(text, out),
            Value::Array(items) if items.is_empty() => out.push_str("[]"),
            Value::Array(items) => {
                out.push_str("[\n");
                for (index, item) in items.iter().enumerate() {
                    indent(level + 1, out);
                    write_value(item, level + 1, out);
                    out.push_str(if index + 1 < items.len() { ",\n" } else { "\n" });
                }
                indent(level, out);
                out.push(']');
            }
            Value::Object(map) if map.is_empty() => out.push_str("{}"),
            Value::Object(map) => {
                out.push_str("{\n");
                for (index, (key, item)) in map.iter().enumerate() {
                    indent(level + 1, out);
                    write_string(key, out);
                    out.push_str(": ");
                    write_value(item, level + 1, out);
                    out.push_str(if index + 1 < map.len() { ",\n" } else { "\n" });
                }
                indent(level, out);
                out.push('}');
            }
        }
    }

    #[derive(Debug, Clone, PartialEq, Eq)]
    pub struct ParseError {
        pub offset: usize,
        pub message: &'static str,
    }

    impl fmt::Display for ParseError {
        fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
            write!(f, "{} at byte {}", self.message, self.offset)
        }
    }

    impl std::error::Error for ParseError {}

    /// Parse UTF-8 bytes whose root must be a JSON object.
    pub fn parse_object(bytes: &[u8]) -> Result<Value, ParseError> {
        let text = std::str::from_utf8(bytes).map_err(|error| ParseError {
            offset: error.valid_up_to(),
            message: "invalid UTF-8",
        })?;
        let mut parser = Parser {
            bytes: text.as_bytes(),
            pos: 0,
        };
        parser.skip_ws();
        if parser.peek() != Some(b'{') {
            return Err(parser.error("root must be a JSON object"));
        }
        let value = parser.value(0)?;
        parser.skip_ws();
        if parser.pos != parser.bytes.len() {
            return Err(parser.error("trailing data after JSON value"));
        }
        Ok(value)
    }

    struct Parser<'a> {
        bytes: &'a [u8],
        pos: usize,
    }

    impl Parser<'_> {
        fn error(&self, message: &'static str) -> ParseError {
            ParseError {
                offset: self.pos,
                message,
            }
        }

        fn peek(&self) -> Option<u8> {
            self.bytes.get(self.pos).copied()
        }

        fn skip_ws(&mut self) {
            while matches!(self.peek(), Some(b' ' | b'\t' | b'\n' | b'\r')) {
                self.pos += 1;
            }
        }

        fn expect(&mut self, byte: u8, message: &'static str) -> Result<(), ParseError> {
            if self.peek() == Some(byte) {
                self.pos += 1;
                Ok(())
            } else {
                Err(self.error(message))
            }
        }

        fn literal(&mut self, word: &'static [u8], value: Value) -> Result<Value, ParseError> {
            if self.bytes[self.pos..].starts_with(word) {
                self.pos += word.len();
                Ok(value)
            } else {
                Err(self.error("invalid literal (NaN/Infinity are not JSON)"))
            }
        }

        fn value(&mut self, depth: usize) -> Result<Value, ParseError> {
            self.skip_ws();
            match self.peek() {
                Some(b'{') => self.object(depth + 1),
                Some(b'[') => self.array(depth + 1),
                Some(b'"') => self.string().map(Value::String),
                Some(b't') => self.literal(b"true", Value::Bool(true)),
                Some(b'f') => self.literal(b"false", Value::Bool(false)),
                Some(b'n') => self.literal(b"null", Value::Null),
                Some(b'-' | b'0'..=b'9') => self.number().map(Value::Number),
                Some(_) => Err(self.error("unexpected character (NaN/Infinity are not JSON)")),
                None => Err(self.error("unexpected end of input")),
            }
        }

        fn object(&mut self, depth: usize) -> Result<Value, ParseError> {
            if depth > MAX_JSON_DEPTH {
                return Err(self.error("nesting exceeds 128 levels"));
            }
            self.pos += 1;
            let mut map = BTreeMap::new();
            self.skip_ws();
            if self.peek() == Some(b'}') {
                self.pos += 1;
                return Ok(Value::Object(map));
            }
            loop {
                self.skip_ws();
                if self.peek() != Some(b'"') {
                    return Err(self.error("object key must be a string"));
                }
                let key_offset = self.pos;
                let key = self.string()?;
                self.skip_ws();
                self.expect(b':', "expected ':' after object key")?;
                let item = self.value(depth)?;
                if map.insert(key, item).is_some() {
                    return Err(ParseError {
                        offset: key_offset,
                        message: "duplicate object key",
                    });
                }
                self.skip_ws();
                match self.peek() {
                    Some(b',') => self.pos += 1,
                    Some(b'}') => {
                        self.pos += 1;
                        return Ok(Value::Object(map));
                    }
                    _ => return Err(self.error("expected ',' or '}' in object")),
                }
            }
        }

        fn array(&mut self, depth: usize) -> Result<Value, ParseError> {
            if depth > MAX_JSON_DEPTH {
                return Err(self.error("nesting exceeds 128 levels"));
            }
            self.pos += 1;
            let mut items = Vec::new();
            self.skip_ws();
            if self.peek() == Some(b']') {
                self.pos += 1;
                return Ok(Value::Array(items));
            }
            loop {
                items.push(self.value(depth)?);
                self.skip_ws();
                match self.peek() {
                    Some(b',') => self.pos += 1,
                    Some(b']') => {
                        self.pos += 1;
                        return Ok(Value::Array(items));
                    }
                    _ => return Err(self.error("expected ',' or ']' in array")),
                }
            }
        }

        fn hex4(&mut self) -> Result<u32, ParseError> {
            let digits = self
                .bytes
                .get(self.pos..self.pos + 4)
                .ok_or_else(|| self.error("truncated \\u escape"))?;
            let mut value = 0u32;
            for &digit in digits {
                let nibble = (digit as char)
                    .to_digit(16)
                    .ok_or_else(|| self.error("invalid \\u escape"))?;
                value = value * 16 + nibble;
            }
            self.pos += 4;
            Ok(value)
        }

        fn string(&mut self) -> Result<String, ParseError> {
            self.pos += 1;
            let mut out = String::new();
            loop {
                let start = self.pos;
                while let Some(byte) = self.peek() {
                    if byte == b'"' || byte == b'\\' || byte < 0x20 {
                        break;
                    }
                    self.pos += 1;
                }
                // Input is valid UTF-8 and the stop bytes are ASCII, so this
                // slice falls on character boundaries.
                out.push_str(
                    std::str::from_utf8(&self.bytes[start..self.pos])
                        .map_err(|_| self.error("invalid UTF-8"))?,
                );
                match self.peek() {
                    None => return Err(self.error("unterminated string")),
                    Some(b'"') => {
                        self.pos += 1;
                        return Ok(out);
                    }
                    Some(b'\\') => {
                        self.pos += 1;
                        let escape = self
                            .peek()
                            .ok_or_else(|| self.error("unterminated escape"))?;
                        self.pos += 1;
                        match escape {
                            b'"' => out.push('"'),
                            b'\\' => out.push('\\'),
                            b'/' => out.push('/'),
                            b'b' => out.push('\u{8}'),
                            b'f' => out.push('\u{c}'),
                            b'n' => out.push('\n'),
                            b'r' => out.push('\r'),
                            b't' => out.push('\t'),
                            b'u' => {
                                let high = self.hex4()?;
                                let code = if (0xD800..0xDC00).contains(&high) {
                                    if !self.bytes[self.pos..].starts_with(b"\\u") {
                                        return Err(self.error("lone high surrogate"));
                                    }
                                    self.pos += 2;
                                    let low = self.hex4()?;
                                    if !(0xDC00..0xE000).contains(&low) {
                                        return Err(self.error("invalid low surrogate"));
                                    }
                                    0x10000 + ((high - 0xD800) << 10) + (low - 0xDC00)
                                } else if (0xDC00..0xE000).contains(&high) {
                                    return Err(self.error("lone low surrogate"));
                                } else {
                                    high
                                };
                                out.push(
                                    char::from_u32(code)
                                        .ok_or_else(|| self.error("invalid code point"))?,
                                );
                            }
                            _ => return Err(self.error("invalid escape")),
                        }
                    }
                    Some(_) => return Err(self.error("control character in string")),
                }
            }
        }

        fn digits(&mut self) -> usize {
            let start = self.pos;
            while matches!(self.peek(), Some(b'0'..=b'9')) {
                self.pos += 1;
            }
            self.pos - start
        }

        fn number(&mut self) -> Result<Number, ParseError> {
            let start = self.pos;
            if self.peek() == Some(b'-') {
                self.pos += 1;
            }
            match self.peek() {
                Some(b'0') => {
                    self.pos += 1;
                    if matches!(self.peek(), Some(b'0'..=b'9')) {
                        return Err(self.error("leading zero in number"));
                    }
                }
                Some(b'1'..=b'9') => {
                    self.digits();
                }
                _ => return Err(self.error("invalid number")),
            }
            if self.peek() == Some(b'.') {
                self.pos += 1;
                if self.digits() == 0 {
                    return Err(self.error("fraction requires digits"));
                }
            }
            if matches!(self.peek(), Some(b'e' | b'E')) {
                self.pos += 1;
                if matches!(self.peek(), Some(b'+' | b'-')) {
                    self.pos += 1;
                }
                if self.digits() == 0 {
                    return Err(self.error("exponent requires digits"));
                }
            }
            let raw = std::str::from_utf8(&self.bytes[start..self.pos])
                .map_err(|_| self.error("invalid number"))?;
            let value: f64 = raw.parse().map_err(|_| self.error("invalid number"))?;
            if !value.is_finite() {
                return Err(ParseError {
                    offset: start,
                    message: "non-finite or overflowed number",
                });
            }
            Ok(Number {
                raw: raw.to_owned(),
                value,
            })
        }
    }
}

use json::Value;

/// Typed failure reason codes (stable strings in the receipt).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Reason {
    RunDirMissing,
    ManifestMissing,
    ManifestNotRegular,
    ManifestTooLarge,
    ManifestInvalidJson,
    ManifestChanged,
    ManifestFieldInvalid,
    SchemaVersionUnsupported,
    RunIdMismatch,
    RunDirMismatch,
    HashMalformed,
    UnsafeOutputName,
    TimeStretchNotExcluded,
    TimelineStartInvalid,
    PcmInvalid,
    OutputMissing,
    OutputNotRegular,
    OutputHashMismatch,
    SourceMissing,
    SourceNotRegular,
    SourceHashMismatch,
    FileChangedDuringVerification,
    ReadBudgetExceeded,
    ReadError,
}

impl Reason {
    pub fn code(self) -> &'static str {
        match self {
            Self::RunDirMissing => "run_dir_missing",
            Self::ManifestMissing => "manifest_missing",
            Self::ManifestNotRegular => "manifest_not_regular",
            Self::ManifestTooLarge => "manifest_too_large",
            Self::ManifestInvalidJson => "manifest_invalid_json",
            Self::ManifestChanged => "manifest_changed",
            Self::ManifestFieldInvalid => "manifest_field_invalid",
            Self::SchemaVersionUnsupported => "schema_version_unsupported",
            Self::RunIdMismatch => "run_id_mismatch",
            Self::RunDirMismatch => "run_dir_mismatch",
            Self::HashMalformed => "hash_malformed",
            Self::UnsafeOutputName => "unsafe_output_name",
            Self::TimeStretchNotExcluded => "time_stretch_not_excluded",
            Self::TimelineStartInvalid => "timeline_start_invalid",
            Self::PcmInvalid => "pcm_invalid",
            Self::OutputMissing => "output_missing",
            Self::OutputNotRegular => "output_not_regular",
            Self::OutputHashMismatch => "output_hash_mismatch",
            Self::SourceMissing => "source_missing",
            Self::SourceNotRegular => "source_not_regular",
            Self::SourceHashMismatch => "source_hash_mismatch",
            Self::FileChangedDuringVerification => "file_changed_during_verification",
            Self::ReadBudgetExceeded => "read_budget_exceeded",
            Self::ReadError => "read_error",
        }
    }
}

/// A typed failure with human detail.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Failure {
    pub reason: Reason,
    pub detail: String,
}

impl Failure {
    fn new(reason: Reason, detail: impl Into<String>) -> Self {
        Self {
            reason,
            detail: detail.into(),
        }
    }
}

impl fmt::Display for Failure {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.reason.code(), self.detail)
    }
}

impl std::error::Error for Failure {}

#[derive(Debug, Clone, PartialEq)]
pub struct SourceRecord {
    pub path: PathBuf,
    pub sha256: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Timeline {
    /// Always true for a parsed record; false/absent is refused.
    pub no_time_stretch: bool,
    pub audio_start_seconds: f64,
    /// `None` means absent/null (unknown).
    pub format_start_seconds: Option<f64>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Pcm {
    pub sample_rate: u32,
    pub channels: u16,
    pub sample_count: u64,
    pub codec: Option<String>,
}

/// Optional latency evidence; `None` is unknown, never coerced to false/0.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct DspLatency {
    pub denoise_delay_samples: Option<u64>,
    pub denoise_status: Option<String>,
    pub physical_audio_video_sync_verified: Option<bool>,
}

/// Typed subset of `manifest.json` (schema_version 1).
#[derive(Debug, Clone, PartialEq)]
pub struct RunRecord {
    pub schema_version: u64,
    pub run_id: String,
    pub run_dir: PathBuf,
    pub source: SourceRecord,
    pub output_sha256: BTreeMap<String, String>,
    pub timeline: Timeline,
    pub pcm: Pcm,
    pub dsp_latency: DspLatency,
    pub status: Option<String>,
}

fn field_invalid(path: &str, rule: &str) -> Failure {
    Failure::new(Reason::ManifestFieldInvalid, format!("{path} {rule}"))
}

fn optional_string(value: Option<&Value>, path: &str) -> Result<Option<String>, Failure> {
    match value {
        None | Some(Value::Null) => Ok(None),
        Some(Value::String(text)) => Ok(Some(text.clone())),
        Some(_) => Err(field_invalid(path, "must be a string or null")),
    }
}

fn optional_bool(value: Option<&Value>, path: &str) -> Result<Option<bool>, Failure> {
    match value {
        None | Some(Value::Null) => Ok(None),
        Some(Value::Bool(flag)) => Ok(Some(*flag)),
        Some(_) => Err(field_invalid(path, "must be a boolean or null")),
    }
}

/// A plain run-relative basename: no separators, traversal, hidden or drive names.
pub fn is_safe_output_name(name: &str) -> bool {
    !name.is_empty()
        && name != "."
        && name != ".."
        && !name.starts_with('.')
        && !name.contains(['/', '\\', ':', '\0'])
        && !name.contains("..")
}

impl RunRecord {
    /// Validate the typed subset in contract-table order. The first failing
    /// field determines the reason. Identity checks against the run directory
    /// (run_id basename, canonical run_dir) are performed by [`verify_run`].
    pub fn from_json(root: &Value) -> Result<Self, Failure> {
        let schema_version = match root.get("schema_version").and_then(Value::as_number) {
            Some(number) if number.as_u64() == Some(SUPPORTED_SCHEMA_VERSION) => {
                SUPPORTED_SCHEMA_VERSION
            }
            other => {
                let shown = other.map_or_else(
                    || "absent or non-numeric".to_owned(),
                    |n| n.raw().to_owned(),
                );
                return Err(Failure::new(
                    Reason::SchemaVersionUnsupported,
                    format!("schema_version must be 1, found {shown}"),
                ));
            }
        };
        let run_id = match root.get("run_id").and_then(Value::as_str) {
            Some(text) if !text.is_empty() => text.to_owned(),
            _ => {
                return Err(Failure::new(
                    Reason::RunIdMismatch,
                    "run_id must be a non-empty string",
                ));
            }
        };
        let run_dir = match root.get("run_dir").and_then(Value::as_str) {
            Some(text) if Path::new(text).is_absolute() => PathBuf::from(text),
            _ => {
                return Err(Failure::new(
                    Reason::RunDirMismatch,
                    "run_dir must be an absolute path string",
                ));
            }
        };
        let source = root
            .get("source")
            .filter(|value| value.as_object().is_some())
            .ok_or_else(|| field_invalid("source", "must be an object"))?;
        let source_path = match source.get("path").and_then(Value::as_str) {
            Some(text) if Path::new(text).is_absolute() => PathBuf::from(text),
            _ => {
                return Err(field_invalid(
                    "source.path",
                    "must be an absolute path string",
                ));
            }
        };
        let source_sha256 = match source.get("sha256").and_then(Value::as_str) {
            Some(text) if hash::is_lower_hex_digest(text) => text.to_owned(),
            _ => {
                return Err(Failure::new(
                    Reason::HashMalformed,
                    "source.sha256 must be 64 lowercase hex characters",
                ));
            }
        };
        let outputs = root
            .get("output_sha256")
            .and_then(Value::as_object)
            .ok_or_else(|| field_invalid("output_sha256", "must be an object"))?;
        if outputs.is_empty() || outputs.len() > MAX_OUTPUTS {
            return Err(field_invalid("output_sha256", "must list 1..=64 files"));
        }
        let mut output_sha256 = BTreeMap::new();
        for (name, value) in outputs {
            if !is_safe_output_name(name) {
                return Err(Failure::new(
                    Reason::UnsafeOutputName,
                    format!("output_sha256 key {name:?} is not a plain run-relative basename"),
                ));
            }
            match value.as_str() {
                Some(text) if hash::is_lower_hex_digest(text) => {
                    output_sha256.insert(name.clone(), text.to_owned());
                }
                _ => {
                    return Err(Failure::new(
                        Reason::HashMalformed,
                        format!("output_sha256[{name:?}] must be 64 lowercase hex characters"),
                    ));
                }
            }
        }
        let timeline = root
            .get("timeline")
            .filter(|value| value.as_object().is_some())
            .ok_or_else(|| {
                Failure::new(Reason::TimeStretchNotExcluded, "timeline object is absent")
            })?;
        if timeline.get("no_time_stretch") != Some(&Value::Bool(true)) {
            return Err(Failure::new(
                Reason::TimeStretchNotExcluded,
                "timeline.no_time_stretch must be JSON true",
            ));
        }
        let audio_start_seconds = timeline
            .get("audio_start_seconds")
            .and_then(Value::as_number)
            .map(json::Number::as_f64)
            .filter(|value| value.is_finite())
            .ok_or_else(|| {
                Failure::new(
                    Reason::TimelineStartInvalid,
                    "timeline.audio_start_seconds must be a finite number",
                )
            })?;
        let format_start_seconds = match timeline.get("format_start_seconds") {
            None | Some(Value::Null) => None,
            Some(Value::Number(number)) => Some(number.as_f64()),
            Some(_) => {
                return Err(field_invalid(
                    "timeline.format_start_seconds",
                    "must be a number or null",
                ));
            }
        };
        let pcm_value = root
            .get("pcm")
            .filter(|value| value.as_object().is_some())
            .ok_or_else(|| Failure::new(Reason::PcmInvalid, "pcm object is absent"))?;
        let positive = |key: &str| -> Option<u64> {
            pcm_value
                .get(key)
                .and_then(Value::as_number)
                .and_then(json::Number::as_u64)
                .filter(|value| *value > 0)
        };
        let pcm_error = |key: &str| {
            Failure::new(
                Reason::PcmInvalid,
                format!("pcm.{key} must be a positive exact integer in range"),
            )
        };
        let sample_rate = positive("sample_rate")
            .and_then(|value| u32::try_from(value).ok())
            .ok_or_else(|| pcm_error("sample_rate"))?;
        let channels = positive("channels")
            .and_then(|value| u16::try_from(value).ok())
            .ok_or_else(|| pcm_error("channels"))?;
        let sample_count = positive("sample_count").ok_or_else(|| pcm_error("sample_count"))?;
        let codec = optional_string(pcm_value.get("codec"), "pcm.codec")?;
        let latency = root.get("dsp_latency");
        if latency.is_some_and(|value| !matches!(value, Value::Object(_) | Value::Null)) {
            return Err(field_invalid("dsp_latency", "must be an object or null"));
        }
        let denoise = latency.and_then(|value| value.get("denoise"));
        if denoise.is_some_and(|value| !matches!(value, Value::Object(_) | Value::Null)) {
            return Err(field_invalid(
                "dsp_latency.denoise",
                "must be an object or null",
            ));
        }
        let denoise_delay_samples = match denoise.and_then(|value| value.get("delay_samples")) {
            None | Some(Value::Null) => None,
            Some(Value::Number(number)) => Some(number.as_u64().ok_or_else(|| {
                field_invalid(
                    "dsp_latency.denoise.delay_samples",
                    "must be a non-negative exact integer or null",
                )
            })?),
            Some(_) => {
                return Err(field_invalid(
                    "dsp_latency.denoise.delay_samples",
                    "must be a non-negative exact integer or null",
                ));
            }
        };
        let dsp_latency = DspLatency {
            denoise_delay_samples,
            denoise_status: optional_string(
                denoise.and_then(|value| value.get("status")),
                "dsp_latency.denoise.status",
            )?,
            physical_audio_video_sync_verified: optional_bool(
                latency.and_then(|value| value.get("physical_audio_video_sync_verified")),
                "dsp_latency.physical_audio_video_sync_verified",
            )?,
        };
        let status = optional_string(root.get("status"), "status")?;
        Ok(Self {
            schema_version,
            run_id,
            run_dir,
            source: SourceRecord {
                path: source_path,
                sha256: source_sha256,
            },
            output_sha256,
            timeline: Timeline {
                no_time_stretch: true,
                audio_start_seconds,
                format_start_seconds,
            },
            pcm: Pcm {
                sample_rate,
                channels,
                sample_count,
                codec,
            },
            dsp_latency,
            status,
        })
    }
}

/// Verification options.
#[derive(Debug, Clone, Copy, Default)]
pub struct VerifyOptions {
    /// Treat an absent source file as failure `source_missing`.
    pub require_source: bool,
}

/// Per-file result for the receipt.
#[derive(Debug, Clone, PartialEq)]
pub struct FileCheck {
    pub name: String,
    pub expected_sha256: String,
    pub actual_sha256: Option<String>,
    pub bytes: Option<u64>,
    pub status: &'static str,
}

/// Outcome of [`verify_run`]; always renderable as a receipt.
#[derive(Debug, Clone)]
pub struct Verification {
    pub run_dir: PathBuf,
    pub canonical_run_dir: Option<PathBuf>,
    pub manifest_sha256: Option<String>,
    pub manifest_bytes: Option<u64>,
    pub record: Option<RunRecord>,
    pub outputs: Vec<FileCheck>,
    pub source: Option<FileCheck>,
    pub source_status: &'static str,
    pub bytes_hashed: u64,
    pub failure: Option<Failure>,
}

impl Verification {
    pub fn verified(&self) -> bool {
        self.failure.is_none()
    }
}

struct Budget {
    used: u64,
}

impl Budget {
    fn reserve(&mut self, bytes: u64, what: &str) -> Result<(), Failure> {
        match self.used.checked_add(bytes) {
            Some(total) if total <= MAX_VERIFY_READ_BYTES => Ok(()),
            _ => Err(Failure::new(
                Reason::ReadBudgetExceeded,
                format!("hashing {what} would exceed the {MAX_VERIFY_READ_BYTES}-byte read budget"),
            )),
        }
    }
}

#[cfg(unix)]
fn same_file(left: &fs::Metadata, right: &fs::Metadata) -> bool {
    use std::os::unix::fs::MetadataExt;
    left.dev() == right.dev() && left.ino() == right.ino()
}

#[cfg(not(unix))]
fn same_file(left: &fs::Metadata, right: &fs::Metadata) -> bool {
    left.len() == right.len() && left.file_type() == right.file_type()
}

/// Stream at most `limit + 1` bytes, returning digest and count.
fn hash_bounded(file: &mut File, limit: u64) -> io::Result<(Digest, u64)> {
    hash::hash_reader(&mut file.take(limit.saturating_add(1)))
}

#[derive(Clone, Copy)]
enum Role {
    Output,
    Source,
}

/// Hash a regular non-symlink file whose identity and length must stay
/// stable for the duration of the read.
fn hash_stable_file(
    path: &Path,
    role: Role,
    label: &str,
    budget: &mut Budget,
) -> Result<(Digest, u64), Failure> {
    let (missing, not_regular) = match role {
        Role::Output => (Reason::OutputMissing, Reason::OutputNotRegular),
        Role::Source => (Reason::SourceMissing, Reason::SourceNotRegular),
    };
    let before = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            return Err(Failure::new(missing, format!("{label} does not exist")));
        }
        Err(error) => return Err(Failure::new(Reason::ReadError, format!("{label}: {error}"))),
    };
    if before.file_type().is_symlink() || !before.is_file() {
        return Err(Failure::new(
            not_regular,
            format!("{label} is not a regular non-symlink file"),
        ));
    }
    budget.reserve(before.len(), label)?;
    let mut file = File::open(path)
        .map_err(|error| Failure::new(Reason::ReadError, format!("{label}: {error}")))?;
    let opened = file
        .metadata()
        .map_err(|error| Failure::new(Reason::ReadError, format!("{label}: {error}")))?;
    if !opened.is_file() || !same_file(&before, &opened) {
        return Err(Failure::new(
            Reason::FileChangedDuringVerification,
            format!("{label} was replaced between inspection and open"),
        ));
    }
    let (digest, bytes) = hash_bounded(&mut file, before.len())
        .map_err(|error| Failure::new(Reason::ReadError, format!("{label}: {error}")))?;
    budget.used += bytes.min(before.len());
    let after = file
        .metadata()
        .map_err(|error| Failure::new(Reason::ReadError, format!("{label}: {error}")))?;
    if bytes != before.len() || after.len() != before.len() {
        return Err(Failure::new(
            Reason::FileChangedDuringVerification,
            format!("{label} length changed during verification"),
        ));
    }
    Ok((digest, bytes))
}

/// Read the manifest with the size bound; returns bytes and digest.
fn read_manifest(path: &Path) -> Result<(Vec<u8>, Digest), Failure> {
    let before = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            return Err(Failure::new(
                Reason::ManifestMissing,
                "manifest.json does not exist",
            ));
        }
        Err(error) => {
            return Err(Failure::new(
                Reason::ReadError,
                format!("manifest.json: {error}"),
            ));
        }
    };
    if before.file_type().is_symlink() || !before.is_file() {
        return Err(Failure::new(
            Reason::ManifestNotRegular,
            "manifest.json is not a regular non-symlink file",
        ));
    }
    if before.len() > MAX_MANIFEST_BYTES {
        return Err(Failure::new(
            Reason::ManifestTooLarge,
            format!(
                "manifest.json is {} bytes; bound is {MAX_MANIFEST_BYTES}",
                before.len()
            ),
        ));
    }
    let file = File::open(path)
        .map_err(|error| Failure::new(Reason::ReadError, format!("manifest.json: {error}")))?;
    let opened = file
        .metadata()
        .map_err(|error| Failure::new(Reason::ReadError, format!("manifest.json: {error}")))?;
    if !opened.is_file() || !same_file(&before, &opened) {
        return Err(Failure::new(
            Reason::ManifestChanged,
            "manifest.json was replaced before reading",
        ));
    }
    let mut bytes = Vec::with_capacity(before.len() as usize);
    file.take(MAX_MANIFEST_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|error| Failure::new(Reason::ReadError, format!("manifest.json: {error}")))?;
    if bytes.len() as u64 > MAX_MANIFEST_BYTES {
        return Err(Failure::new(
            Reason::ManifestTooLarge,
            "manifest.json grew beyond the bound while reading",
        ));
    }
    let digest = hash::digest(&bytes);
    Ok((bytes, digest))
}

/// Metadata-only, read-only verification of one run directory.
pub fn verify_run(run_dir: &Path, options: VerifyOptions) -> Verification {
    let mut result = Verification {
        run_dir: run_dir.to_path_buf(),
        canonical_run_dir: None,
        manifest_sha256: None,
        manifest_bytes: None,
        record: None,
        outputs: Vec::new(),
        source: None,
        source_status: "not_checked",
        bytes_hashed: 0,
        failure: None,
    };
    if let Err(failure) = verify_into(run_dir, options, &mut result) {
        result.failure = Some(failure);
    }
    result
}

fn verify_into(
    run_dir: &Path,
    options: VerifyOptions,
    result: &mut Verification,
) -> Result<(), Failure> {
    let canonical = match fs::canonicalize(run_dir) {
        Ok(path) if path.is_dir() => path,
        Ok(_) => {
            return Err(Failure::new(
                Reason::RunDirMissing,
                "RUN_DIR is not a directory",
            ));
        }
        Err(error) => {
            return Err(Failure::new(
                Reason::RunDirMissing,
                format!("RUN_DIR: {error}"),
            ));
        }
    };
    result.canonical_run_dir = Some(canonical.clone());
    let manifest_path = canonical.join("manifest.json");
    let mut budget = Budget { used: 0 };
    let (bytes, manifest_digest) = read_manifest(&manifest_path)?;
    budget.used += bytes.len() as u64;
    result.bytes_hashed = budget.used;
    result.manifest_sha256 = Some(manifest_digest.to_hex());
    result.manifest_bytes = Some(bytes.len() as u64);
    let root = json::parse_object(&bytes)
        .map_err(|error| Failure::new(Reason::ManifestInvalidJson, error.to_string()))?;
    drop(bytes);
    let record = RunRecord::from_json(&root)?;
    drop(root);
    result.record = Some(record.clone());

    let basename = canonical
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("");
    if record.run_id != basename {
        return Err(Failure::new(
            Reason::RunIdMismatch,
            format!(
                "run_id {:?} differs from RUN_DIR basename {basename:?}",
                record.run_id
            ),
        ));
    }
    match fs::canonicalize(&record.run_dir) {
        Ok(path) if path == canonical => {}
        _ => {
            return Err(Failure::new(
                Reason::RunDirMismatch,
                "manifest run_dir does not resolve to RUN_DIR",
            ));
        }
    }

    for (name, expected) in &record.output_sha256 {
        let mut check = FileCheck {
            name: name.clone(),
            expected_sha256: expected.clone(),
            actual_sha256: None,
            bytes: None,
            status: "failed",
        };
        let outcome = hash_stable_file(
            &canonical.join(name),
            Role::Output,
            &format!("output {name:?}"),
            &mut budget,
        );
        result.bytes_hashed = budget.used;
        match outcome {
            Ok((digest, length)) => {
                check.actual_sha256 = Some(digest.to_hex());
                check.bytes = Some(length);
                if digest.to_hex() == *expected {
                    check.status = "verified";
                    result.outputs.push(check);
                } else {
                    check.status = "hash_mismatch";
                    result.outputs.push(check);
                    return Err(Failure::new(
                        Reason::OutputHashMismatch,
                        format!("output {name:?} digest differs from manifest"),
                    ));
                }
            }
            Err(failure) => {
                check.status = failure.reason.code();
                result.outputs.push(check);
                return Err(failure);
            }
        }
    }

    let mut source = FileCheck {
        name: record.source.path.to_string_lossy().into_owned(),
        expected_sha256: record.source.sha256.clone(),
        actual_sha256: None,
        bytes: None,
        status: "not_checked",
    };
    let outcome = hash_stable_file(&record.source.path, Role::Source, "source", &mut budget);
    result.bytes_hashed = budget.used;
    match outcome {
        Ok((digest, length)) => {
            source.actual_sha256 = Some(digest.to_hex());
            source.bytes = Some(length);
            if digest.to_hex() == record.source.sha256 {
                source.status = "verified";
                result.source_status = "verified";
                result.source = Some(source);
            } else {
                source.status = "hash_mismatch";
                result.source_status = "hash_mismatch";
                result.source = Some(source);
                return Err(Failure::new(
                    Reason::SourceHashMismatch,
                    "source digest differs from manifest",
                ));
            }
        }
        Err(failure) if failure.reason == Reason::SourceMissing && !options.require_source => {
            source.status = "absent_unverified";
            result.source_status = "absent_unverified";
            result.source = Some(source);
        }
        Err(failure) => {
            source.status = failure.reason.code();
            result.source_status = failure.reason.code();
            result.source = Some(source);
            return Err(failure);
        }
    }

    let (again, digest_again) = read_manifest(&manifest_path).map_err(|failure| {
        Failure::new(
            Reason::ManifestChanged,
            format!("manifest re-read failed: {failure}"),
        )
    })?;
    budget.used += again.len() as u64;
    result.bytes_hashed = budget.used;
    if digest_again != manifest_digest {
        return Err(Failure::new(
            Reason::ManifestChanged,
            "manifest.json changed during verification",
        ));
    }
    Ok(())
}

fn file_check_json(check: &FileCheck) -> Value {
    let mut map = BTreeMap::new();
    map.insert("name".into(), Value::string(&check.name));
    map.insert(
        "expected_sha256".into(),
        Value::string(&check.expected_sha256),
    );
    map.insert(
        "actual_sha256".into(),
        Value::opt_string(check.actual_sha256.as_deref()),
    );
    map.insert("bytes".into(), check.bytes.map_or(Value::Null, Value::u64));
    map.insert("status".into(), Value::string(check.status));
    Value::Object(map)
}

/// Render the verification as the stable `verify-run` receipt.
pub fn receipt(verification: &Verification, verifier: &str) -> Value {
    let mut map = BTreeMap::new();
    let record = verification.record.as_ref();
    map.insert("schema_version".into(), Value::u64(RECEIPT_SCHEMA_VERSION));
    map.insert(
        "kind".into(),
        Value::string("video_utils_verify_run_receipt"),
    );
    map.insert("verifier".into(), Value::string(verifier));
    map.insert(
        "status".into(),
        Value::string(if verification.verified() {
            "verified"
        } else {
            "failed"
        }),
    );
    map.insert(
        "reason".into(),
        Value::opt_string(
            verification
                .failure
                .as_ref()
                .map(|failure| failure.reason.code()),
        ),
    );
    map.insert(
        "detail".into(),
        Value::opt_string(
            verification
                .failure
                .as_ref()
                .map(|failure| failure.detail.as_str()),
        ),
    );
    map.insert(
        "run_dir".into(),
        Value::string(verification.run_dir.to_string_lossy()),
    );
    map.insert(
        "canonical_run_dir".into(),
        Value::opt_string(
            verification
                .canonical_run_dir
                .as_ref()
                .map(|path| path.to_string_lossy())
                .as_deref(),
        ),
    );
    map.insert(
        "run_id".into(),
        Value::opt_string(record.map(|r| r.run_id.as_str())),
    );
    map.insert(
        "manifest_sha256".into(),
        Value::opt_string(verification.manifest_sha256.as_deref()),
    );
    map.insert(
        "manifest_bytes".into(),
        verification.manifest_bytes.map_or(Value::Null, Value::u64),
    );
    map.insert(
        "manifest_schema_version".into(),
        record.map_or(Value::Null, |r| Value::u64(r.schema_version)),
    );
    map.insert(
        "manifest_status".into(),
        Value::opt_string(record.and_then(|r| r.status.as_deref())),
    );

    let verified_outputs = verification
        .outputs
        .iter()
        .filter(|c| c.status == "verified")
        .count();
    let mut outputs = BTreeMap::new();
    outputs.insert("verified".into(), Value::u64(verified_outputs as u64));
    outputs.insert(
        "total".into(),
        record.map_or(Value::Null, |r| Value::u64(r.output_sha256.len() as u64)),
    );
    outputs.insert(
        "files".into(),
        Value::Array(verification.outputs.iter().map(file_check_json).collect()),
    );
    map.insert("outputs".into(), Value::Object(outputs));

    let mut source = BTreeMap::new();
    source.insert("status".into(), Value::string(verification.source_status));
    source.insert(
        "path".into(),
        record.map_or(Value::Null, |r| {
            Value::string(r.source.path.to_string_lossy())
        }),
    );
    source.insert(
        "expected_sha256".into(),
        record.map_or(Value::Null, |r| Value::string(&r.source.sha256)),
    );
    source.insert(
        "actual_sha256".into(),
        Value::opt_string(
            verification
                .source
                .as_ref()
                .and_then(|c| c.actual_sha256.as_deref()),
        ),
    );
    source.insert(
        "bytes".into(),
        verification
            .source
            .as_ref()
            .and_then(|c| c.bytes)
            .map_or(Value::Null, Value::u64),
    );
    map.insert("source".into(), Value::Object(source));

    map.insert(
        "timeline".into(),
        record.map_or(Value::Null, |r| {
            let mut timeline = BTreeMap::new();
            timeline.insert(
                "no_time_stretch".into(),
                Value::Bool(r.timeline.no_time_stretch),
            );
            timeline.insert(
                "audio_start_seconds".into(),
                Value::f64(r.timeline.audio_start_seconds),
            );
            timeline.insert(
                "format_start_seconds".into(),
                r.timeline
                    .format_start_seconds
                    .map_or(Value::Null, Value::f64),
            );
            Value::Object(timeline)
        }),
    );
    map.insert(
        "pcm".into(),
        record.map_or(Value::Null, |r| {
            let mut pcm = BTreeMap::new();
            pcm.insert(
                "sample_rate".into(),
                Value::u64(u64::from(r.pcm.sample_rate)),
            );
            pcm.insert("channels".into(), Value::u64(u64::from(r.pcm.channels)));
            pcm.insert("sample_count".into(), Value::u64(r.pcm.sample_count));
            pcm.insert("codec".into(), Value::opt_string(r.pcm.codec.as_deref()));
            Value::Object(pcm)
        }),
    );
    map.insert(
        "dsp_latency".into(),
        record.map_or(Value::Null, |r| {
            let mut latency = BTreeMap::new();
            latency.insert(
                "denoise_delay_samples".into(),
                r.dsp_latency
                    .denoise_delay_samples
                    .map_or(Value::Null, Value::u64),
            );
            latency.insert(
                "denoise_status".into(),
                Value::opt_string(r.dsp_latency.denoise_status.as_deref()),
            );
            Value::Object(latency)
        }),
    );
    map.insert(
        "physical_audio_video_sync_verified".into(),
        Value::opt_bool(record.and_then(|r| r.dsp_latency.physical_audio_video_sync_verified)),
    );
    map.insert("pcm_extent_verified".into(), Value::Bool(false));
    map.insert(
        "pcm_extent_basis".into(),
        Value::string("metadata_only_no_decode"),
    );
    map.insert(
        "export_receipt_verified".into(),
        Value::string("not_checked"),
    );
    map.insert("listening_accepted".into(), Value::Null);
    map.insert("media_decoded".into(), Value::Bool(false));
    map.insert("subprocesses_launched".into(), Value::u64(0));
    map.insert("bytes_hashed".into(), Value::u64(verification.bytes_hashed));
    map.insert(
        "read_budget_bytes".into(),
        Value::u64(MAX_VERIFY_READ_BYTES),
    );
    map.insert(
        "claim_scope".into(),
        Value::string(
            "byte identity of listed files and typed manifest-field validity only; not media quality, \
             decoded PCM extent, timing accuracy, export integrity or listening acceptance",
        ),
    );
    Value::Object(map)
}

#[cfg(test)]
mod tests {
    use super::json::{Value, parse_object};
    use super::*;

    #[test]
    fn json_accepts_escapes_surrogates_and_unicode() {
        let value = parse_object(
            br#"{"a": "x\"\\\/\b\f\n\r\t", "nb": "3.38\u202fPM", "pair": "\ud83c\udfb8", "n": [1, -0.5, 2e3, 0, -0, 1E-400], "e": {}, "l": []}"#,
        )
        .unwrap();
        assert_eq!(
            value.get("a").unwrap().as_str(),
            Some("x\"\\/\u{8}\u{c}\n\r\t")
        );
        assert_eq!(value.get("nb").unwrap().as_str(), Some("3.38\u{202f}PM"));
        let raw = parse_object("{\"raw\": \"3.38\u{202f}PM\"}".as_bytes()).unwrap();
        assert_eq!(raw.get("raw").unwrap().as_str(), Some("3.38\u{202f}PM"));
        assert_eq!(value.get("pair").unwrap().as_str(), Some("\u{1f3b8}"));
        let Value::Array(numbers) = value.get("n").unwrap() else {
            panic!("array expected")
        };
        assert_eq!(numbers.len(), 6);
        assert_eq!(numbers[2].as_number().unwrap().as_f64(), 2000.0);
        assert_eq!(numbers[2].as_number().unwrap().as_u64(), None);
        assert_eq!(numbers[5].as_number().unwrap().as_f64(), 0.0);
    }

    #[test]
    fn json_rejects_invalid_documents() {
        let deep_ok = format!(
            "{}{}",
            "{\"a\":".repeat(128),
            "1".to_owned() + &"}".repeat(128)
        );
        assert!(parse_object(deep_ok.as_bytes()).is_ok());
        let too_deep = format!(
            "{}{}",
            "{\"a\":".repeat(129),
            "1".to_owned() + &"}".repeat(129)
        );
        let rejects: Vec<&[u8]> = vec![
            b"[1]",
            b"\"s\"",
            b"{\"a\": NaN}",
            b"{\"a\": Infinity}",
            b"{\"a\": -Infinity}",
            b"{\"a\": 1e400}",
            b"{\"a\": -1e999}",
            b"{\"a\": 1} x",
            b"{\"a\": 1}{}",
            b"{\"a\": 1, \"a\": 2}",
            b"{\"a\": \"\\ud800\"}",
            b"{\"a\": \"\\udc00\"}",
            b"{\"a\": \"\\ud800\\u0041\"}",
            b"{\"a\": \"tab\there\"}",
            b"{\"a\": \"\\x\"}",
            b"{\"a\": 01}",
            b"{\"a\": 1.}",
            b"{\"a\": .5}",
            b"{\"a\": +1}",
            b"{\"a\": 1,}",
            b"{\"a\" 1}",
            b"{a: 1}",
            b"\xef\xbb\xbf{}",
            b"{\"a\": \"\xff\"}",
            b"",
            too_deep.as_bytes(),
        ];
        for document in rejects {
            assert!(
                parse_object(document).is_err(),
                "accepted {:?}",
                String::from_utf8_lossy(document)
            );
        }
    }

    #[test]
    fn exact_u64_parsing_of_sample_count() {
        let value = parse_object(b"{\"big\": 18446744073709551615, \"over\": 18446744073709551616, \"near\": 9007199254740993, \"frac\": 6657385.0, \"neg\": -1}").unwrap();
        let get = |key: &str| value.get(key).unwrap().as_number().unwrap().as_u64();
        assert_eq!(get("big"), Some(u64::MAX));
        assert_eq!(get("over"), None);
        assert_eq!(get("near"), Some(9_007_199_254_740_993));
        assert_eq!(get("frac"), None);
        assert_eq!(get("neg"), None);
    }

    #[test]
    fn pretty_round_trip_is_stable() {
        let source = br#"{"b": [1, {"c": null}], "a": "q\"\u0001", "d": true}"#;
        let value = parse_object(source).unwrap();
        let text = value.to_pretty();
        assert_eq!(parse_object(text.as_bytes()).unwrap(), value);
        assert!(text.find("\"a\"").unwrap() < text.find("\"b\"").unwrap());
    }

    fn manifest(extra: &str) -> String {
        format!(
            r#"{{"schema_version": 1, "run_id": "r1", "run_dir": "/x/r1",
            "source": {{"path": "/s/Movie 3.38\u202fPM.mov", "sha256": "{h}"}},
            "output_sha256": {{"a.wav": "{h}"}},
            "timeline": {{"no_time_stretch": true, "audio_start_seconds": 0.0}},
            "pcm": {{"sample_rate": 44100, "channels": 1, "sample_count": 6657385}}{extra}}}"#,
            h = "0".repeat(64)
        )
    }

    #[test]
    fn record_carries_unknowns_and_types() {
        let value = parse_object(manifest("").as_bytes()).unwrap();
        let record = RunRecord::from_json(&value).unwrap();
        assert_eq!(record.pcm.sample_count, 6_657_385);
        assert_eq!(record.timeline.format_start_seconds, None);
        assert_eq!(record.dsp_latency, DspLatency::default());
        assert_eq!(record.status, None);
        assert!(record.source.path.to_str().unwrap().contains('\u{202f}'));
        let with = manifest(
            r#", "dsp_latency": {"denoise": {"delay_samples": 1102, "status": "measured_and_compensated"}, "physical_audio_video_sync_verified": false}, "status": "rendered_unreviewed""#,
        );
        let record = RunRecord::from_json(&parse_object(with.as_bytes()).unwrap()).unwrap();
        assert_eq!(record.dsp_latency.denoise_delay_samples, Some(1102));
        assert_eq!(
            record.dsp_latency.physical_audio_video_sync_verified,
            Some(false)
        );
    }

    #[test]
    fn record_reason_codes() {
        let base = manifest("");
        let cases = [
            (
                base.replace("\"schema_version\": 1", "\"schema_version\": 1.0"),
                Reason::SchemaVersionUnsupported,
            ),
            (
                base.replace("\"no_time_stretch\": true", "\"no_time_stretch\": 1"),
                Reason::TimeStretchNotExcluded,
            ),
            (
                base.replace(
                    "\"audio_start_seconds\": 0.0",
                    "\"audio_start_seconds\": null",
                ),
                Reason::TimelineStartInvalid,
            ),
            (
                base.replace("\"channels\": 1", "\"channels\": 70000"),
                Reason::PcmInvalid,
            ),
            (
                base.replace("\"sample_count\": 6657385", "\"sample_count\": 0"),
                Reason::PcmInvalid,
            ),
            (
                base.replace("\"a.wav\"", "\".hidden\""),
                Reason::UnsafeOutputName,
            ),
            (
                base.replace("\"a.wav\"", "\"c:x\""),
                Reason::UnsafeOutputName,
            ),
            (
                base.replace("\"run_dir\": \"/x/r1\"", "\"run_dir\": \"r1\""),
                Reason::RunDirMismatch,
            ),
            (
                base.replace("\"run_id\": \"r1\"", "\"run_id\": \"\""),
                Reason::RunIdMismatch,
            ),
            (
                base.replace("\"path\": \"/s/", "\"path\": \"s/"),
                Reason::ManifestFieldInvalid,
            ),
        ];
        for (text, reason) in cases {
            let value = parse_object(text.as_bytes()).unwrap();
            assert_eq!(
                RunRecord::from_json(&value).unwrap_err().reason,
                reason,
                "{text}"
            );
        }
        let upper = base.replacen(&"0".repeat(64), &"A".repeat(64), 1);
        let value = parse_object(upper.as_bytes()).unwrap();
        assert_eq!(
            RunRecord::from_json(&value).unwrap_err().reason,
            Reason::HashMalformed
        );
    }
}
