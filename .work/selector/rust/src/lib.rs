//! Delsk simple selector `delsk.simple-selector.v1` (.work/selector/README.md).
//!
//! Scalar reference that must order bases exactly like `.work/tools/simple_selector.py`: a 64-byte bottom-k
//! MinHash descriptor of 8-byte shingles and the interleave of a metadata order with a content order. The
//! [`Catalog`] adds an index for large object sets: a path map and an inverted index over descriptor hashes with
//! capped postings, next to an exact scan.

use std::cmp::Ordering;
use std::collections::HashMap;

/// Hashes per descriptor: 8 x 8 bytes = 64 bytes.
pub const HASHES: usize = 8;
/// Shingle length in bytes.
pub const SHINGLE: usize = 8;
/// Mixer seed; equal to the DELSK-004 Slice A sketch seed.
pub const SEED: u64 = 20261006;

#[inline]
fn mix(w: u64) -> u64 {
    let mut z = w ^ SEED;
    z = (z ^ (z >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94d049bb133111eb);
    z ^ (z >> 31)
}

/// Streaming descriptor builder: feed bytes in any split, `finish` gives the same descriptor as one call.
#[derive(Clone, Debug, Default)]
pub struct DescriptorBuilder {
    window: u64,
    seen: u64,
    smallest: Vec<u64>,
}

impl DescriptorBuilder {
    pub fn new() -> Self {
        Self { window: 0, seen: 0, smallest: Vec::with_capacity(HASHES + 1) }
    }

    #[inline]
    fn offer(&mut self, z: u64) {
        let full = self.smallest.len() == HASHES;
        if full && z >= self.smallest[HASHES - 1] {
            return;
        }
        if let Err(at) = self.smallest.binary_search(&z) {
            self.smallest.insert(at, z);
            if self.smallest.len() > HASHES {
                self.smallest.pop();
            }
        }
    }

    pub fn update(&mut self, data: &[u8]) {
        for &byte in data {
            self.window = (self.window << 8) | u64::from(byte);
            self.seen += 1;
            if self.seen >= SHINGLE as u64 {
                let z = mix(self.window);
                self.offer(z);
            }
        }
    }

    /// The 8 smallest distinct mixed shingles, ascending. An object shorter than 8 bytes is one shingle of its
    /// whole content (big-endian), the empty object has an empty descriptor.
    pub fn finish(mut self) -> Vec<u64> {
        if self.seen > 0 && self.seen < SHINGLE as u64 {
            let z = mix(self.window);
            self.offer(z);
        }
        self.smallest
    }
}

pub fn descriptor(data: &[u8]) -> Vec<u64> {
    let mut b = DescriptorBuilder::new();
    b.update(data);
    b.finish()
}

/// (shared, union) among the 8 smallest hashes of the union of two descriptors; resemblance = shared / union.
pub fn resemblance(a: &[u64], b: &[u64]) -> (u32, u32) {
    let (a, b) = (&a[..a.len().min(HASHES)], &b[..b.len().min(HASHES)]);
    let (mut i, mut j, mut union, mut shared) = (0, 0, 0u32, 0u32);
    while union < HASHES as u32 && (i < a.len() || j < b.len()) {
        match (a.get(i), b.get(j)) {
            (Some(x), Some(y)) if x == y => {
                shared += 1;
                i += 1;
                j += 1;
            }
            (Some(x), Some(y)) if x < y => i += 1,
            (Some(_), None) => i += 1,
            _ => j += 1,
        }
        union += 1;
    }
    (shared, union)
}

/// Descending resemblance as an exact rational comparison (0/0 counts as 0).
fn cmp_resemblance_desc(x: (u32, u32), y: (u32, u32)) -> Ordering {
    let lhs = u64::from(y.0) * u64::from(x.1.max(1));
    let rhs = u64::from(x.0) * u64::from(y.1.max(1));
    lhs.cmp(&rhs)
}

/// What the selector may know about an object.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Object {
    pub id: String,
    pub size: u64,
    pub path: Option<String>,
    pub line: Option<String>,
    pub version: i64,
    pub offset: Option<u64>,
    pub descriptor: Vec<u64>,
}

fn gap(t: &Object, b: &Object) -> u64 {
    t.size.abs_diff(b.size)
}

