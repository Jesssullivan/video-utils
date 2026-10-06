//! Dependency-free streaming SHA-256 (FIPS 180-4).
//!
//! The hasher itself never allocates. `hash_reader`/`hash_file` allocate one
//! fixed 1 MiB read buffer per call and are intended for offline CLI use, not
//! for an audio render path.

use std::fmt;
use std::fs::File;
use std::io::{self, Read};
use std::path::Path;

/// Fixed read buffer used by [`hash_reader`] and [`hash_file`].
pub const READ_BUFFER_BYTES: usize = 1 << 20;

const K: [u32; 64] = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];

const H0: [u32; 8] = [
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
];

/// A finished 32-byte SHA-256 digest.
#[derive(Clone, Copy, PartialEq, Eq, Hash)]
pub struct Digest(pub [u8; 32]);

impl Digest {
    /// Lowercase hexadecimal form (64 characters).
    pub fn to_hex(&self) -> String {
        const HEX: &[u8; 16] = b"0123456789abcdef";
        let mut text = String::with_capacity(64);
        for byte in self.0 {
            text.push(HEX[usize::from(byte >> 4)] as char);
            text.push(HEX[usize::from(byte & 0x0f)] as char);
        }
        text
    }
}

impl fmt::Display for Digest {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.to_hex())
    }
}

impl fmt::Debug for Digest {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "Digest({})", self.to_hex())
    }
}

/// Returns true for exactly 64 lowercase hexadecimal characters.
pub fn is_lower_hex_digest(text: &str) -> bool {
    text.len() == 64 && text.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
}

/// Streaming SHA-256 state. Update splits never change the digest.
#[derive(Clone)]
pub struct Sha256 {
    state: [u32; 8],
    block: [u8; 64],
    block_len: usize,
    message_bytes: u64,
}

impl Default for Sha256 {
    fn default() -> Self {
        Self::new()
    }
}

impl Sha256 {
    pub const fn new() -> Self {
        Self {
            state: H0,
            block: [0; 64],
            block_len: 0,
            message_bytes: 0,
        }
    }

    /// Total message bytes consumed so far.
    pub fn len(&self) -> u64 {
        self.message_bytes
    }

    pub fn is_empty(&self) -> bool {
        self.message_bytes == 0
    }

    pub fn update(&mut self, mut data: &[u8]) {
        // FIPS 180-4 limits messages to 2^64 - 1 bits; files here are far smaller.
        self.message_bytes = self.message_bytes.wrapping_add(data.len() as u64);
        if self.block_len > 0 {
            let take = (64 - self.block_len).min(data.len());
            self.block[self.block_len..self.block_len + take].copy_from_slice(&data[..take]);
            self.block_len += take;
            data = &data[take..];
            if self.block_len < 64 {
                return;
            }
            let block = self.block;
            compress(&mut self.state, &block);
            self.block_len = 0;
        }
        let mut chunks = data.chunks_exact(64);
        for chunk in &mut chunks {
            let mut block = [0u8; 64];
            block.copy_from_slice(chunk);
            compress(&mut self.state, &block);
        }
        let rest = chunks.remainder();
        self.block[..rest.len()].copy_from_slice(rest);
        self.block_len = rest.len();
    }

    pub fn finalize(mut self) -> Digest {
        let bit_length = self.message_bytes.wrapping_mul(8);
        let mut tail = [0u8; 128];
        tail[..self.block_len].copy_from_slice(&self.block[..self.block_len]);
        tail[self.block_len] = 0x80;
        let total = if self.block_len < 56 { 64 } else { 128 };
        tail[total - 8..total].copy_from_slice(&bit_length.to_be_bytes());
        for chunk in tail[..total].chunks_exact(64) {
            let mut block = [0u8; 64];
            block.copy_from_slice(chunk);
            compress(&mut self.state, &block);
        }
        let mut out = [0u8; 32];
        for (slot, word) in out.chunks_exact_mut(4).zip(self.state) {
            slot.copy_from_slice(&word.to_be_bytes());
        }
        Digest(out)
    }
}

