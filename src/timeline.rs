//! Edit decision list (EDL) for condensed talks: the segment model, whole-frame
//! quantisation and the map between source and output times.
//!
//! This ports `seg_dur`, `coalesce`, `quantise` and `Timeline` from
//! `talk_condense/edl.py` at talk-condense bf5b9dc. The copy frozen in
//! `condense/tests/frozen/edl_timeline_bf5b9dc.py` is the oracle, and
//! `tests/fixtures/edl-golden-v1.json` holds its answers. Every floating-point
//! step keeps Python's operation order, and Python's `round()` (half to even)
//! is `f64::round_ties_even`, so the results are bit-identical.
//!
//! Clocks: an EDL time is an analysis time, in seconds from a clip's first
//! decoded audio sample. A clip's `shift` (its audio start after its video
//! start, in whole frames) maps that to the source container. An output time
//! is an output frame index divided by `fps`.
//!
//! Validation checks the structure the render relies on. It does not
//! establish sync, loudness or that a cut drops only silence.

use crate::json::{self, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::ops::Range;

/// Timeline mapping name for run manifests whose output is an EDL edit.
pub const EDL_MAPPING: &str = "edl_v1";
/// Largest EDL file read.
pub const MAX_EDL_BYTES: u64 = 16 * 1024 * 1024;
/// Most clips in one EDL.
pub const MAX_CLIPS: usize = 64;
/// Most segments across all clips of one EDL.
pub const MAX_SEGMENTS: usize = 200_000;
/// The render's audio rate; the frame rate must divide it.
pub const AUDIO_RATE: u64 = 48_000;
/// Edge tolerance edl.py uses when it joins segments.
pub const EDGE_EPS: f64 = 1e-6;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum Kind {
    Speech,
    Pause,
    Filler,
    Cut,
    Card,
}

impl Kind {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Speech => "speech",
            Self::Pause => "pause",
            Self::Filler => "filler",
            Self::Cut => "cut",
            Self::Card => "card",
        }
    }

    pub fn parse(text: &str) -> Option<Self> {
        Some(match text {
            "speech" => Self::Speech,
            "pause" => Self::Pause,
            "filler" => Self::Filler,
            "cut" => Self::Cut,
            "card" => Self::Card,
            _ => return None,
        })
    }
}

/// The two kept edges of a cut: `[[a0, a1], [b0, b1]]`; `[a1, b0)` is dropped.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Keep {
    pub head: (f64, f64),
    pub tail: (f64, f64),
}

#[derive(Debug, Clone, PartialEq)]
pub struct Segment {
    pub src: String,
    pub inp: f64,
    pub out: f64,
    pub speed: f64,
    pub kind: Kind,
    /// Output frames; 0 until quantised.
    pub frames: u64,
    pub keep: Option<Keep>,
    pub gain: Option<f64>,
    pub out_dur: Option<f64>,
}

impl Segment {
    /// Output seconds before quantisation (`edl.seg_dur`).
    pub fn duration(&self) -> f64 {
        match (self.kind, &self.keep) {
            (Kind::Cut, Some(keep)) => {
                (0.0 + (keep.head.1 - keep.head.0)) + (keep.tail.1 - keep.tail.0)
            }
            _ => (self.out - self.inp) / self.speed,
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct Clip {
    pub name: String,
    pub duration: f64,
    pub shift: f64,
    pub speed: f64,
    pub welcome: Option<(f64, f64)>,
    pub expected_s: f64,
    pub out_s_by_kind: BTreeMap<String, f64>,
    pub segments: Vec<Segment>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Edl {
    pub fps: u64,
    /// The pacing rules the EDL was built with, kept verbatim.
    pub rules: Value,
    pub clips: Vec<Clip>,
    pub expected_total_s: f64,
}

/// Typed failure codes (stable strings in receipts).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EdlReason {
    InvalidJson,
    TooLarge,
    FieldInvalid,
    FpsInvalid,
    ClipNameDuplicate,
    SegmentSourceMismatch,
    SegmentOutOfRange,
    NotContiguous,
    FramesInvalid,
    CutKeepInvalid,
    CardNotAlone,
    SpeedInvalid,
    TotalMismatch,
}

impl EdlReason {
    pub fn code(self) -> &'static str {
        match self {
            Self::InvalidJson => "invalid_json",
            Self::TooLarge => "too_large",
            Self::FieldInvalid => "field_invalid",
            Self::FpsInvalid => "fps_invalid",
            Self::ClipNameDuplicate => "clip_name_duplicate",
            Self::SegmentSourceMismatch => "segment_source_mismatch",
            Self::SegmentOutOfRange => "segment_out_of_range",
            Self::NotContiguous => "not_contiguous",
            Self::FramesInvalid => "frames_invalid",
            Self::CutKeepInvalid => "cut_keep_invalid",
            Self::CardNotAlone => "card_not_alone",
            Self::SpeedInvalid => "speed_invalid",
            Self::TotalMismatch => "total_mismatch",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EdlFailure {
    pub reason: EdlReason,
    pub detail: String,
}

impl fmt::Display for EdlFailure {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.reason.code(), self.detail)
    }
}

impl std::error::Error for EdlFailure {}

fn fail<T>(reason: EdlReason, detail: impl Into<String>) -> Result<T, EdlFailure> {
    Err(EdlFailure {
        reason,
        detail: detail.into(),
    })
}

/// Python's `round(x)` for a float: nearest integer, ties to even.
pub fn py_round(x: f64) -> i64 {
    x.round_ties_even() as i64
}

/// Python's `max(0.0, x)`.
fn max0(x: f64) -> f64 {
    if x > 0.0 { x } else { 0.0 }
}

/// What validation measured on a valid EDL.
#[derive(Debug, Clone, PartialEq)]
pub struct Report {
    pub fps: u64,
    pub clips: usize,
    pub segments: usize,
    pub total_frames: u64,
    pub total_seconds: f64,
    /// Largest |frames so far - ideal frames so far| within a clip; a measurement, not a gate.
    pub max_drift_frames: f64,
}

// ----------------------------------------------------------------- JSON reading

type Map = BTreeMap<String, Value>;

fn object<'a>(value: &'a Value, what: &str) -> Result<&'a Map, EdlFailure> {
    value.as_object().map_or_else(
        || fail(EdlReason::FieldInvalid, format!("{what} must be an object")),
        Ok,
    )
}

fn keys(map: &Map, required: &[&str], optional: &[&str], what: &str) -> Result<(), EdlFailure> {
    for key in required {
        if !map.contains_key(*key) {
            return fail(EdlReason::FieldInvalid, format!("{what} lacks `{key}`"));
        }
    }
    for key in map.keys() {
        if !required.contains(&key.as_str()) && !optional.contains(&key.as_str()) {
            return fail(
                EdlReason::FieldInvalid,
                format!("{what} has unknown key `{key}`"),
            );
        }
    }
    Ok(())
}

fn number(value: &Value, what: &str) -> Result<f64, EdlFailure> {
    value.as_number().map(json::Number::as_f64).map_or_else(
        || fail(EdlReason::FieldInvalid, format!("{what} must be a number")),
        Ok,
    )
}

fn field(map: &Map, key: &str, what: &str) -> Result<f64, EdlFailure> {
    number(&map[key], &format!("{what}.{key}"))
}

fn unsigned(value: &Value, what: &str) -> Result<u64, EdlFailure> {
    value
        .as_number()
        .and_then(json::Number::as_u64)
        .map_or_else(
            || {
                fail(
                    EdlReason::FieldInvalid,
                    format!("{what} must be a whole number"),
                )
            },
            Ok,
        )
}

fn array<'a>(value: &'a Value, what: &str) -> Result<&'a [Value], EdlFailure> {
    match value {
        Value::Array(items) => Ok(items),
        _ => fail(EdlReason::FieldInvalid, format!("{what} must be an array")),
    }
}

