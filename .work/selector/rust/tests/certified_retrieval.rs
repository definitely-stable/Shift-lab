//! H11 research foundation: exactness is tested against the full-order oracle.
//! This suite does NOT measure performance or touch the sealed S4-C corpus.
use delsk_selector::{
    Catalog, Object, RetrievalCertification, xorshift_bytes, descriptor,
};

fn obj(id: &str, size: u64, hashes: &[u64], path: Option<&str>) -> Object {
    Object {
        id: id.into(),
        size,
        path: path.map(str::to_owned),
        line: path.map(|_| "stable".into()),
        version: 1,
        offset: None,
        descriptor: hashes.to_vec(),
    }
}

fn assert_exact(catalog: &Catalog, t: &Object, k: usize) -> RetrievalCertification {
    let got = catalog.select_indexed_certified(t, k);
    assert_eq!(got.ids, catalog.select_exact(t, k), "k={k}");
    got.certification
}

#[test]
fn zero_overlap_without_path_must_fallback() {
    let t = obj("target", 100, &[11], None);
    let catalog = Catalog::new(
        vec![obj("far", 10, &[50], None), obj("closest", 99, &[60], None)],
        64,
    );
    assert!(catalog.select_indexed(&t, 1).0.is_empty());
    let got = catalog.select_indexed_certified(&t, 1);
    assert_eq!(got.ids, vec!["closest"]);
    assert_eq!(got.certification, RetrievalCertification::ExactFallbackSparse);
    assert_eq!(got.stats.positive_candidates, 0);
}

#[test]
fn metadata_only_is_not_mistaken_for_positive_resemblance() {
    let t = obj("target", 100, &[11], Some("file.bin"));
    let catalog = Catalog::new(
        vec![
            obj("meta", 110, &[50], Some("file.bin")),
            obj("other", 101, &[60], None),
        ],
        64,
    );
    assert_eq!(assert_exact(&catalog, &t, 2), RetrievalCertification::ExactFallbackSparse);
}

#[test]
fn uncapped_positive_candidates_certify_exact_content_top_k() {
    let t = obj("target", 100, &[3, 7], None);
    let catalog = Catalog::new(
        vec![
            obj("a", 90, &[3, 13], None),
            obj("b", 98, &[7, 17], None),
            obj("c", 100, &[99], None),
        ],
        64,
    );
    let got = catalog.select_indexed_certified(&t, 2);
    assert_eq!(got.certification, RetrievalCertification::IndexedExact);
    assert_eq!(got.stats.positive_candidates, 2);
    assert_eq!(got.ids, catalog.select_exact(&t, 2));
}

#[test]
fn capped_popular_hash_must_fallback_even_when_k_candidates_exist() {
    let t = obj("target", 100, &[42], None);
    let catalog = Catalog::new(
        vec![
            obj("far", 1, &[42], None),
            obj("medium", 50, &[42], None),
            obj("closest", 99, &[42], None),
        ],
        1,
    );
    assert_ne!(catalog.select_indexed(&t, 1).0, catalog.select_exact(&t, 1));
    assert_eq!(assert_exact(&catalog, &t, 1), RetrievalCertification::ExactFallbackCapped);
}

#[test]
fn zero_budget_is_exact_without_scan() {
    let t = obj("target", 100, &[42], None);
    let catalog = Catalog::new(vec![obj("x", 100, &[42], None)], 0);
    let got = catalog.select_indexed_certified(&t, 0);
    assert!(got.ids.is_empty());
    assert_eq!(got.certification, RetrievalCertification::IndexedExact);
}

#[test]
fn empty_short_and_repeated_data_obey_exact_oracle() {
    let t = obj("target", 0, &[], None);
    let catalog = Catalog::new(
        vec![
            obj("empty", 0, &[], None),
            obj("short", 3, &descriptor(b"abc"), None),
            obj("repeated", 32, &descriptor(&[7; 32]), Some("same")),
        ],
        64,
    );
    for k in 0..=5 {
        assert_exact(&catalog, &t, k);
    }
}

#[test]
fn deterministic_adversarial_property_matrix() {
    for seed in 1..=35u64 {
        let objs: Vec<Object> = (0..28u64)
            .map(|i| {
                let data = xorshift_bytes(seed ^ (i * 17 + 1), 24 + (i as usize * 31) % 180);
                let one_hash = [seed % 5 + 1];
                let mut o = obj(
                    &format!("obj-{i:02}"),
                    data.len() as u64,
                    if i % 7 == 0 { &[] } else if i % 3 == 0 { &one_hash } else { &[] },
                    if i % 4 == 0 { Some("same") } else { None },
                );
                if i % 7 != 0 && i % 3 != 0 {
                    o.descriptor = descriptor(&data);
                }
                o.version = (i % 10) as i64;
                o.offset = Some(i * 4096);
                o
            })
            .collect();
        let t = objs[(seed as usize) % objs.len()].clone();
        for cap in [0, 1, 2, 4, 64] {
            let catalog = Catalog::new(objs.clone(), cap);
            for k in [0, 1, 2, 4, 8, 28, 40] {
                assert_exact(&catalog, &t, k);
            }
        }
    }
}
