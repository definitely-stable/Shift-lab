//! H11-B0 synthetic, deterministic, non-decision retrieval smoke.
//! No S4-C E1 or natural holdout. Usage: delsk-h11b0 <N> <queries>
use delsk_selector::{Catalog, Object, RetrievalCertification};
use std::time::Instant;

fn obj(i: usize) -> Object {
    let fam = i / 16;
    let f = fam as u64;
    let mut hashes = vec![
        ((f % 257 + 1) << 32) | 0x10,
        ((f % 257 + 1) << 32) | 0x20,
        ((i as u64 + 50_000) << 32) | (i as u64 & 0xffff),
        ((i as u64 + 60_000) << 32) | 0x33,
    ];
    if i % 5 == 0 { hashes.push(0x5555_0000_0000_0001); }
    if i % 11 == 0 { hashes.push(0x7777_0000_0000_0001 + (i as u64 & 0xffff)); }
    hashes.sort_unstable();
    hashes.dedup();
    Object {
        id: format!("o{i:08}"), size: 4096 + (i % 67) as u64,
        path: (fam % 4 != 0).then(|| format!("root/f{fam}")),
        line: (fam % 4 != 0).then(|| "r1".to_owned()),
        version: (i % 16) as i64,
        offset: Some((i % 16) as u64 * 4096),
        descriptor: hashes,
    }
}

fn vm_status_bytes(field: &str) -> Option<u64> {
    let s = std::fs::read_to_string("/proc/self/status").ok()?;
    let line = s.lines().find(|x| x.starts_with(field))?;
    let kib: u64 = line.split_whitespace().nth(1)?.parse().ok()?;
    kib.checked_mul(1024)
}

fn quantile(mut v: Vec<u128>, q: f64) -> f64 {
    v.sort_unstable();
    let i = ((v.len() - 1) as f64 * q).ceil() as usize;
    v[i] as f64 / 1000.0
}

fn run(n: usize, queries: usize) -> String {
    assert!((64..=1_000_000).contains(&n));
    assert!((2..=32).contains(&queries));
    let started = Instant::now();
    let objects: Vec<Object> = (0..n).map(obj).collect();
    let descriptor_s = started.elapsed().as_secs_f64();
    let targets: Vec<Object> = (0..queries)
        .map(|q| objects[(q * n / queries).min(n - 1)].clone())
        .chain(std::iter::once(Object {
            id: "unseen-zero-target".to_owned(), size: 4096,
            path: None, line: None, version: 0, offset: None,
            descriptor: vec![u64::MAX - 1],
        })).collect();
    let start = Instant::now();
    let mut catalog = Catalog::new(objects, usize::MAX);
    let index_s = start.elapsed().as_secs_f64();
    let index_bytes = catalog.index_bytes();
    let rss_after_build = vm_status_bytes("VmRSS:");
    let mut results = Vec::new();
    for cap in [2usize, 32, usize::MAX] {
        catalog.posting_cap = cap;
        for k in [1usize, 2, 4] {
            let (mut ex_ns, mut cert_ns, mut ap_ns) = (Vec::new(), Vec::new(), Vec::new());
            let (mut indexed, mut sparse, mut capped, mut invalid, mut ap_mismatch) =
                (0usize, 0usize, 0usize, 0usize, 0usize);
            for (q, target) in targets.iter().enumerate() {
                let (exact, certified, approximate);
                if q % 2 == 0 {
                    let t = Instant::now();
                    exact = catalog.select_exact(target, k);
                    ex_ns.push(t.elapsed().as_nanos());
                    let t = Instant::now();
                    certified = catalog.select_indexed_certified(target, k);
                    cert_ns.push(t.elapsed().as_nanos());
                    let t = Instant::now();
                    approximate = catalog.select_indexed(target, k).0;
                    ap_ns.push(t.elapsed().as_nanos());
                } else {
                    let t = Instant::now();
                    certified = catalog.select_indexed_certified(target, k);
                    cert_ns.push(t.elapsed().as_nanos());
                    let t = Instant::now();
                    approximate = catalog.select_indexed(target, k).0;
                    ap_ns.push(t.elapsed().as_nanos());
                    let t = Instant::now();
                    exact = catalog.select_exact(target, k);
                    ex_ns.push(t.elapsed().as_nanos());
                }
                assert_eq!(certified.ids, exact, "H11 mismatch n={n} cap={cap} k={k} q={q}");
                ap_mismatch += usize::from(approximate != exact);
                match certified.certification {
                    RetrievalCertification::IndexedExact => indexed += 1,
                    RetrievalCertification::ExactFallbackSparse => sparse += 1,
                    RetrievalCertification::ExactFallbackCapped => capped += 1,
                    RetrievalCertification::ExactFallbackInvalidInput => invalid += 1,
                }
            }
            results.push(format!(
                "{{\"posting_cap\":{},\"k\":{},\"queries\":{},\"indexed_exact\":{},\"fallback_sparse\":{},\"fallback_capped\":{},\"fallback_invalid\":{},\"approximate_mismatches\":{},\"exact_p50_us\":{:.3},\"exact_p95_us\":{:.3},\"exact_p99_us\":{:.3},\"certified_p50_us\":{:.3},\"certified_p95_us\":{:.3},\"certified_p99_us\":{:.3},\"approximate_p95_us\":{:.3}}}",
                if cap == usize::MAX { 0 } else { cap }, k, targets.len(),
                indexed, sparse, capped, invalid, ap_mismatch,
                quantile(ex_ns.clone(), 0.5), quantile(ex_ns.clone(), 0.95), quantile(ex_ns, 0.99),
                quantile(cert_ns.clone(), 0.5), quantile(cert_ns.clone(), 0.95), quantile(cert_ns, 0.99),
                quantile(ap_ns, 0.95),
            ));
        }
    }
    format!(
        "{{\"schema\":\"delsk.h11b0.synthetic-smoke.v1\",\"scope\":\"SYNTHETIC_ONLY_NOT_DECISION_EVIDENCE\",\"objects\":{},\"target_queries\":{},\"descriptor_build_seconds\":{:.6},\"index_build_seconds\":{:.6},\"logical_index_bytes\":{},\"rss_after_catalog_build_bytes\":{},\"process_peak_rss_bytes\":{},\"cases\":[{}]}}",
        n, targets.len(), descriptor_s, index_s, index_bytes,
        rss_after_build.map_or("null".into(), |x| x.to_string()),
        vm_status_bytes("VmHWM:").map_or("null".into(), |x| x.to_string()), results.join(",")
    )
}

fn main() {
    let args: Vec<_> = std::env::args().collect();
    assert!(args.len() == 3, "usage: delsk-h11b0 N QUERIES");
    let n: usize = args[1].parse().expect("integer object count");
    let q: usize = args[2].parse().expect("integer query count");
    println!("{}", run(n, q));
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn deterministic_small_catalog_parity() {
        let report = run(128, 4);
        assert!(report.contains("\"scope\":\"SYNTHETIC_ONLY_NOT_DECISION_EVIDENCE\""));
        assert!(report.contains("\"fallback_capped\""));
        assert!(report.contains("\"fallback_sparse\""));
        assert!(report.contains("\"process_peak_rss_bytes\""));
    }
}
