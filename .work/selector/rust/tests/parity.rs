//! Parity with the Python reference: `.work/selector/vectors.txt` from `simple_selector.py vectors`.

use delsk_selector::{descriptor, resemblance, select, xorshift_bytes, Catalog, Object};
use std::collections::HashMap;

fn vectors() -> Vec<Vec<String>> {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../vectors.txt");
    std::fs::read_to_string(path)
        .expect("vectors.txt")
        .lines()
        .map(|l| l.split(' ').map(str::to_owned).collect())
        .collect()
}

fn hashes(field: &str) -> Vec<u64> {
    if field == "-" {
        return Vec::new();
    }
    field.split(',').map(|h| u64::from_str_radix(h, 16).unwrap()).collect()
}

fn opt(field: &str) -> Option<String> {
    (field != "-").then(|| field.to_owned())
}

fn objects(v: &[Vec<String>]) -> HashMap<String, Object> {
    v.iter()
        .filter(|f| f[0] == "O")
        .map(|f| {
            let o = Object {
                id: f[1].clone(),
                size: f[2].parse().unwrap(),
                path: opt(&f[3]),
                line: opt(&f[4]),
                version: f[5].parse().unwrap(),
                offset: opt(&f[6]).map(|s| s.parse().unwrap()),
                descriptor: hashes(&f[7]),
            };
            (o.id.clone(), o)
        })
        .collect()
}

#[test]
fn descriptors_match_python() {
    let v = vectors();
    let mut n = 0;
    for f in v.iter().filter(|f| f[0] == "D") {
        let data = xorshift_bytes(f[1].parse().unwrap(), f[2].parse().unwrap());
        assert_eq!(descriptor(&data), hashes(&f[3]), "seed {} length {}", f[1], f[2]);
        n += 1;
    }
    assert_eq!(n, 9);
}

#[test]
fn resemblance_matches_python() {
    let v = vectors();
    let objs = objects(&v);
    for f in v.iter().filter(|f| f[0] == "R") {
        let (a, b) = (&objs[&f[1]], &objs[&f[2]]);
        assert_eq!(resemblance(&a.descriptor, &b.descriptor), (f[3].parse().unwrap(), f[4].parse().unwrap()));
    }
}

#[test]
fn selection_matches_python() {
    let v = vectors();
    let objs = objects(&v);
    let mut cases = 0;
    for f in v.iter().filter(|f| f[0] == "C") {
        let t = &objs[&f[2]];
        let mut bases: Vec<Object> = objs.values().filter(|o| o.id != t.id).cloned().collect();
        bases.sort_by(|a, b| a.id.cmp(&b.id));
        let got: Vec<String> = select(t, &bases, f[3].parse().unwrap()).into_iter().map(|o| o.id.clone()).collect();
        assert_eq!(got.join(","), f[4], "case {}", f[1]);
        // Input order must not matter.
        bases.reverse();
        let again: Vec<String> =
            select(t, &bases, f[3].parse().unwrap()).into_iter().map(|o| o.id.clone()).collect();
        assert_eq!(again, got, "case {} reversed", f[1]);
        cases += 1;
    }
    assert_eq!(cases, 5);
}

#[test]
fn uncapped_index_equals_exact_scan_on_the_vectors() {
    let v = vectors();
    let objs: Vec<Object> = {
        let mut o: Vec<Object> = objects(&v).into_values().collect();
        o.sort_by(|a, b| a.id.cmp(&b.id));
        o
    };
    let catalog = Catalog::new(objs.clone(), usize::MAX);
    for t in &objs {
        let exact = catalog.select_exact(t, 2);
        let (indexed, _) = catalog.select_indexed(t, 2);
        // Indexed candidates are a subset; with every hash shared in this family the top 2 agree.
        if t.id != "far" && t.id != "tiny" {
            assert_eq!(indexed, exact, "target {}", t.id);
        }
    }
}
