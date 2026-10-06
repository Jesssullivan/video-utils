//! Allocation-free, bounded, atomic-failure filters and meters.
//!
//! These primitives are not adopted by the rendering path; FFmpeg `equalizer`
//! remains the production EQ. No high-pass or notch filter is provided or
//! defaulted, so ~32 Hz content of the nine-string low C is never removed here.
//!
//! Every `process` call follows the [`crate::apply_gain`] convention: blocks
//! larger than [`MAX_BLOCK_SAMPLES`] are refused, and on any error the sample
//! buffer and the filter/meter state are left bitwise unchanged. Validation is
//! a first pass over a stack copy of the state; results are then committed.

use crate::MAX_BLOCK_SAMPLES;
use std::f64::consts::PI;
use std::fmt;

/// Supported sample-rate bounds in Hz (inclusive).
pub const MIN_SAMPLE_RATE: f64 = 8_000.0;
pub const MAX_SAMPLE_RATE: f64 = 384_000.0;
/// Highest corner/centre frequency as a fraction of the sample rate (exclusive).
pub const MAX_FREQUENCY_FRACTION: f64 = 0.49;
/// Q bounds (inclusive).
pub const MIN_Q: f64 = 0.1;
pub const MAX_Q: f64 = 40.0;
/// Maximum absolute gain in dB (inclusive).
pub const MAX_ABS_GAIN_DB: f64 = 24.0;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DspError {
    BlockTooLarge,
    InvalidParameter,
    NonFiniteSample,
    Overflow,
}

impl fmt::Display for DspError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::BlockTooLarge => "sample block exceeds the supported bound",
            Self::InvalidParameter => "filter parameter is non-finite or out of range",
            Self::NonFiniteSample => "sample block contains a non-finite value",
            Self::Overflow => "filter would produce a non-finite sample",
        })
    }
}

impl std::error::Error for DspError {}

/// Normalized biquad coefficients (a0 == 1) for
/// `y[n] = b0 x[n] + b1 x[n-1] + b2 x[n-2] - a1 y[n-1] - a2 y[n-2]`.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct BiquadCoefficients {
    pub b0: f64,
    pub b1: f64,
    pub b2: f64,
    pub a1: f64,
    pub a2: f64,
}

fn validate(sample_rate: f64, frequency: f64, q: f64, gain_db: f64) -> Result<(), DspError> {
    let finite = [sample_rate, frequency, q, gain_db]
        .iter()
        .all(|value| value.is_finite());
    if !finite
        || !(MIN_SAMPLE_RATE..=MAX_SAMPLE_RATE).contains(&sample_rate)
        || frequency <= 0.0
        || frequency >= MAX_FREQUENCY_FRACTION * sample_rate
        || !(MIN_Q..=MAX_Q).contains(&q)
        || gain_db.abs() > MAX_ABS_GAIN_DB
    {
        return Err(DspError::InvalidParameter);
    }
    Ok(())
}

impl BiquadCoefficients {
    /// RBJ peaking EQ, matching FFmpeg `equalizer=f=F:t=q:w=Q:g=G` formulas:
    /// `A = 10^(G/40)`, `w0 = 2π f0/fs`, `alpha = sin(w0)/(2Q)`,
    /// `b = [1+αA, −2cos w0, 1−αA]`, `a = [1+α/A, −2cos w0, 1−α/A]`, normalized by a0.
    pub fn peaking(
        sample_rate: f64,
        frequency: f64,
        q: f64,
        gain_db: f64,
    ) -> Result<Self, DspError> {
        validate(sample_rate, frequency, q, gain_db)?;
        let a = 10f64.powf(gain_db / 40.0);
        let w0 = 2.0 * PI * frequency / sample_rate;
        let alpha = w0.sin() / (2.0 * q);
        let cos_w0 = w0.cos();
        let a0 = 1.0 + alpha / a;
        Ok(Self {
            b0: (1.0 + alpha * a) / a0,
            b1: (-2.0 * cos_w0) / a0,
            b2: (1.0 - alpha * a) / a0,
            a1: (-2.0 * cos_w0) / a0,
            a2: (1.0 - alpha / a) / a0,
        })
    }