/// Bases with the target's path and release line: nearest offset, latest earlier version, size gap, id.
pub fn metadata_order<'a>(t: &Object, bases: &'a [Object]) -> Vec<&'a Object> {
    let Some(path) = &t.path else { return Vec::new() };
    let mut same: Vec<&Object> =
        bases.iter().filter(|b| b.path.as_ref() == Some(path) && b.line == t.line).collect();
    let toff = t.offset.unwrap_or(0);
    same.sort_by(|x, y| {
        (x.offset.unwrap_or(0).abs_diff(toff), -x.version, gap(t, x), &x.id)
            .cmp(&(y.offset.unwrap_or(0).abs_diff(toff), -y.version, gap(t, y), &y.id))
    });
    same
}

/// All bases by descending resemblance, then size gap, then id.
pub fn content_order<'a>(t: &Object, bases: &'a [Object]) -> Vec<&'a Object> {
    let mut scored: Vec<((u32, u32), &Object)> =
        bases.iter().map(|b| (resemblance(&t.descriptor, &b.descriptor), b)).collect();
    scored.sort_by(|(rx, x), (ry, y)| {
        cmp_resemblance_desc(*rx, *ry).then_with(|| (gap(t, x), &x.id).cmp(&(gap(t, y), &y.id)))
    });
    scored.into_iter().map(|(_, b)| b).collect()
}

/// meta[0], content[0], meta[1], content[1], ... without repeats.
pub fn interleave<'a>(meta: &[&'a Object], content: &[&'a Object]) -> Vec<&'a Object> {
    let mut out: Vec<&Object> = Vec::with_capacity(content.len());
    let mut seen = std::collections::HashSet::new();
    for i in 0..meta.len().max(content.len()) {
        for order in [meta, content] {
            if let Some(o) = order.get(i) {
                if seen.insert(o.id.as_str()) {
                    out.push(o);
                }
            }
        }
    }
    out
}

/// The first K bases of the full order; K >= |bases| is exhaustive.
pub fn select<'a>(t: &Object, bases: &'a [Object], k: usize) -> Vec<&'a Object> {
    let mut order = interleave(&metadata_order(t, bases), &content_order(t, bases));
    order.truncate(k);
    order
}

/// First K of the full order without sorting every base: only the first K of each component order can appear in
/// the first K of the interleave (each step emits at least one new content element).
pub fn select_top<'a>(t: &Object, bases: &[&'a Object], k: usize) -> Vec<&'a Object> {
    if k == 0 {
        return Vec::new();
    }
    let mut meta: Vec<&Object> = match &t.path {
        Some(path) => bases.iter().copied().filter(|b| b.path.as_ref() == Some(path) && b.line == t.line).collect(),
        None => Vec::new(),
    };
    let toff = t.offset.unwrap_or(0);
    let meta_key = |x: &&Object| (x.offset.unwrap_or(0).abs_diff(toff), -x.version, gap(t, x), x.id.clone());
    meta.sort_by_cached_key(meta_key);
    meta.truncate(k);
    let mut scored: Vec<((u32, u32), &Object)> =
        bases.iter().map(|b| (resemblance(&t.descriptor, &b.descriptor), *b)).collect();
    let cmp = |(rx, x): &((u32, u32), &Object), (ry, y): &((u32, u32), &Object)| {
        cmp_resemblance_desc(*rx, *ry).then_with(|| (gap(t, x), &x.id).cmp(&(gap(t, y), &y.id)))
    };
    if scored.len() > k {
        scored.select_nth_unstable_by(k - 1, cmp);
        scored.truncate(k);
    }
    scored.sort_by(cmp);
    let content: Vec<&Object> = scored.into_iter().map(|(_, b)| b).collect();
    let mut out = interleave(&meta, &content);
    out.truncate(k);
    out
}

/// Packed postings. Each entry contains a 32-bit fingerprint (upper bits of
/// the full descriptor hash) and a 24-bit object index, stored in exactly 7 bytes.
/// Full 64-bit descriptor hashes remain authoritative when reading the index.
///
/// For catalogs larger than 2^24 objects, fall back to two u32 words per
/// posting. Both layouts store exactly one entry per original descriptor hash.
/// Fingerprint collisions can add *lookup candidates*, never remove an exact
/// hash hit while its posting bucket is not truncated.
enum PostingStorage {
    Compact(Vec<[u8; 7]>),
    Wide(Vec<(u32, u32)>),
}

