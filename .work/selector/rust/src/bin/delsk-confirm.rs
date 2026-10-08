//! S4-C real Rust selector driver.
//!
//! Input is a closed TSV generated from the frozen S4-C plan:
//!   T <tid> <object> <bytes> <version> <offset|-> <path-hex|-> <line-hex|->
//!   B <tid> <object> <bytes> <version> <offset|-> <path-hex|-> <line-hex|->
//!
//! Usage:
//!   delsk-confirm <STORE> <INPUT.tsv> <OUT.json>
//!
//! The binary reads every unique content object once, builds the real 64-byte
//! descriptor and Catalog, then executes K=2 over each query's exact frozen C_t.

use delsk_selector::{descriptor, select_top, Catalog, Object, HASHES};
use std::collections::{BTreeMap, HashMap};
use std::fs;
use std::path::{Path, PathBuf};
use std::time::Instant;

const K: usize = 2;

#[cfg(target_os = "linux")]
#[repr(C)]
struct Timespec {
    tv_sec: i64,
    tv_nsec: i64,
}

#[cfg(target_os = "linux")]
extern "C" {
    fn clock_gettime(clock_id: i32, tp: *mut Timespec) -> i32;
}

#[cfg(target_os = "linux")]
fn cpu_ns() -> u64 {
    const CLOCK_PROCESS_CPUTIME_ID: i32 = 2;
    let mut ts = Timespec { tv_sec: 0, tv_nsec: 0 };
    let rc = unsafe { clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &mut ts as *mut Timespec) };
    assert_eq!(rc, 0, "clock_gettime(CLOCK_PROCESS_CPUTIME_ID)");
    (ts.tv_sec as u64) * 1_000_000_000 + ts.tv_nsec as u64
}

#[cfg(not(target_os = "linux"))]
fn cpu_ns() -> u64 {
    panic!("delsk-confirm is pinned to the Linux GitHub-hosted S4-C runner");
}

fn decode_hex(value: &str) -> Option<String> {
    if value == "-" {
        return None;
    }
    assert!(value.len() % 2 == 0, "hex string length");
    let mut bytes = Vec::with_capacity(value.len() / 2);
    for i in (0..value.len()).step_by(2) {
        bytes.push(u8::from_str_radix(&value[i..i + 2], 16).expect("hex"));
    }
    Some(String::from_utf8(bytes).expect("utf8 metadata"))
}

#[derive(Clone)]
struct Meta {
    id: String,
    size: u64,
    version: i64,
    offset: Option<u64>,
    path: Option<String>,
    line: Option<String>,
}

impl Meta {
    fn object(&self, d: Vec<u64>) -> Object {
        Object {
            id: self.id.clone(),
            size: self.size,
            path: self.path.clone(),
            line: self.line.clone(),
            version: self.version,
            offset: self.offset,
            descriptor: d,
        }
    }
}

struct Query {
    tid: String,
    target: Meta,
    bases: Vec<Meta>,
}

fn parse_row(parts: &[&str]) -> Meta {
    assert_eq!(parts.len(), 8, "metadata row fields");
    let size: u64 = parts[3].parse().expect("bytes");
    let version: i64 = parts[4].parse().expect("version");
    let offset = if parts[5] == "-" { None } else { Some(parts[5].parse().expect("offset")) };
    Meta {
        id: parts[2].to_owned(),
        size,
        version,
        offset,
        path: decode_hex(parts[6]),
        line: decode_hex(parts[7]),
    }
}