fn compress(state: &mut [u32; 8], block: &[u8; 64]) {
    let mut w = [0u32; 64];
    for (index, word) in block.chunks_exact(4).enumerate() {
        w[index] = u32::from_be_bytes([word[0], word[1], word[2], word[3]]);
    }
    for t in 16..64 {
        let s0 = w[t - 15].rotate_right(7) ^ w[t - 15].rotate_right(18) ^ (w[t - 15] >> 3);
        let s1 = w[t - 2].rotate_right(17) ^ w[t - 2].rotate_right(19) ^ (w[t - 2] >> 10);
        w[t] = w[t - 16]
            .wrapping_add(s0)
            .wrapping_add(w[t - 7])
            .wrapping_add(s1);
    }
    let [mut a, mut b, mut c, mut d, mut e, mut f, mut g, mut h] = *state;
    for t in 0..64 {
        let big_s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
        let ch = (e & f) ^ (!e & g);
        let t1 = h
            .wrapping_add(big_s1)
            .wrapping_add(ch)
            .wrapping_add(K[t])
            .wrapping_add(w[t]);
        let big_s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
        let maj = (a & b) ^ (a & c) ^ (b & c);
        let t2 = big_s0.wrapping_add(maj);
        h = g;
        g = f;
        f = e;
        e = d.wrapping_add(t1);
        d = c;
        c = b;
        b = a;
        a = t1.wrapping_add(t2);
    }
    for (slot, value) in state.iter_mut().zip([a, b, c, d, e, f, g, h]) {
        *slot = slot.wrapping_add(value);
    }
}

/// One-shot digest of an in-memory buffer.
pub fn digest(data: &[u8]) -> Digest {
    let mut hasher = Sha256::new();
    hasher.update(data);
    hasher.finalize()
}

/// Stream a reader to EOF with a fixed 1 MiB buffer; returns digest and byte count.
pub fn hash_reader<R: Read>(reader: &mut R) -> io::Result<(Digest, u64)> {
    let mut buffer = vec![0u8; READ_BUFFER_BYTES];
    let mut hasher = Sha256::new();
    loop {
        let read = match reader.read(&mut buffer) {
            Ok(0) => break,
            Ok(read) => read,
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            Err(error) => return Err(error),
        };
        hasher.update(&buffer[..read]);
    }
    let bytes = hasher.len();
    Ok((hasher.finalize(), bytes))
}

/// Typed failure for hashing a named file.
#[derive(Debug)]
pub enum HashFileError {
    NotFound,
    IsDirectory,
    NotRegular,
    PermissionDenied,
    Read(io::Error),
}

impl HashFileError {
    /// Stable machine-readable code.
    pub fn code(&self) -> &'static str {
        match self {
            Self::NotFound => "not_found",
            Self::IsDirectory => "is_directory",
            Self::NotRegular => "not_regular_file",
            Self::PermissionDenied => "permission_denied",
            Self::Read(_) => "read_error",
        }
    }

    fn from_io(error: io::Error) -> Self {
        match error.kind() {
            io::ErrorKind::NotFound => Self::NotFound,
            io::ErrorKind::PermissionDenied => Self::PermissionDenied,
            io::ErrorKind::IsADirectory => Self::IsDirectory,
            _ => Self::Read(error),
        }
    }
}

impl fmt::Display for HashFileError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::NotFound => f.write_str("not_found: no such file"),
            Self::IsDirectory => f.write_str("is_directory: path is a directory"),
            Self::NotRegular => f.write_str("not_regular_file: path is not a regular file"),
            Self::PermissionDenied => f.write_str("permission_denied: file is not readable"),
            Self::Read(error) => write!(f, "read_error: {error}"),
        }
    }
}

impl std::error::Error for HashFileError {}