fn pair(value: &Value, what: &str) -> Result<(f64, f64), EdlFailure> {
    match array(value, what)? {
        [a, b] => Ok((number(a, what)?, number(b, what)?)),
        _ => fail(
            EdlReason::FieldInvalid,
            format!("{what} must hold two numbers"),
        ),
    }
}

fn optional(map: &Map, key: &str, what: &str) -> Result<Option<f64>, EdlFailure> {
    map.get(key)
        .map(|value| number(value, &format!("{what}.{key}")))
        .transpose()
}

impl Segment {
    /// One segment; `frames` may be absent before quantisation.
    pub fn from_json(value: &Value, require_frames: bool, what: &str) -> Result<Self, EdlFailure> {
        let map = object(value, what)?;
        let required: &[&str] = if require_frames {
            &["src", "inp", "out", "speed", "kind", "frames"]
        } else {
            &["src", "inp", "out", "speed", "kind"]
        };
        keys(map, required, &["frames", "keep", "gain", "out_dur"], what)?;
        let src = map["src"].as_str().map_or_else(
            || {
                fail(
                    EdlReason::FieldInvalid,
                    format!("{what}.src must be a string"),
                )
            },
            Ok,
        )?;
        let kind = map["kind"].as_str().and_then(Kind::parse).map_or_else(
            || {
                fail(
                    EdlReason::FieldInvalid,
                    format!("{what}.kind is not a segment kind"),
                )
            },
            Ok,
        )?;
        let keep = match map.get("keep") {
            None => None,
            Some(keep) => match array(keep, &format!("{what}.keep"))? {
                [head, tail] => Some(Keep {
                    head: pair(head, &format!("{what}.keep"))?,
                    tail: pair(tail, &format!("{what}.keep"))?,
                }),
                _ => {
                    return fail(
                        EdlReason::CutKeepInvalid,
                        format!("{what}.keep must hold two edges"),
                    );
                }
            },
        };
        if (kind == Kind::Cut) != keep.is_some() {
            return fail(
                EdlReason::CutKeepInvalid,
                format!("{what}: a cut, and only a cut, has `keep`"),
            );
        }
        Ok(Self {
            src: src.to_owned(),
            inp: field(map, "inp", what)?,
            out: field(map, "out", what)?,
            speed: field(map, "speed", what)?,
            kind,
            frames: map
                .get("frames")
                .map(|v| unsigned(v, &format!("{what}.frames")))
                .transpose()?
                .unwrap_or(0),
            keep,
            gain: optional(map, "gain", what)?,
            out_dur: optional(map, "out_dur", what)?,
        })
    }