fn load_queries(path: &Path) -> Vec<Query> {
    let text = fs::read_to_string(path).expect("input TSV");
    let mut targets: BTreeMap<String, Meta> = BTreeMap::new();
    let mut bases: BTreeMap<String, Vec<Meta>> = BTreeMap::new();

    for line in text.lines().filter(|line| !line.is_empty()) {
        let parts: Vec<&str> = line.split(char::from(9)).collect();
        assert_eq!(parts.len(), 8, "TSV shape");
        let kind = parts[0];
        let tid = parts[1].to_owned();
        let meta = parse_row(&parts);
        match kind {
            "T" => {
                assert!(targets.insert(tid, meta).is_none(), "duplicate target row");
            }
            "B" => bases.entry(tid).or_default().push(meta),
            _ => panic!("unknown row kind"),
        }
    }

    assert_eq!(targets.len(), 9, "S4-C target count");
    let mut queries = Vec::new();
    for (tid, target) in targets {
        let bs = bases.remove(&tid).expect("target bases");
        assert!(!bs.is_empty(), "empty C_t");
        assert!(bs.len() <= 64, "candidate cap");
        let mut ids: Vec<&str> = bs.iter().map(|b| b.id.as_str()).collect();
        ids.sort_unstable();
        ids.dedup();
        assert_eq!(ids.len(), bs.len(), "duplicate base object");
        queries.push(Query { tid, target, bases: bs });
    }
    assert!(bases.is_empty(), "bases for foreign target");
    assert_eq!(queries.iter().map(|q| q.bases.len()).sum::<usize>(), 106, "S4-C pair count");
    queries
}

fn unique_meta(queries: &[Query]) -> BTreeMap<String, Meta> {
    let mut out = BTreeMap::new();
    for q in queries {
        for meta in std::iter::once(&q.target).chain(q.bases.iter()) {
            match out.get(&meta.id) {
                Some(existing) => {
                    let existing: &Meta = existing;
                    assert_eq!(existing.size, meta.size, "object size drift");
                }
                None => {
                    out.insert(meta.id.clone(), meta.clone());
                }
            }
        }
    }
    out
}

fn json_string(s: &str) -> String {
    assert!(s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit()), "non-hex JSON identity");
    format!("\"{}\"", s)
}