    /// RBJ cookbook low shelf with Q parameterization (`alpha = sin(w0)/(2Q)`).
    pub fn low_shelf(
        sample_rate: f64,
        frequency: f64,
        q: f64,
        gain_db: f64,
    ) -> Result<Self, DspError> {
        validate(sample_rate, frequency, q, gain_db)?;
        let a = 10f64.powf(gain_db / 40.0);
        let w0 = 2.0 * PI * frequency / sample_rate;
        let alpha = w0.sin() / (2.0 * q);
        let cos_w0 = w0.cos();
        let root_a_alpha = 2.0 * a.sqrt() * alpha;
        let a0 = (a + 1.0) + (a - 1.0) * cos_w0 + root_a_alpha;
        Ok(Self {
            b0: a * ((a + 1.0) - (a - 1.0) * cos_w0 + root_a_alpha) / a0,
            b1: 2.0 * a * ((a - 1.0) - (a + 1.0) * cos_w0) / a0,
            b2: a * ((a + 1.0) - (a - 1.0) * cos_w0 - root_a_alpha) / a0,
            a1: -2.0 * ((a - 1.0) + (a + 1.0) * cos_w0) / a0,
            a2: ((a + 1.0) + (a - 1.0) * cos_w0 - root_a_alpha) / a0,
        })
    }
}

/// Direct Form I delay line (f64).
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct BiquadState {
    pub x1: f64,
    pub x2: f64,
    pub y1: f64,
    pub y2: f64,
}

impl BiquadState {
    /// Bit patterns, for exact unchanged-state comparisons.
    pub fn to_bits(&self) -> [u64; 4] {
        [
            self.x1.to_bits(),
            self.x2.to_bits(),
            self.y1.to_bits(),
            self.y2.to_bits(),
        ]
    }
}

impl BiquadCoefficients {
    pub fn to_bits(&self) -> [u64; 5] {
        [
            self.b0.to_bits(),
            self.b1.to_bits(),
            self.b2.to_bits(),
            self.a1.to_bits(),
            self.a2.to_bits(),
        ]
    }
}

#[inline(always)]
fn step(c: &BiquadCoefficients, s: &mut BiquadState, x: f64) -> f64 {
    let y = c.b0 * x + c.b1 * s.x1 + c.b2 * s.x2 - c.a1 * s.y1 - c.a2 * s.y2;
    s.x2 = s.x1;
    s.x1 = x;
    s.y2 = s.y1;
    s.y1 = y;
    y
}

/// Single-channel Direct Form I biquad: f64 coefficients/state, f32 samples.
/// Multichannel audio uses one instance per planar channel.
#[derive(Debug, Clone)]
pub struct Biquad {
    coefficients: BiquadCoefficients,
    state: BiquadState,
}

impl Biquad {
    pub fn new(coefficients: BiquadCoefficients) -> Self {
        Self {
            coefficients,
            state: BiquadState::default(),
        }
    }

    pub fn peaking(
        sample_rate: f64,
        frequency: f64,
        q: f64,
        gain_db: f64,
    ) -> Result<Self, DspError> {
        BiquadCoefficients::peaking(sample_rate, frequency, q, gain_db).map(Self::new)
    }

    pub fn low_shelf(
        sample_rate: f64,
        frequency: f64,
        q: f64,
        gain_db: f64,
    ) -> Result<Self, DspError> {
        BiquadCoefficients::low_shelf(sample_rate, frequency, q, gain_db).map(Self::new)
    }

    /// Retune to a peaking band, keeping the delay line. Invalid parameters
    /// leave coefficients and state unchanged.
    pub fn set_peaking(
        &mut self,
        sample_rate: f64,
        frequency: f64,
        q: f64,
        gain_db: f64,
    ) -> Result<(), DspError> {
        self.coefficients = BiquadCoefficients::peaking(sample_rate, frequency, q, gain_db)?;
        Ok(())
    }

    /// Retune to a low shelf, keeping the delay line. Invalid parameters leave
    /// coefficients and state unchanged.
    pub fn set_low_shelf(
        &mut self,
        sample_rate: f64,
        frequency: f64,
        q: f64,
        gain_db: f64,
    ) -> Result<(), DspError> {
        self.coefficients = BiquadCoefficients::low_shelf(sample_rate, frequency, q, gain_db)?;
        Ok(())
    }

    pub fn coefficients(&self) -> BiquadCoefficients {
        self.coefficients
    }

    pub fn state(&self) -> BiquadState {
        self.state
    }

    pub fn reset(&mut self) {
        self.state = BiquadState::default();
    }