impl PostingStorage {
    fn new(objects: &[Object]) -> Self {
        let capacity = objects.iter().map(|o| o.descriptor.len()).sum();
        if objects.len() <= 1 << 24 {
            let mut rows = Vec::with_capacity(capacity);
            for (i, o) in objects.iter().enumerate() {
                let id = u32::try_from(i).expect("compact object index");
                for &hash in &o.descriptor {
                    let key = (hash >> 32) as u32;
                    let bytes = key.to_be_bytes();
                    rows.push([
                        bytes[0], bytes[1], bytes[2], bytes[3],
                        (id >> 16) as u8, (id >> 8) as u8, id as u8,
                    ]);
                }
            }
            rows.sort_unstable();
            Self::Compact(rows)
        } else {
            let mut rows = Vec::with_capacity(capacity);
            for (i, o) in objects.iter().enumerate() {
                let id = u32::try_from(i).expect("catalog index requires u32 object count");
                for &hash in &o.descriptor {
                    rows.push(((hash >> 32) as u32, id));
                }
            }
            rows.sort_unstable();
            Self::Wide(rows)
        }
    }

    fn accounted_bytes(&self) -> usize {
        match self {
            Self::Compact(rows) => rows.len() * std::mem::size_of::<[u8; 7]>(),
            Self::Wide(rows) => rows.len() * std::mem::size_of::<(u32, u32)>(),
        }
    }

    fn fingerprint_hits(&self, hash: u64, cap: usize, out: &mut Vec<u32>) -> bool {
        let key = (hash >> 32) as u32;
        match self {
            Self::Compact(rows) => {
                let prefix = key.to_be_bytes();
                let start = rows.partition_point(|e| e[..4].cmp(&prefix[..]).is_lt());
                let end = start + rows[start..].partition_point(|e| e[..4].eq(&prefix[..]));
                for entry in rows[start..end].iter().take(cap) {
                    out.push((u32::from(entry[4]) << 16)
                        | (u32::from(entry[5]) << 8) | u32::from(entry[6]));
                }
                end - start > cap
            }
            Self::Wide(rows) => {
                let start = rows.partition_point(|e| e.0 < key);
                let end = start + rows[start..].partition_point(|e| e.0 == key);
                out.extend(rows[start..end].iter().take(cap).map(|e| e.1));
                end - start > cap
            }
        }
    }
}

/// Catalog of base objects with a path map and a packed, 32-bit-fingerprint
/// inverted index. The entire 64-bit descriptor is kept separately for scoring.
/// This is research-only infrastructure, not a frozen public representation.
pub struct Catalog {
    pub objects: Vec<Object>,
    by_path: HashMap<(String, Option<String>), Vec<u32>>,
    postings: PostingStorage,
    /// Maximum entries read per fingerprint bucket in an indexed query.
    pub posting_cap: usize,
}

/// Counters of one indexed query.
#[derive(Clone, Copy, Debug, Default)]
pub struct QueryStats {
    pub candidates: usize,
    pub capped_postings: usize,
}

impl Catalog {
    pub fn new(objects: Vec<Object>, posting_cap: usize) -> Self {
        assert!(objects.len() <= u32::MAX as usize, "catalog object limit u32");
        let mut by_path: HashMap<(String, Option<String>), Vec<u32>> = HashMap::new();
        for (i, o) in objects.iter().enumerate() {
            if let Some(p) = &o.path {
                by_path.entry((p.clone(), o.line.clone())).or_default().push(i as u32);
            }
        }
        let postings = PostingStorage::new(&objects);
        Self { objects, by_path, postings, posting_cap }
    }

    /// Logical index payload: packed fingerprint+object-index entries plus
    /// path posting IDs. This preserves the S4-C index_bytes cost boundary,
    /// but does not represent HashMap/Vec/string allocator overhead or RSS.
    /// Those must be measured independently for product claims.
    pub fn index_bytes(&self) -> usize {
        let path_ids: usize = self.by_path.values().map(|v| v.len() * 4).sum();
        self.postings.accounted_bytes() + path_ids
    }