/// Hash one file (following symlinks, like `shasum`). Directories, FIFOs and
/// other non-regular files are refused before any read.
pub fn hash_file(path: &Path) -> Result<(Digest, u64), HashFileError> {
    let metadata = std::fs::metadata(path).map_err(HashFileError::from_io)?;
    if metadata.is_dir() {
        return Err(HashFileError::IsDirectory);
    }
    if !metadata.is_file() {
        return Err(HashFileError::NotRegular);
    }
    let mut file = File::open(path).map_err(HashFileError::from_io)?;
    hash_reader(&mut file).map_err(HashFileError::from_io)
}

/// Format one `shasum -a 256` text-mode line (without trailing newline) from
/// raw name bytes. Names containing `\` or newline use the shasum/coreutils
/// escape: a leading `\`, then `\\` for backslash and `\n` for newline.
pub fn shasum_line(digest: &Digest, name: &[u8]) -> Vec<u8> {
    let escape = name.iter().any(|&b| b == b'\\' || b == b'\n');
    let mut line = Vec::with_capacity(name.len() + 68);
    if escape {
        line.push(b'\\');
    }
    line.extend_from_slice(digest.to_hex().as_bytes());
    line.extend_from_slice(b"  ");
    for &byte in name {
        match byte {
            b'\\' if escape => line.extend_from_slice(b"\\\\"),
            b'\n' if escape => line.extend_from_slice(b"\\n"),
            other => line.push(other),
        }
    }
    line
}

#[cfg(test)]
mod tests {
    use super::*;

    const MSG_448: &[u8] = b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq";
    const MSG_896: &[u8] = b"abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmnhijklmnoijklmnopjklmnopqklmnopqrlmnopqrsmnopqrstnopqrstu";

    fn million_a() -> Vec<u8> {
        vec![b'a'; 1_000_000]
    }

    #[test]
    fn fips_180_4_vectors() {
        let cases: [(&[u8], &str); 4] = [
            (
                b"",
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            ),
            (
                b"abc",
                "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            ),
            (
                MSG_448,
                "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1",
            ),
            (
                MSG_896,
                "cf5b16a778af8380036ce59e7b0492370b249b11e8f07a51afac45037afee9d1",
            ),
        ];
        for (message, expected) in cases {
            assert_eq!(digest(message).to_hex(), expected);
        }
        assert_eq!(
            digest(&million_a()).to_hex(),
            "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"
        );
    }

    #[test]
    fn every_split_point_matches_one_shot() {
        for message in [MSG_448, MSG_896] {
            let expected = digest(message);
            for split in 0..=message.len() {
                let mut hasher = Sha256::new();
                hasher.update(&message[..split]);
                hasher.update(&message[split..]);
                assert_eq!(hasher.finalize(), expected, "split {split}");
            }
        }
    }

    #[test]
    fn chunked_million_a_matches_for_all_chunk_sizes() {
        let message = million_a();
        let expected = digest(&message);
        for chunk in [1usize, 63, 64, 65, READ_BUFFER_BYTES + 1] {
            let mut hasher = Sha256::new();
            for part in message.chunks(chunk) {
                hasher.update(part);
            }
            assert_eq!(hasher.len(), 1_000_000);
            assert_eq!(hasher.finalize(), expected, "chunk {chunk}");
        }
        let (streamed, bytes) = hash_reader(&mut message.as_slice()).unwrap();
        assert_eq!((streamed, bytes), (expected, 1_000_000));
    }

    #[test]
    fn hex_validation_and_shasum_escaping() {
        assert!(is_lower_hex_digest(&digest(b"abc").to_hex()));
        assert!(!is_lower_hex_digest(&"A".repeat(64)));
        assert!(!is_lower_hex_digest(&"a".repeat(63)));
        let d = digest(b"abc");
        assert_eq!(
            shasum_line(&d, b"plain name"),
            format!("{}  plain name", d.to_hex()).into_bytes()
        );
        assert_eq!(
            shasum_line(&d, b"a\\b\nc"),
            format!("\\{}  a\\\\b\\nc", d.to_hex()).into_bytes()
        );
    }
}