    /// Filter in place without allocating. On error nothing is modified.
    pub fn process(&mut self, samples: &mut [f32]) -> Result<(), DspError> {
        if samples.len() > MAX_BLOCK_SAMPLES {
            return Err(DspError::BlockTooLarge);
        }
        let coefficients = self.coefficients;
        let mut trial = self.state;
        for &sample in samples.iter() {
            if !sample.is_finite() {
                return Err(DspError::NonFiniteSample);
            }
            let y = step(&coefficients, &mut trial, f64::from(sample));
            if !y.is_finite() || !(y as f32).is_finite() {
                return Err(DspError::Overflow);
            }
        }
        let mut state = self.state;
        for sample in samples.iter_mut() {
            *sample = step(&coefficients, &mut state, f64::from(*sample)) as f32;
        }
        self.state = state;
        Ok(())
    }
}

/// Running peak and RMS meter over finite f32 samples.
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct PeakRms {
    peak: f32,
    sum_squares: f64,
    count: u64,
}

impl PeakRms {
    pub const fn new() -> Self {
        Self {
            peak: 0.0,
            sum_squares: 0.0,
            count: 0,
        }
    }

    /// Accumulate one block. Non-finite samples or oversized blocks leave the
    /// meter unchanged.
    pub fn process(&mut self, samples: &[f32]) -> Result<(), DspError> {
        if samples.len() > MAX_BLOCK_SAMPLES {
            return Err(DspError::BlockTooLarge);
        }
        let mut peak = self.peak;
        let mut sum = self.sum_squares;
        for &sample in samples {
            if !sample.is_finite() {
                return Err(DspError::NonFiniteSample);
            }
            let value = f64::from(sample);
            peak = peak.max(sample.abs());
            sum += value * value;
        }
        let count = self
            .count
            .checked_add(samples.len() as u64)
            .ok_or(DspError::Overflow)?;
        if !sum.is_finite() {
            return Err(DspError::Overflow);
        }
        *self = Self {
            peak,
            sum_squares: sum,
            count,
        };
        Ok(())
    }

    pub fn count(&self) -> u64 {
        self.count
    }

    /// Peak absolute sample, or `None` (unknown) when no samples were metered.
    pub fn peak(&self) -> Option<f32> {
        (self.count > 0).then_some(self.peak)
    }

    /// Root-mean-square value, or `None` (unknown) when empty.
    pub fn rms(&self) -> Option<f64> {
        (self.count > 0).then(|| (self.sum_squares / self.count as f64).sqrt())
    }

    /// Peak in dBFS (1.0 = 0 dBFS). Digital silence is `Some(-inf)`; empty is `None`.
    pub fn peak_dbfs(&self) -> Option<f64> {
        self.peak().map(|peak| 20.0 * f64::from(peak).log10())
    }

    /// RMS in dBFS (unity-amplitude reference, no sine offset).
    pub fn rms_dbfs(&self) -> Option<f64> {
        self.rms().map(|rms| 20.0 * rms.log10())
    }

    pub fn reset(&mut self) {
        *self = Self::new();
    }

    /// Bit patterns of (peak, sum of squares, count) for exact comparisons.
    pub fn to_bits(&self) -> (u32, u64, u64) {
        (self.peak.to_bits(), self.sum_squares.to_bits(), self.count)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unity_gain_peaking_is_identity_and_reset_zeroes() {
        let mut filter = Biquad::peaking(48_000.0, 300.0, 0.8, 0.0).unwrap();
        // b == a exactly at 0 dB, so the transfer function is 1; f64 recursion
        // leaves only rounding-level residue (not bitwise identity).
        let input = [0.5f32, -0.25, 0.125, 0.0];
        let mut samples = input;
        filter.process(&mut samples).unwrap();
        for (got, want) in samples.iter().zip(input) {
            assert!((got - want).abs() <= 1e-12, "{got} vs {want}");
        }
        assert_ne!(filter.state(), BiquadState::default());
        filter.reset();
        assert_eq!(filter.state(), BiquadState::default());
    }

    #[test]
    fn meter_reports_unknown_when_empty() {
        let mut meter = PeakRms::new();
        assert_eq!(meter.peak(), None);
        assert_eq!(meter.rms_dbfs(), None);
        meter.process(&[0.5, -1.0]).unwrap();
        assert_eq!(meter.peak(), Some(1.0));
        assert!((meter.rms().unwrap() - (0.625f64).sqrt()).abs() < 1e-15);
        meter.reset();
        assert_eq!(meter.count(), 0);
    }
}