    pub fn to_json(&self) -> Value {
        let mut map = Map::new();
        map.insert("src".into(), Value::string(&self.src));
        map.insert("inp".into(), Value::f64(self.inp));
        map.insert("out".into(), Value::f64(self.out));
        map.insert("speed".into(), Value::f64(self.speed));
        map.insert("kind".into(), Value::string(self.kind.as_str()));
        map.insert("frames".into(), Value::u64(self.frames));
        if let Some(keep) = self.keep {
            let edge = |(a, b): (f64, f64)| Value::Array(vec![Value::f64(a), Value::f64(b)]);
            map.insert(
                "keep".into(),
                Value::Array(vec![edge(keep.head), edge(keep.tail)]),
            );
        }
        if let Some(gain) = self.gain {
            map.insert("gain".into(), Value::f64(gain));
        }
        if let Some(out_dur) = self.out_dur {
            map.insert("out_dur".into(), Value::f64(out_dur));
        }
        Value::Object(map)
    }
}

/// Segments from a JSON array (for `quantise`).
pub fn segments_from_json(
    value: &Value,
    require_frames: bool,
    what: &str,
) -> Result<Vec<Segment>, EdlFailure> {
    let items = array(value, what)?;
    if items.len() > MAX_SEGMENTS {
        return fail(
            EdlReason::TooLarge,
            format!("{what} holds more than {MAX_SEGMENTS} segments"),
        );
    }
    items
        .iter()
        .enumerate()
        .map(|(i, item)| Segment::from_json(item, require_frames, &format!("{what}[{i}]")))
        .collect()
}

impl Clip {
    fn from_json(value: &Value, what: &str) -> Result<Self, EdlFailure> {
        let map = object(value, what)?;
        keys(
            map,
            &[
                "name",
                "duration",
                "shift",
                "speed",
                "welcome",
                "expected_s",
                "out_s_by_kind",
                "segments",
            ],
            &[],
            what,
        )?;
        let name = map["name"].as_str().map_or_else(
            || {
                fail(
                    EdlReason::FieldInvalid,
                    format!("{what}.name must be a string"),
                )
            },
            Ok,
        )?;
        let welcome = match &map["welcome"] {
            Value::Null => None,
            value => Some(pair(value, &format!("{what}.welcome"))?),
        };
        let mut by_kind = BTreeMap::new();
        for (kind, seconds) in object(&map["out_s_by_kind"], &format!("{what}.out_s_by_kind"))? {
            by_kind.insert(
                kind.clone(),
                number(seconds, &format!("{what}.out_s_by_kind.{kind}"))?,
            );
        }
        Ok(Self {
            name: name.to_owned(),
            duration: field(map, "duration", what)?,
            shift: field(map, "shift", what)?,
            speed: field(map, "speed", what)?,
            welcome,
            expected_s: field(map, "expected_s", what)?,
            out_s_by_kind: by_kind,
            segments: segments_from_json(&map["segments"], true, &format!("{what}.segments"))?,
        })
    }

    fn to_json(&self) -> Value {
        let mut map = Map::new();
        map.insert("name".into(), Value::string(&self.name));
        map.insert("duration".into(), Value::f64(self.duration));
        map.insert("shift".into(), Value::f64(self.shift));
        map.insert("speed".into(), Value::f64(self.speed));
        map.insert(
            "welcome".into(),
            self.welcome.map_or(Value::Null, |(a, b)| {
                Value::Array(vec![Value::f64(a), Value::f64(b)])
            }),
        );
        map.insert("expected_s".into(), Value::f64(self.expected_s));
        map.insert(
            "out_s_by_kind".into(),
            Value::Object(
                self.out_s_by_kind
                    .iter()
                    .map(|(k, v)| (k.clone(), Value::f64(*v)))
                    .collect(),
            ),
        );
        map.insert(
            "segments".into(),
            Value::Array(self.segments.iter().map(Segment::to_json).collect()),
        );
        Value::Object(map)
    }
}

/// The frame rate must be positive and divide the 48 kHz audio rate.
pub fn check_fps(fps: u64) -> Result<(), EdlFailure> {
    if fps == 0 || !AUDIO_RATE.is_multiple_of(fps) {
        return fail(
            EdlReason::FpsInvalid,
            format!("fps {fps} must be positive and divide {AUDIO_RATE}"),
        );
    }
    Ok(())
}

impl Edl {
    /// Parse EDL JSON bytes (an object root). Structure only; see [`Edl::validate`].
    pub fn parse(bytes: &[u8]) -> Result<Self, EdlFailure> {
        if bytes.len() as u64 > MAX_EDL_BYTES {
            return fail(
                EdlReason::TooLarge,
                format!("EDL exceeds {MAX_EDL_BYTES} bytes"),
            );
        }
        let root = json::parse_object(bytes).map_err(|error| EdlFailure {
            reason: EdlReason::InvalidJson,
            detail: error.to_string(),
        })?;
        Self::from_json(&root)
    }

    pub fn from_json(value: &Value) -> Result<Self, EdlFailure> {
        let map = object(value, "edl")?;
        keys(
            map,
            &["fps", "rules", "clips", "expected_total_s"],
            &[],
            "edl",
        )?;
        let fps = unsigned(&map["fps"], "edl.fps")?;
        object(&map["rules"], "edl.rules")?;
        let items = array(&map["clips"], "edl.clips")?;
        if items.is_empty() || items.len() > MAX_CLIPS {
            return fail(
                EdlReason::TooLarge,
                format!("edl.clips must hold 1 to {MAX_CLIPS} clips"),
            );
        }
        let mut clips = Vec::with_capacity(items.len());
        let mut segments = 0;
        for (i, item) in items.iter().enumerate() {
            let clip = Clip::from_json(item, &format!("edl.clips[{i}]"))?;
            segments += clip.segments.len();
            if segments > MAX_SEGMENTS {
                return fail(
                    EdlReason::TooLarge,
                    format!("the EDL holds more than {MAX_SEGMENTS} segments"),
                );
            }
            clips.push(clip);
        }
        Ok(Self {
            fps,
            rules: map["rules"].clone(),
            clips,
            expected_total_s: field(map, "expected_total_s", "edl")?,
        })
    }

