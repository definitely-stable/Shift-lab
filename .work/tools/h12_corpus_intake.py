#!/usr/bin/env python3
"""H12-B0 corpus intake safety gate. DISCOVERY ONLY; cannot authorize measurement."""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

SCHEMA = "delsk.h12b.discovery.v1"
STAGE = "DISCOVERY_ONLY_NOT_FROZEN"
EXPOSED_FAMILIES = frozenset({"zstd", "zlib", "curl", "libpng", "sqlite", "bzip2"})
REQUIRED_MODALITIES = ("application-binary", "non-code-large-object")
LICENSE_PENDING = {"MIT_REVIEW_REQUIRED", "MIXED_MEMBER_REVIEW_REQUIRED"}
ROOT_KEYS = {"schema", "stage", "entries", "unmet_modalities"}
ENTRY_KEYS = {"family", "upstream", "modality", "license_review", "candidate_status"}
REPO_RE = re.compile(r"https://github[.]com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
FAMILY_RE = re.compile(r"[a-z][a-z0-9-]{1,40}")

class IntakeError(ValueError):
    pass

def fail(message: str) -> None:
    raise IntakeError(message)

def load_no_duplicate_keys(path: Path) -> dict:
    def strict_pairs(pairs):
        d = {}
        for k, v in pairs:
            if k in d:
                fail(f"duplicate JSON key: {k}")
            d[k] = v
        return d
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=strict_pairs)

def validate_discovery(doc: dict) -> dict:
    if not isinstance(doc, dict) or set(doc) != ROOT_KEYS:
        fail("intake top-level schema must be closed")
    if doc["schema"] != SCHEMA or doc["stage"] != STAGE:
        fail("only unsealed discovery intake accepted: NOT a freeze")
    if doc["unmet_modalities"] != list(REQUIRED_MODALITIES):
        fail("cannot imply non-source modalities were tested")
    entries = doc["entries"]
    if not isinstance(entries, list) or len(entries) < 3:
        fail("need at least three distinct discovery candidates")
    previous = ""
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != ENTRY_KEYS:
            fail("candidate must have closed schema; no release locks/quality field")
        family = entry["family"]
        if not isinstance(family, str) or not FAMILY_RE.fullmatch(family):
            fail("family must have canonical lowercase stable ID")
        if family in EXPOSED_FAMILIES:
            fail(f"exposed E1 or development family is not fresh: {family}")
        if family <= previous:
            fail("candidate families must be sorted with no duplicates")
        previous = family
        if not isinstance(entry["upstream"], str) or not REPO_RE.fullmatch(entry["upstream"]):
            fail("upstream must be a canonical GitHub repository URL")
        if entry["modality"] != "source-release":
            fail("unknown or falsely asserted independent data modality")
        if entry["license_review"] not in LICENSE_PENDING:
            fail("member-level license review has NOT happened")
        if entry["candidate_status"] != "NEEDS_SHA_AND_LICENSE_REVIEW":
            fail("candidate cannot be tagged ready or measured")
    return {
        "schema": "delsk.h12b.intake-check.v1",
        "status": "DISCOVERY_ONLY_NOT_READY_FOR_MEASUREMENT",
        "candidate_families": [item["family"] for item in entries],
        "unmet_modalities": list(REQUIRED_MODALITIES),
        "all_family_ids_disjoint_from_exposed": True,
        "release_tags_pinned": False,
        "archive_sha256_verified": False,
        "license_review_complete": False,
        "natural_corpus_frozen": False,
        "h12_decision_authorized": False,
    }

def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        raise SystemExit("usage: h12_corpus_intake.py PATH")
    print(json.dumps(validate_discovery(load_no_duplicate_keys(Path(argv[0]))), sort_keys=True, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