/// Capacity is fixed at eight slots, not eight necessarily distinct observations.
/// Deliberately does not fill missing hashes with zero or duplicate hashes:
/// that would change the frozen MinHash resemblance/order semantics.
fn validate_descriptor_width(hashes: &[u64]) {
    assert!(hashes.len() <= HASHES, "descriptor exceeds eight-hash capacity");
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    assert_eq!(args.len(), 4, "usage: delsk-confirm STORE INPUT.tsv OUT.json");
    let store = PathBuf::from(&args[1]);
    let input = PathBuf::from(&args[2]);
    let output = PathBuf::from(&args[3]);

    let queries = load_queries(&input);
    let metas = unique_meta(&queries);

    let desc_wall = Instant::now();
    let desc_cpu0 = cpu_ns();
    let mut descriptors: HashMap<String, Vec<u64>> = HashMap::new();
    let mut scanned = 0u64;
    for (id, meta) in &metas {
        let data = fs::read(store.join(id)).expect("object bytes");
        assert_eq!(data.len() as u64, meta.size, "object size");
        scanned += data.len() as u64;
        let d = descriptor(&data);
        // Bottom-k retains at most eight *distinct* hashes. Repeated, short and
        // empty objects can have fewer; fixed-width accounting still reserves
        // 64 B per object, as required by the frozen S4-C protocol.
        validate_descriptor_width(&d);
        assert!(descriptors.insert(id.clone(), d).is_none());
    }
    let descriptor_cpu_ns = cpu_ns() - desc_cpu0;
    let descriptor_wall_ns = desc_wall.elapsed().as_nanos() as u64;

    let mut catalog_objects = Vec::with_capacity(metas.len());
    for (id, meta) in &metas {
        catalog_objects.push(meta.object(descriptors[id].clone()));
    }
    let catalog_wall = Instant::now();
    let catalog_cpu0 = cpu_ns();
    let catalog = Catalog::new(catalog_objects, usize::MAX);
    let catalog_cpu_ns = cpu_ns() - catalog_cpu0;
    let catalog_wall_ns = catalog_wall.elapsed().as_nanos() as u64;
    let index_bytes = catalog.index_bytes();

    let mut query_ns = Vec::with_capacity(queries.len());
    let mut selections: Vec<(String, Vec<String>)> = Vec::with_capacity(queries.len());
    for q in &queries {
        let target = q.target.object(descriptors[&q.target.id].clone());
        let base_objects: Vec<Object> = q.bases.iter()
            .map(|b| b.object(descriptors[&b.id].clone()))
            .collect();
        let refs: Vec<&Object> = base_objects.iter().collect();
        let started = Instant::now();
        let selected: Vec<String> = select_top(&target, &refs, K)
            .into_iter().map(|o| o.id.clone()).collect();
        query_ns.push(started.elapsed().as_nanos() as u64);
        assert_eq!(selected.len(), K.min(base_objects.len()), "K2 width");
        selections.push((q.tid.clone(), selected));
    }

    // Seven query-only rounds are retained for the paired-timing record. Descriptor
    // and catalog setup are outside these measurements.
    let mut query_round_ns = Vec::with_capacity(7);
    for _ in 0..7 {
        let started = Instant::now();
        for q in &queries {
            let target = q.target.object(descriptors[&q.target.id].clone());
            let base_objects: Vec<Object> = q.bases.iter()
                .map(|b| b.object(descriptors[&b.id].clone()))
                .collect();
            let refs: Vec<&Object> = base_objects.iter().collect();
            let got = select_top(&target, &refs, K);
            assert_eq!(got.len(), K.min(base_objects.len()));
        }
        query_round_ns.push(started.elapsed().as_nanos() as u64);
    }

    let selection_json = selections.iter().map(|(tid, ids)| {
        format!(
            "{{\"target_occurrence_id\":{},\"rust_k2\":[{}]}}",
            json_string(tid),
            ids.iter().map(|id| json_string(id)).collect::<Vec<_>>().join(",")
        )
    }).collect::<Vec<_>>().join(",");

    let query_json = query_ns.iter().map(u64::to_string).collect::<Vec<_>>().join(",");
    let round_json = query_round_ns.iter().map(u64::to_string).collect::<Vec<_>>().join(",");
    let doc = format!(
        "{{\"schema\":\"delsk.chunkshift-s4-confirm.rust-driver.v1\",         \"objects\":{},\"object_bytes_scanned\":{},\"descriptor_bytes\":{},         \"descriptor_wall_ns\":{},\"descriptor_cpu_ns\":{},         \"catalog_wall_ns\":{},\"catalog_cpu_ns\":{},\"index_bytes\":{},         \"query_ns\":[{}],\"query_round_ns\":[{}],\"selections\":[{}]}}\n",
        metas.len(), scanned, metas.len() * 64, descriptor_wall_ns, descriptor_cpu_ns,
        catalog_wall_ns, catalog_cpu_ns, index_bytes, query_json, round_json, selection_json
    );
    fs::write(output, doc).expect("write output");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn short_empty_and_repetitive_descriptors_are_valid() {
        for bytes in [
            &b""[..],
            &b"a"[..],
            &b"abcdefg"[..],
            &b"abcdefgh"[..],
            &[0x55; 4096][..],
        ] {
            let d = descriptor(bytes);
            validate_descriptor_width(&d);
        }
        assert_eq!(descriptor(b"").len(), 0);
        assert_eq!(descriptor(b"a").len(), 1);
        assert_eq!(descriptor(&[0x55; 4096]).len(), 1);
        // Storage is still the preregistered fixed 64 B per catalog object.
        assert_eq!(3 * HASHES * std::mem::size_of::<u64>(), 192);
    }

    #[test]
    fn distinct_valid_hashes_can_exceed_frozen_index_budget() {
        // Synthetic *structural* counterexample, not sealed S4-C evidence.
        // Eight unique hashes per object require 8 B/key + 4 B/posting id
        // in the current Catalog::index_bytes model: 96 B/object.
        let objects: Vec<Object> = (0..2u64)
            .map(|i| Object {
                id: format!("base-{i}"),
                size: 4096,
                path: None,
                line: None,
                version: 0,
                offset: None,
                descriptor: (i * 8 + 1..=i * 8 + 8).collect(),
            })
            .collect();
        let catalog = Catalog::new(objects, usize::MAX);
        assert_eq!(catalog.index_bytes(), 2 * 96);
        assert!(catalog.index_bytes() > 2 * 64);
    }
}