    pub fn to_json(&self) -> Value {
        let mut map = Map::new();
        map.insert("fps".into(), Value::u64(self.fps));
        map.insert("rules".into(), self.rules.clone());
        map.insert(
            "clips".into(),
            Value::Array(self.clips.iter().map(Clip::to_json).collect()),
        );
        map.insert("expected_total_s".into(), Value::f64(self.expected_total_s));
        Value::Object(map)
    }

    /// Check every invariant the render and the time map rely on.
    pub fn validate(&self) -> Result<Report, EdlFailure> {
        check_fps(self.fps)?;
        let fps = self.fps as f64;
        let mut names = BTreeSet::new();
        let (mut total_frames, mut segments, mut drift) = (0u64, 0usize, 0.0f64);
        for (c, clip) in self.clips.iter().enumerate() {
            let what = format!("clip {c} `{}`", clip.name);
            if clip.name.is_empty() {
                return fail(
                    EdlReason::FieldInvalid,
                    format!("clip {c} has an empty name"),
                );
            }
            if !names.insert(clip.name.as_str()) {
                return fail(
                    EdlReason::ClipNameDuplicate,
                    format!("{what} repeats a name"),
                );
            }
            if clip.duration < 0.0 || clip.shift < 0.0 || clip.speed <= 0.0 {
                return fail(
                    EdlReason::FieldInvalid,
                    format!("{what}: negative duration or shift, or a speed under 0"),
                );
            }
            if let Some((a, b)) = clip.welcome
                && a > b
            {
                return fail(
                    EdlReason::FieldInvalid,
                    format!("{what}: welcome starts after it ends"),
                );
            }
            if let Some(kind) = clip.out_s_by_kind.keys().find(|k| Kind::parse(k).is_none()) {
                return fail(
                    EdlReason::FieldInvalid,
                    format!("{what}: out_s_by_kind has unknown kind `{kind}`"),
                );
            }
            if clip.segments.is_empty() {
                return fail(EdlReason::FieldInvalid, format!("{what} has no segments"));
            }
            if clip.segments.len() > 1 && clip.segments.iter().any(|s| s.kind == Kind::Card) {
                return fail(
                    EdlReason::CardNotAlone,
                    format!("{what}: a card is the clip's only segment"),
                );
            }
            let (mut ideal, mut done) = (0.0f64, 0.0f64);
            let mut clip_frames = 0u64;
            for (i, s) in clip.segments.iter().enumerate() {
                let at = format!("{what} segment {i}");
                validate_segment(s, &clip.name, fps, &at)?;
                if let Some(next) = clip.segments.get(i + 1)
                    && (s.out - next.inp).abs() > EDGE_EPS
                {
                    return fail(
                        EdlReason::NotContiguous,
                        format!("{at} ends at {} but the next starts at {}", s.out, next.inp),
                    );
                }
                ideal += s.duration() * fps;
                done += s.frames as f64;
                drift = drift.max((done - ideal).abs());
                clip_frames += s.frames;
            }
            let (first, last) = (&clip.segments[0], &clip.segments[clip.segments.len() - 1]);
            if first.inp < -EDGE_EPS || last.out > clip.duration + EDGE_EPS {
                return fail(
                    EdlReason::SegmentOutOfRange,
                    format!("{what}: segments leave [0, {}]", clip.duration),
                );
            }
            let tolerance = 5e-4 + clip.segments.len() as f64 * 1e-6 + 1e-9;
            if (clip.expected_s - clip_frames as f64 / fps).abs() > tolerance {
                return fail(
                    EdlReason::TotalMismatch,
                    format!(
                        "{what}: expected_s {} is not {clip_frames} frames",
                        clip.expected_s
                    ),
                );
            }
            total_frames += clip_frames;
            segments += clip.segments.len();
        }
        let total_seconds = total_frames as f64 / fps;
        let tolerance = 5e-4 * (self.clips.len() + 1) as f64 + segments as f64 * 1e-6 + 1e-9;
        if (self.expected_total_s - total_seconds).abs() > tolerance {
            return fail(
                EdlReason::TotalMismatch,
                format!(
                    "expected_total_s {} is not {total_frames} frames",
                    self.expected_total_s
                ),
            );
        }
        Ok(Report {
            fps: self.fps,
            clips: self.clips.len(),
            segments,
            total_frames,
            total_seconds,
            max_drift_frames: drift,
        })
    }
}

