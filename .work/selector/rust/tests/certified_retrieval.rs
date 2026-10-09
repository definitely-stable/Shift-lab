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
fn repeated_object_ids_do_not_falsely_certify_k_distinct_candidates() {
    // A duplicate logical ID invalidates the snapshot; never certify.
    let t = obj("target", 100, &[42], None);
    let catalog = Catalog::new(
        vec![
            obj("duplicate", 99, &[42], None),
            obj("duplicate", 98, &[42], None),
            obj("zero-overlap", 100, &[99], None),
        ],
        64,
    );
    let got = catalog.select_indexed_certified(&t, 2);
    assert_eq!(got.stats.positive_candidates, 1);
    assert_eq!(got.certification, RetrievalCertification::ExactFallbackInvalidInput);
    assert_eq!(got.ids, catalog.select_exact(&t, 2));
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
fn extreme_version_rank_has_total_order_without_signed_overflow() {
    // Python's -version is unbounded, while i64::MIN negation overflows in Rust.
    // Reverse(i64) preserves descending semantics for the *entire* i64 domain.
    let t = obj("target", 100, &[42], Some("same"));
    let mut oldest = obj("oldest", 100, &[42], Some("same"));
    let mut ordinary = obj("ordinary", 100, &[42], Some("same"));
    let mut latest = obj("latest", 100, &[42], Some("same"));
    oldest.version = i64::MIN;
    ordinary.version = 0;
    latest.version = i64::MAX;
    let objects = vec![oldest, ordinary, latest];
    let ordered = delsk_selector::metadata_order(&t, &objects);
    let ids: Vec<_> = ordered.iter().map(|o| o.id.as_str()).collect();
    assert_eq!(ids, ["latest", "ordinary", "oldest"]);
    for cap in [0, 1, 64] {
        let catalog = Catalog::new(objects.clone(), cap);
        for k in 0..=5 {
            assert_exact(&catalog, &t, k);
        }
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


#[test]
fn duplicate_object_ids_with_k_positive_candidates_never_certify() {
    let t = obj("target", 100, &[42], None);
    let catalog = Catalog::new(
        vec![
            obj("same", 100, &[42], None),
            obj("same", 99, &[42], None),
            obj("other", 98, &[42], None),
            obj("zero", 101, &[99], None),
        ],
        usize::MAX,
    );
    // Duplicate IDs invalidate certification even when positive candidates >= K.
    for k in 1..=4 {
        assert_eq!(
            assert_exact(&catalog, &t, k),
            RetrievalCertification::ExactFallbackInvalidInput
        );
    }
}

#[test]
fn malformed_descriptors_never_certify_even_with_positive_overlap() {
    let target = obj("target", 100, &[10, 20, 30], None);
    let valid = obj("valid", 101, &[10, 20, 40], None);
    let malformed = [
        vec![20, 10],                   // unsorted
        vec![10, 10, 20],               // duplicates
        (0..=8u64).collect::<Vec<_>>(), // >8
    ];
    for hashes in malformed {
        let invalid_catalog = Catalog::new(
            vec![valid.clone(), obj("broken", 101, &hashes, None)],
            usize::MAX,
        );
        for k in [1, 2, 3, 4] {
            assert_eq!(
                assert_exact(&invalid_catalog, &target, k),
                RetrievalCertification::ExactFallbackInvalidInput
            );
        }
        let valid_catalog = Catalog::new(
            vec![valid.clone(), obj("other", 103, &[20, 50], None)],
            usize::MAX,
        );
        let invalid_target = obj("target", 101, &hashes, None);
        for k in [1, 2, 3, 4] {
            assert_eq!(
                assert_exact(&valid_catalog, &invalid_target, k),
                RetrievalCertification::ExactFallbackInvalidInput
            );
        }
    }
}

#[test]
fn immutable_catalog_snapshot_exposes_only_read_only_objects() {
    let target = obj("target", 101, &[42], None);
    let mut original = vec![
        obj("a", 100, &[42], None),
        obj("b", 102, &[42], None),
        obj("c", 101, &[99], None),
    ];
    let catalog = Catalog::new(original.clone(), usize::MAX);
    let before = assert_exact(&catalog, &target, 1);
    assert_eq!(before, RetrievalCertification::IndexedExact);
    assert_eq!(catalog.objects().len(), original.len());
    original[1].descriptor = vec![99];
    original[2].descriptor = vec![42];
    assert_eq!(before, assert_exact(&catalog, &target, 1));
    assert_eq!(catalog.objects()[1].descriptor, vec![42]);
    let rebuilt = Catalog::new(original, usize::MAX);
    assert_exact(&rebuilt, &target, 1);
    assert_ne!(rebuilt.select_exact(&target, 1), catalog.select_exact(&target, 1));
}
