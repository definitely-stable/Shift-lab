//! S2 cost benchmark of delsk.simple-selector.v1 (.work/selector/s2.md). Synthetic, deterministic workload:
//! descriptor throughput, then catalogs of N objects (families of 16 versions of 4 KiB objects) with exact-scan
//! and indexed queries. Prints one JSON document. Quality against an oracle is not measured here.
//!
//!     delsk-bench <N,N,...> [queries]

use delsk_selector::{descriptor, xorshift_bytes, Catalog, DescriptorBuilder, Object};
use std::time::Instant;

const OBJECT_BYTES: usize = 4096;
const VERSIONS: u64 = 16;
const K: usize = 2;
const CAPS: [usize; 3] = [16, 64, 1024];

fn peak_rss_bytes() -> Option<u64> {
    let status = std::fs::read_to_string("/proc/self/status").ok()?;
    let line = status.lines().find(|l| l.starts_with("VmHWM:"))?;
    let kb: u64 = line.split_whitespace().nth(1)?.parse().ok()?;
    Some(kb * 1024)
}

fn quantile(xs: &mut [f64], p: f64) -> f64 {
    xs.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let h = (xs.len() - 1) as f64 * p;
    let lo = h.floor() as usize;
    let hi = (lo + 1).min(xs.len() - 1);
    xs[lo] + (h - lo as f64) * (xs[hi] - xs[lo])
}

/// Version v of family f: 1 KiB of boilerplate shared by every 32nd family (popular hashes), the family body, and
/// 8 cumulative 16-byte edits per version. Every 8th family is a fork of family f/2 with 64 extra edits, so
/// related bases also exist across families.
fn object_bytes(f: u64, v: u64) -> Vec<u8> {
    let root = if f % 8 == 7 { f / 2 } else { f };
    let mut data = xorshift_bytes(root.wrapping_mul(0x9e3779b97f4a7c15) | 1, OBJECT_BYTES);
    data[..1024].copy_from_slice(&xorshift_bytes(1_000 + f % 32, 1024));
    let mut edits: Vec<u64> = (0..8 * v).map(|e| f * 1_000_003 + e + 7).collect();
    if root != f {
        edits.extend((0..64).map(|e| f * 7_000_001 + e + 3));
    }
    for seed in edits {
        let noise = xorshift_bytes(seed, 18);
        let at = 1024 + (usize::from(noise[0]) << 8 | usize::from(noise[1])) % (OBJECT_BYTES - 1040);
        data[at..at + 16].copy_from_slice(&noise[2..]);
    }
    data
}

fn catalog(n: u64) -> (Vec<Object>, f64) {
    let started = Instant::now();
    let objects = (0..n)
        .map(|i| {
            let (f, v) = (i / VERSIONS, i % VERSIONS);
            let data = object_bytes(f, v);
            // A quarter of the families carry no path metadata: those queries rely on content alone.
            let path = (f % 4 != 0).then(|| format!("fam{f}/obj"));
            Object {
                id: format!("{i:08}"),
                size: data.len() as u64,
                line: path.as_ref().map(|_| "1".to_owned()),
                path,
                version: v as i64,
                offset: None,
                descriptor: descriptor(&data),
            }
        })
        .collect();
    (objects, started.elapsed().as_secs_f64())
}

fn throughput() -> String {
    let data = xorshift_bytes(99, 256 << 20);
    let started = Instant::now();
    let d = descriptor(&data);
    let one = started.elapsed().as_secs_f64();
    let started = Instant::now();
    let mut b = DescriptorBuilder::new();
    for chunk in data.chunks(65536) {
        b.update(chunk);
    }
    let streamed = b.finish();
    let chunked = started.elapsed().as_secs_f64();
    assert_eq!(d, streamed);
    format!(
        "{{\"bytes\": {}, \"one_call_mib_s\": {:.1}, \"streamed_64k_mib_s\": {:.1}}}",
        data.len(),
        data.len() as f64 / one / 1048576.0,
        data.len() as f64 / chunked / 1048576.0
    )
}

fn run(n: u64, queries: u64) -> String {
    let (objects, build_seconds) = catalog(n);
    // Targets: the latest version of evenly spaced families; the exact scan sees every other object.
    let families = (n / VERSIONS).max(1);
    let targets: Vec<Object> =
        (0..queries.min(families)).map(|q| objects[((q * families / queries.min(families)) * VERSIONS
            + VERSIONS - 1).min(n - 1) as usize].clone()).collect();
    let mut cap_rows = Vec::new();
    let mut exact_us = Vec::new();
    let mut exact_answers = Vec::new();
    let index_started = Instant::now();
    let catalog = Catalog::new(objects, usize::MAX);
    let index_seconds = index_started.elapsed().as_secs_f64();
    let index_bytes = catalog.index_bytes();
    for t in &targets {
        let s = Instant::now();
        exact_answers.push(catalog.select_exact(t, K));
        exact_us.push(s.elapsed().as_secs_f64() * 1e6);
    }
    let mut catalog = catalog;
    for cap in CAPS {
        catalog.posting_cap = cap;
        let (mut us, mut same, mut top1, mut cands, mut capped) = (Vec::new(), 0, 0, 0usize, 0usize);
        for (t, exact) in targets.iter().zip(&exact_answers) {
            let s = Instant::now();
            let (got, stats) = catalog.select_indexed(t, K);
            us.push(s.elapsed().as_secs_f64() * 1e6);
            same += usize::from(&got == exact);
            top1 += usize::from(exact.first().is_some_and(|e| got.contains(e)));
            cands += stats.candidates;
            capped += stats.capped_postings;
        }
        let q = targets.len() as f64;
        cap_rows.push(format!(
            "{{\"posting_cap\": {cap}, \"p50_us\": {:.1}, \"p95_us\": {:.1}, \"same_top{K}_as_exact\": {:.4}, \
             \"exact_top1_found\": {:.4}, \"mean_candidates\": {:.1}, \"capped_postings_per_query\": {:.2}}}",
            quantile(&mut us, 0.5), quantile(&mut us, 0.95), same as f64 / q, top1 as f64 / q, cands as f64 / q,
            capped as f64 / q
        ));
    }
    format!(
        "{{\"objects\": {n}, \"object_bytes\": {OBJECT_BYTES}, \"queries\": {}, \"k\": {K}, \
         \"descriptor_build_seconds\": {build_seconds:.3}, \"index_build_seconds\": {index_seconds:.3}, \
         \"descriptor_bytes\": {}, \"index_bytes\": {index_bytes}, \"peak_rss_bytes\": {}, \
         \"exact\": {{\"p50_us\": {:.1}, \"p95_us\": {:.1}}}, \"indexed\": [{}]}}",
        targets.len(),
        n * 64,
        peak_rss_bytes().map_or("null".to_owned(), |b| b.to_string()),
        quantile(&mut exact_us, 0.5),
        quantile(&mut exact_us, 0.95),
        cap_rows.join(", ")
    )
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let sizes: Vec<u64> = args.get(1).map_or("10000".to_owned(), Clone::clone)
        .split(',').map(|s| s.parse().expect("N")).collect();
    let queries: u64 = args.get(2).map_or(200, |s| s.parse().expect("queries"));
    let runs: Vec<String> = sizes.iter().map(|&n| run(n, queries)).collect();
    println!(
        "{{\"schema\": \"delsk.selector.s2-bench.v1\", \"spec\": \"delsk.simple-selector.v1\", \
         \"throughput\": {}, \"catalogs\": [{}]}}",
        throughput(),
        runs.join(", ")
    );
}