fn validate_segment(s: &Segment, clip: &str, fps: f64, at: &str) -> Result<(), EdlFailure> {
    if s.src != clip {
        return fail(
            EdlReason::SegmentSourceMismatch,
            format!("{at}: src `{}` is not its clip", s.src),
        );
    }
    if s.out - s.inp < EDGE_EPS {
        return fail(
            EdlReason::FieldInvalid,
            format!("{at}: out must follow inp"),
        );
    }
    if s.speed <= 0.0 {
        return fail(
            EdlReason::SpeedInvalid,
            format!("{at}: speed must be positive"),
        );
    }
    if s.frames == 0 {
        return fail(EdlReason::FramesInvalid, format!("{at}: no output frame"));
    }
    if s.gain.is_some_and(|g| g < 0.0) {
        return fail(
            EdlReason::FieldInvalid,
            format!("{at}: gain must not be negative"),
        );
    }
    if let Some(out_dur) = s.out_dur
        && (out_dur - s.frames as f64 / fps).abs() > EDGE_EPS
    {
        return fail(
            EdlReason::FramesInvalid,
            format!("{at}: out_dur {out_dur} is not {} frames", s.frames),
        );
    }
    match (s.kind, s.keep) {
        (
            Kind::Cut,
            Some(Keep {
                head: (a0, a1),
                tail: (b0, b1),
            }),
        ) => {
            if s.speed != 1.0 {
                return fail(EdlReason::SpeedInvalid, format!("{at}: a cut plays at 1x"));
            }
            if a0 != s.inp || b1 != s.out || !(a0 < a1 && a1 <= b0 && b0 < b1) {
                return fail(
                    EdlReason::CutKeepInvalid,
                    format!("{at}: keep must be [[inp, a], [b, out]] with inp < a <= b < out"),
                );
            }
            if s.frames as i64 != py_round(s.duration() * fps) {
                return fail(
                    EdlReason::FramesInvalid,
                    format!("{at}: a cut keeps exactly its kept frames"),
                );
            }
        }
        (Kind::Cut, None) => {
            return fail(EdlReason::CutKeepInvalid, format!("{at}: a cut needs keep"));
        }
        (_, Some(_)) => {
            return fail(
                EdlReason::CutKeepInvalid,
                format!("{at}: only a cut has keep"),
            );
        }
        (Kind::Card, None) => {}
        (_, None) => {
            if s.frames as i64 > py_round((s.out - s.inp) * fps) {
                return fail(
                    EdlReason::FramesInvalid,
                    format!("{at}: more output frames than source frames"),
                );
            }
        }
    }
    Ok(())
}

// ----------------------------------------------------------------- quantise

fn free(segment: Option<&(Segment, bool)>) -> bool {
    segment.is_some_and(|(s, _)| s.kind != Kind::Cut)
}

/// `edl.coalesce`: drop empty segments and join neighbours of one kind and speed.
fn coalesce_flagged(segs: Vec<(Segment, bool)>) -> Vec<(Segment, bool)> {
    let mut out: Vec<(Segment, bool)> = Vec::with_capacity(segs.len());
    for (s, min1) in segs {
        if s.out - s.inp < 1e-6 {
            continue;
        }
        if let Some((last, _)) = out.last_mut()
            && s.kind != Kind::Cut
            && last.speed == s.speed
            && last.kind == s.kind
            && (last.out - s.inp).abs() < 1e-6
        {
            last.out = s.out;
            continue;
        }
        out.push((s, min1));
    }
    out
}

/// `edl.coalesce` on plain segments.
pub fn coalesce(segs: Vec<Segment>) -> Vec<Segment> {
    coalesce_flagged(segs.into_iter().map(|s| (s, false)).collect())
        .into_iter()
        .map(|(s, _)| s)
        .collect()
}

/// `edl.quantise`: give every segment a whole number of output frames.
///
/// Segment k ends on frame round(ideal running total * fps), so the rounding
/// error stays under half a frame. A segment that gets no frame joins a free
/// neighbour (the one before, or the one after when a cut sits before it);
/// between two cuts it keeps one frame. A cut keeps its own frames.
pub fn quantise(segs: Vec<Segment>, fps: u64) -> Vec<Segment> {
    let fps = fps as f64;
    let mut segs: Vec<(Segment, bool)> = segs.into_iter().map(|s| (s, false)).collect();
    loop {
        let (mut total, mut done) = (0.0f64, 0i64);
        for (s, min1) in &mut segs {
            total += s.duration() * fps;
            let own = if s.kind == Kind::Cut {
                py_round(s.duration() * fps)
            } else {
                i64::from(*min1)
            };
            let frames = if s.kind == Kind::Cut {
                own
            } else {
                (py_round(total - 1e-9) - done).max(own)
            };
            s.frames = frames.max(0) as u64;
            done += frames;
        }
        let Some(zero) = segs.iter().position(|(s, _)| s.frames == 0) else {
            return segs.into_iter().map(|(s, _)| s).collect();
        };
        let (z_inp, z_out, z_speed) = (segs[zero].0.inp, segs[zero].0.out, segs[zero].0.speed);
        let prev = zero.checked_sub(1).map(|i| &segs[i]);
        let next = segs.get(zero + 1);
        let same =
            |o: Option<&(Segment, bool)>| free(o) && o.is_some_and(|(s, _)| s.speed == z_speed);
        if free(prev)
            && prev.is_some_and(|(p, _)| (p.out - z_inp).abs() < 1e-6)
            && (same(prev) || !same(next))
        {
            segs[zero - 1].0.out = z_out;
        } else if free(next) && next.is_some_and(|(n, _)| (n.inp - z_out).abs() < 1e-6) {
            segs[zero + 1].0.inp = z_inp;
        } else {
            segs[zero].1 = true;
            continue;
        }
        segs.remove(zero);
        segs = coalesce_flagged(segs);
    }
}

// ----------------------------------------------------------------- time map

/// Where one segment lands on the output clock.
#[derive(Debug, Clone, PartialEq)]
pub struct Row {
    pub clip: usize,
    pub segment: usize,
    pub start_frame: u64,
    pub end_frame: u64,
    pub start_s: f64,
    pub end_s: f64,
}