    /// Exact selection over every object except the target itself.
    pub fn select_exact(&self, t: &Object, k: usize) -> Vec<String> {
        let bases: Vec<&Object> = self.objects.iter().filter(|o| o.id != t.id).collect();
        select_top(t, &bases, k).into_iter().map(|o| o.id.clone()).collect()
    }

    /// Approximate indexed search: metadata matches and candidates sharing
    /// a full 64-bit descriptor hash. Only 32-bit fingerprints are indexed;
    /// the full 64-bit hash is checked before a posting becomes a candidate.
    /// Truncation is performed over fingerprint buckets (conservative cap
    /// accounting), so this remains approximate and can omit bases.
    pub fn select_indexed(&self, t: &Object, k: usize) -> (Vec<String>, QueryStats) {
        let mut stats = QueryStats::default();
        let mut ids: Vec<u32> = Vec::new();
        if let Some(p) = &t.path {
            if let Some(v) = self.by_path.get(&(p.clone(), t.line.clone())) {
                ids.extend_from_slice(v);
            }
        }
        for &h in &t.descriptor {
            let mut found = Vec::new();
            if self.postings.fingerprint_hits(h, self.posting_cap, &mut found) {
                stats.capped_postings += 1;
            }
            // Fingerprints are only a lookup accelerator; never equate
            // a 32-bit collision with a full descriptor-hash match.
            ids.extend(found.into_iter().filter(|&id| {
                self.objects[id as usize].descriptor.contains(&h)
            }));
        }
        ids.sort_unstable();
        ids.dedup();
        let bases: Vec<&Object> =
            ids.into_iter().map(|i| &self.objects[i as usize]).filter(|o| o.id != t.id).collect();
        stats.candidates = bases.len();
        (select_top(t, &bases, k).into_iter().map(|o| o.id.clone()).collect(), stats)
    }
}

/// Deterministic test bytes shared with simple_selector.py: xorshift64, low byte of each step.
pub fn xorshift_bytes(seed: u64, n: usize) -> Vec<u8> {
    let mut x = if seed == 0 { 1 } else { seed };
    (0..n)
        .map(|_| {
            x ^= x << 13;
            x ^= x >> 7;
            x ^= x << 17;
            (x & 0xff) as u8
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn streaming_splits_do_not_matter() {
        let data = xorshift_bytes(42, 10_000);
        let whole = descriptor(&data);
        for split in [0, 1, 7, 8, 9, 4095, 9_999] {
            let mut b = DescriptorBuilder::new();
            b.update(&data[..split]);
            b.update(&data[split..]);
            assert_eq!(b.finish(), whole, "split {split}");
        }
    }

    #[test]
    fn select_top_equals_the_full_order() {
        let objs: Vec<Object> = (0..40u64)
            .map(|i| {
                let mut data = xorshift_bytes(7, 3000);
                data.truncate(3000 - (i as usize % 7) * 13);
                for j in 0..(i as usize % 9) {
                    data[(j * 331 + i as usize * 17) % 2900] ^= 0x5a;
                }
                Object {
                    id: format!("o{i:02}"),
                    size: data.len() as u64,
                    path: (i % 3 != 0).then(|| format!("p{}", i % 2)),
                    line: (i % 5 != 0).then(|| "1".to_owned()),
                    version: (i % 11) as i64,
                    offset: (i % 4 != 0).then_some(i * 4096 % 16384),
                    descriptor: descriptor(&data),
                }
            })
            .collect();
        for t in &objs {
            let bases: Vec<Object> = objs.iter().filter(|o| o.id != t.id).cloned().collect();
            let refs: Vec<&Object> = bases.iter().collect();
            for k in [0, 1, 2, 3, 5, 8, 39, 50] {
                let full: Vec<&str> = select(t, &bases, k).iter().map(|o| o.id.as_str()).collect();
                let top: Vec<&str> = select_top(t, &refs, k).iter().map(|o| o.id.as_str()).collect();
                assert_eq!(top, full, "target {} k {k}", t.id);
            }
        }
    }

    #[test]
    fn short_inputs() {
        assert!(descriptor(b"").is_empty());
        assert_eq!(descriptor(b"abc").len(), 1);
        let mut b = DescriptorBuilder::new();
        b.update(b"ab");
        b.update(b"c");
        assert_eq!(b.finish(), descriptor(b"abc"));
    }
}
