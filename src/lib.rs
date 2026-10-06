//! Deterministic, bounded DSP shared by offline processing and future host adapters.
//! No native Audio Unit interface is implemented in this crate.

use std::fmt;

pub mod dsp;
pub mod hash;
pub mod run_record;

/// Maximum interleaved or planar sample count accepted by one gain operation.
pub const MAX_BLOCK_SAMPLES: usize = 65_536;
/// Maximum supported linear gain (approximately 24 dB).
pub const MAX_LINEAR_GAIN: f32 = 16.0;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GainError {
    BlockTooLarge,
    InvalidGain,
    NonFiniteSample,
    Overflow,
}

impl fmt::Display for GainError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::BlockTooLarge => "sample block exceeds the supported bound",
            Self::InvalidGain => "linear gain must be finite and between 0 and 16",
            Self::NonFiniteSample => "sample block contains a non-finite value",
            Self::Overflow => "gain would produce a non-finite sample",
        })
    }
}

impl std::error::Error for GainError {}

/// Apply linear gain without allocating or clipping.
///
/// Invalid input leaves the entire buffer unchanged. This primitive is not a
/// limiter, denoiser, or mastering processor; sample values can exceed unity.
pub fn apply_gain(samples: &mut [f32], gain: f32) -> Result<(), GainError> {
    if samples.len() > MAX_BLOCK_SAMPLES {
        return Err(GainError::BlockTooLarge);
    }
    if !gain.is_finite() || !(0.0..=MAX_LINEAR_GAIN).contains(&gain) {
        return Err(GainError::InvalidGain);
    }
    for &sample in samples.iter() {
        if !sample.is_finite() {
            return Err(GainError::NonFiniteSample);
        }
        if !(sample * gain).is_finite() {
            return Err(GainError::Overflow);
        }
    }
    for sample in samples {
        *sample *= gain;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn gain_scales_without_clipping_and_zero_mutes() {
        let mut samples = [-0.75, 0.0, 0.75];
        apply_gain(&mut samples, 2.0).unwrap();
        assert_eq!(samples, [-1.5, 0.0, 1.5]);
        apply_gain(&mut samples, 0.0).unwrap();
        assert_eq!(samples, [0.0; 3]);
        apply_gain(&mut [], 1.0).unwrap();
    }

    #[test]
    fn invalid_gain_and_overflow_leave_buffer_unchanged() {
        for gain in [f32::NAN, f32::INFINITY, -1.0, MAX_LINEAR_GAIN + 1.0] {
            let mut samples = [0.25, -0.25];
            assert_eq!(apply_gain(&mut samples, gain), Err(GainError::InvalidGain));
            assert_eq!(samples, [0.25, -0.25]);
        }
        let mut samples = [0.25, f32::MAX];
        assert_eq!(apply_gain(&mut samples, 2.0), Err(GainError::Overflow));
        assert_eq!(samples, [0.25, f32::MAX]);
    }

    #[test]
    fn invalid_samples_and_oversized_blocks_fail_atomically() {
        let mut samples = [0.25, f32::INFINITY];
        assert_eq!(
            apply_gain(&mut samples, 2.0),
            Err(GainError::NonFiniteSample)
        );
        assert_eq!(samples[0], 0.25);
        let mut oversized = vec![0.25; MAX_BLOCK_SAMPLES + 1];
        assert_eq!(
            apply_gain(&mut oversized, 2.0),
            Err(GainError::BlockTooLarge)
        );
        assert!(oversized.iter().all(|&sample| sample == 0.25));
    }
}