/// `edl.Timeline`: the output position of every segment and the map between
/// source and output times. Build it from a validated EDL.
#[derive(Debug, Clone)]
pub struct Timeline<'a> {
    edl: &'a Edl,
    rows: Vec<Row>,
    starts: Vec<f64>,
    by_clip: BTreeMap<&'a str, (Vec<f64>, Range<usize>)>,
    total_frames: u64,
}

impl<'a> Timeline<'a> {
    pub fn new(edl: &'a Edl) -> Self {
        let fps = edl.fps as f64;
        let (mut rows, mut by_clip, mut n) = (Vec::new(), BTreeMap::new(), 0u64);
        for (c, clip) in edl.clips.iter().enumerate() {
            let first = rows.len();
            for (i, s) in clip.segments.iter().enumerate() {
                rows.push(Row {
                    clip: c,
                    segment: i,
                    start_frame: n,
                    end_frame: n + s.frames,
                    start_s: n as f64 / fps,
                    end_s: (n + s.frames) as f64 / fps,
                });
                n += s.frames;
            }
            let inps = clip.segments.iter().map(|s| s.inp).collect();
            by_clip.insert(clip.name.as_str(), (inps, first..rows.len()));
        }
        let starts = rows.iter().map(|r| r.start_s).collect();
        Self {
            edl,
            rows,
            starts,
            by_clip,
            total_frames: n,
        }
    }

    pub fn rows(&self) -> &[Row] {
        &self.rows
    }

    pub fn segment(&self, row: usize) -> &'a Segment {
        let r = &self.rows[row];
        &self.edl.clips[r.clip].segments[r.segment]
    }

    pub fn has_clip(&self, clip: &str) -> bool {
        self.by_clip.contains_key(clip)
    }

    pub fn total_frames(&self) -> u64 {
        self.total_frames
    }

    /// Output seconds of the whole edit.
    pub fn total_seconds(&self) -> f64 {
        self.total_frames as f64 / self.edl.fps as f64
    }

    /// The row whose segment holds source time `t` of `clip`.
    pub fn row(&self, clip: &str, t: f64) -> Option<usize> {
        let (inps, range) = self.by_clip.get(clip)?;
        let i = inps.partition_point(|x| *x <= t).checked_sub(1)?;
        let row = range.start + i;
        (t < self.segment(row).out).then_some(row)
    }

    /// Output time of source time `t`; `None` inside a dropped span unless
    /// `snap` moves it to the join.
    pub fn to_out(&self, clip: &str, t: f64, snap: bool) -> Option<f64> {
        let row = self.row(clip, t)?;
        let (t0, t1, s) = (
            self.rows[row].start_s,
            self.rows[row].end_s,
            self.segment(row),
        );
        let Some(Keep {
            head: (a0, a1),
            tail: (b0, _),
        }) = s.keep.filter(|_| s.kind == Kind::Cut)
        else {
            // the segment's real speed is its source length over its whole frames
            return Some(t0 + (t - s.inp) / (s.out - s.inp) * (t1 - t0));
        };
        if a1 <= t && t < b0 && !snap {
            return None;
        }
        Some(
            t0 + if t < a1 {
                t - a0
            } else {
                (a1 - a0) + max0(t - b0)
            },
        )
    }

    /// Source time under output time `t` and its row; `None` past the end.
    pub fn to_src(&self, t: f64) -> Option<(f64, usize)> {
        let row = self.starts.partition_point(|x| *x <= t).checked_sub(1)?;
        let (t0, t1, s) = (
            self.rows[row].start_s,
            self.rows[row].end_s,
            self.segment(row),
        );
        if t >= t1 {
            return None;
        }
        let Some(Keep {
            head: (a0, a1),
            tail: (b0, _),
        }) = s.keep.filter(|_| s.kind == Kind::Cut)
        else {
            return Some((s.inp + (t - t0) / (t1 - t0) * (s.out - s.inp), row));
        };
        Some((
            if t - t0 < a1 - a0 {
                a0 + t - t0
            } else {
                b0 + t - t0 - (a1 - a0)
            },
            row,
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const GOLDEN: &str = include_str!("../tests/fixtures/edl-golden-v1.json");

    fn golden() -> Value {
        json::parse_object(GOLDEN.as_bytes()).expect("golden parses")
    }

    fn items(value: &Value, key: &str) -> Vec<Value> {
        match value.get(key) {
            Some(Value::Array(items)) => items.clone(),
            _ => panic!("missing array {key}"),
        }
    }

    fn num(value: &Value, key: &str) -> f64 {
        value
            .get(key)
            .and_then(Value::as_number)
            .expect(key)
            .as_f64()
    }

    fn text<'v>(value: &'v Value, key: &str) -> &'v str {
        value.get(key).and_then(Value::as_str).expect(key)
    }

    fn same(a: f64, b: f64, what: &str) {
        assert_eq!(a.to_bits(), b.to_bits(), "{what}: {a:?} != {b:?}");
    }

    #[test]
    fn quantise_matches_the_oracle_bit_for_bit() {
        let cases = items(&golden(), "quantise_cases");
        assert!(cases.len() >= 12);
        let mut checked = 0;
        for (c, case) in cases.iter().enumerate() {
            let fps = case
                .get("fps")
                .and_then(Value::as_number)
                .and_then(json::Number::as_u64)
                .unwrap();
            let input = segments_from_json(case.get("segments").unwrap(), false, "in").unwrap();
            let expect = segments_from_json(case.get("expect").unwrap(), true, "expect").unwrap();
            let got = quantise(input, fps);
            assert_eq!(got.len(), expect.len(), "case {c}");
            for (i, (g, e)) in got.iter().zip(&expect).enumerate() {
                let at = format!("case {c} segment {i}");
                assert_eq!(
                    (g.kind, g.frames, &g.src),
                    (e.kind, e.frames, &e.src),
                    "{at}"
                );
                same(g.inp, e.inp, &at);
                same(g.out, e.out, &at);
                same(g.speed, e.speed, &at);
                checked += 1;
            }
        }
        assert!(checked >= 50, "{checked}");
    }

    #[test]
    fn timeline_matches_the_oracle_bit_for_bit() {
        let mut checked = 0;
        for (c, case) in items(&golden(), "timeline_cases").iter().enumerate() {
            let edl = Edl::from_json(case.get("edl").unwrap()).unwrap();
            let report = edl.validate().unwrap_or_else(|e| panic!("case {c}: {e}"));
            assert!(report.max_drift_frames <= 0.5 + 1e-6, "case {c}");
            let tl = Timeline::new(&edl);
            same(tl.total_seconds(), num(case, "total_s"), "total");
            assert_eq!(tl.rows().len() as f64, num(case, "rows"));
            for (q, query) in items(case, "queries").iter().enumerate() {
                let at = format!("case {c} query {q}");
                let expect = query.get("expect").unwrap();
                match text(query, "op") {
                    "to_out" => {
                        let snap = matches!(query.get("snap"), Some(Value::Bool(true)));
                        let got = tl.to_out(text(query, "clip"), num(query, "source_s"), snap);
                        match (got, expect) {
                            (None, Value::Null) => {}
                            (Some(g), Value::Number(e)) => same(g, e.as_f64(), &at),
                            other => panic!("{at}: {other:?}"),
                        }
                    }
                    "row" => {
                        let got = tl.row(text(query, "clip"), num(query, "source_s"));
                        match (got, expect) {
                            (None, Value::Null) => {}
                            (Some(r), Value::Object(_)) => {
                                assert_eq!(r as f64, num(expect, "row"), "{at}");
                                same(tl.rows()[r].start_s, num(expect, "start_s"), &at);
                                same(tl.rows()[r].end_s, num(expect, "end_s"), &at);
                            }
                            other => panic!("{at}: {other:?}"),
                        }
                    }
                    "to_src" => {
                        let got = tl.to_src(num(query, "output_s"));
                        match (got, expect) {
                            (None, Value::Null) => {}
                            (Some((t, r)), Value::Object(_)) => {
                                same(t, num(expect, "source_s"), &at);
                                assert_eq!(r as f64, num(expect, "row"), "{at}");
                            }
                            other => panic!("{at}: {other:?}"),
                        }
                    }
                    op => panic!("{at}: unknown op {op}"),
                }
                checked += 1;
            }
        }
        assert!(checked >= 2000, "{checked}");
    }

    #[test]
    fn the_map_is_monotonic_round_trips_and_snaps_to_the_join() {
        for case in items(&golden(), "timeline_cases") {
            let edl = Edl::from_json(case.get("edl").unwrap()).unwrap();
            let tl = Timeline::new(&edl);
            for clip in &edl.clips {
                let mut last = f64::NEG_INFINITY;
                let steps = (clip.duration * 200.0) as usize;
                for k in 0..steps {
                    let t = k as f64 / 200.0;
                    let Some(out) = tl.to_out(&clip.name, t, false) else {
                        let row = tl.row(&clip.name, t);
                        if let Some(row) = row {
                            let s = tl.segment(row);
                            let keep = s.keep.expect("only a cut drops time");
                            assert!(keep.head.1 <= t && t < keep.tail.0);
                            let snapped = tl.to_out(&clip.name, t, true).unwrap();
                            let join = tl.to_out(&clip.name, keep.tail.0, false).unwrap();
                            assert!((snapped - join).abs() < 1e-9);
                        }
                        continue;
                    };
                    assert!(out >= last, "{} at {t}: {out} < {last}", clip.name);
                    last = out;
                    let (back, row) = tl.to_src(out).expect("a kept time maps back");
                    // a cut's join is both its head end and its tail start
                    let join = tl.segment(row).keep.is_some_and(|k| {
                        (t - k.tail.0).abs() < 1e-6 && (back - k.head.1).abs() < 1e-6
                    });
                    assert!(
                        join || (back - t).abs() < 1e-6,
                        "{} at {t}: back {back}",
                        clip.name
                    );
                }
            }
            assert!(tl.to_src(tl.total_seconds()).is_none());
            assert!((tl.total_seconds() - edl.expected_total_s).abs() <= 1e-3);
        }
    }

    #[test]
    fn json_round_trips_through_the_model() {
        for case in items(&golden(), "timeline_cases") {
            let edl = Edl::from_json(case.get("edl").unwrap()).unwrap();
            let again =
                Edl::from_json(&json::parse_object(edl.to_json().to_pretty().as_bytes()).unwrap())
                    .unwrap();
            assert_eq!(edl, again);
        }
    }

    fn valid() -> Value {
        json::parse_object(
            br#"{"fps": 30, "rules": {}, "expected_total_s": 1.3, "clips": [{
                "name": "a", "duration": 4.0, "shift": 0.0, "speed": 2.0, "welcome": null,
                "expected_s": 1.3, "out_s_by_kind": {"speech": 1.0, "cut": 0.3},
                "segments": [
                  {"src": "a", "inp": 0.0, "out": 2.0, "speed": 2.0, "kind": "speech", "frames": 30, "out_dur": 1.0, "gain": 1.0},
                  {"src": "a", "inp": 2.0, "out": 4.0, "speed": 1.0, "kind": "cut", "frames": 9, "out_dur": 0.3, "gain": 1.0,
                   "keep": [[2.0, 2.1666666666666665], [3.8666666666666667, 4.0]]}]}]}"#,
        )
        .unwrap()
    }

    fn edit(path: &[&str], value: Value) -> Value {
        fn walk(node: &mut Value, path: &[&str], value: Value) {
            let (head, rest) = path.split_first().unwrap();
            let next = match node {
                Value::Object(map) => map.get_mut(*head).unwrap(),
                Value::Array(items) => &mut items[head.parse::<usize>().unwrap()],
                _ => panic!("not a container"),
            };
            if rest.is_empty() {
                *next = value;
            } else {
                walk(next, rest, value);
            }
        }
        let mut root = valid();
        walk(&mut root, path, value);
        root
    }

    fn reason(value: &Value) -> EdlReason {
        match Edl::from_json(value).and_then(|edl| edl.validate()) {
            Ok(report) => panic!("accepted: {report:?}"),
            Err(failure) => failure.reason,
        }
    }

    #[test]
    fn a_small_valid_edl_validates() {
        let report = Edl::from_json(&valid()).unwrap().validate().unwrap();
        assert_eq!(
            (report.total_frames, report.segments, report.clips),
            (39, 2, 1)
        );
    }

    #[test]
    fn each_broken_invariant_has_its_reason() {
        use EdlReason::*;
        let seg = |i: &str, key: &str| -> Vec<String> {
            ["clips", "0", "segments", i, key]
                .iter()
                .map(|s| (*s).to_owned())
                .collect()
        };
        let at = |path: Vec<String>, value: Value| {
            let refs: Vec<&str> = path.iter().map(String::as_str).collect();
            edit(&refs, value)
        };
        assert_eq!(reason(&edit(&["fps"], Value::u64(7))), FpsInvalid);
        assert_eq!(reason(&edit(&["fps"], Value::u64(0))), FpsInvalid);
        assert_eq!(reason(&edit(&["fps"], Value::f64(29.97))), FieldInvalid);
        assert_eq!(reason(&edit(&["rules"], Value::Null)), FieldInvalid);
        assert_eq!(
            reason(&at(seg("0", "frames"), Value::u64(0))),
            FramesInvalid
        );
        assert_eq!(
            reason(&at(seg("0", "frames"), Value::u64(61))),
            FramesInvalid
        );
        assert_eq!(
            reason(&at(seg("0", "out_dur"), Value::f64(0.9))),
            FramesInvalid
        );
        assert_eq!(
            reason(&at(seg("1", "frames"), Value::u64(10))),
            FramesInvalid
        );
        assert_eq!(
            reason(&at(seg("0", "src"), Value::string("b"))),
            SegmentSourceMismatch
        );
        assert_eq!(reason(&at(seg("0", "out"), Value::f64(1.9))), NotContiguous);
        assert_eq!(
            reason(&at(seg("0", "speed"), Value::f64(0.0))),
            SpeedInvalid
        );
        assert_eq!(
            reason(&at(seg("1", "speed"), Value::f64(2.0))),
            SpeedInvalid
        );
        assert_eq!(
            reason(&at(seg("0", "kind"), Value::string("card"))),
            CardNotAlone
        );
        assert_eq!(
            reason(&at(seg("0", "kind"), Value::string("welcome"))),
            FieldInvalid
        );
        assert_eq!(
            reason(&at(seg("1", "kind"), Value::string("pause"))),
            CutKeepInvalid
        );
        let swapped = json::parse_object(br#"{"k": [[2.0, 3.9], [2.2, 4.0]]}"#).unwrap();
        assert_eq!(
            reason(&at(seg("1", "keep"), swapped.get("k").unwrap().clone())),
            CutKeepInvalid
        );
        assert_eq!(
            reason(&edit(&["clips", "0", "duration"], Value::f64(3.0))),
            SegmentOutOfRange
        );
        assert_eq!(
            reason(&edit(&["expected_total_s"], Value::f64(1.31))),
            TotalMismatch
        );
        assert_eq!(
            reason(&edit(&["clips", "0", "expected_s"], Value::f64(1.4))),
            TotalMismatch
        );
        let mut twice = valid();
        if let Value::Object(map) = &mut twice
            && let Some(Value::Array(clips)) = map.get_mut("clips")
        {
            let copy = clips[0].clone();
            clips.push(copy);
        }
        assert_eq!(reason(&twice), ClipNameDuplicate);
        let mut extra = valid();
        if let Value::Object(map) = &mut extra {
            map.insert("note".into(), Value::Null);
        }
        assert_eq!(reason(&extra), FieldInvalid);
        assert_eq!(Edl::parse(b"[1]").unwrap_err().reason, InvalidJson);
        assert_eq!(
            Edl::parse(b"{\"fps\": NaN}").unwrap_err().reason,
            InvalidJson
        );
    }

    #[test]
    fn python_rounding_is_half_to_even() {
        assert_eq!(
            [0.5, 1.5, 2.5, -0.5, 2.4999999].map(py_round),
            [0, 2, 2, 0, 2]
        );
        assert_eq!(max0(-0.0).to_bits(), 0.0f64.to_bits());
    }
}
