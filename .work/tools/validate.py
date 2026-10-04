"""Check documentation integrity. This does not validate scientific claims."""

import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "definitely-stable/Shift-lab"
errors = []


def check(condition, message):
    if not condition:
        errors.append(message)


required = [
    "README.md", ".work/README.md", ".work/charter.md", ".work/protocol.md",
    ".work/corpus-and-baselines.md", ".work/ci-plan.md", ".work/hypotheses.md",
    ".work/roadmap.md", ".work/research/report-audit.md",
    ".work/research/literature-review.md", ".work/research/lab-practices.md",
    ".work/templates/experiment.md", ".work/templates/evidence.md",
    ".work/issues/index.json", ".work/research/baseline-availability.json",
    ".work/research/claim-matrix.md",
]
for name in required:
    check((ROOT / name).is_file(), f"Missing required file: {name}")

documents = [ROOT / "README.md", *sorted((ROOT / ".work").rglob("*.md"))]
for path in documents:
    if not path.is_file():
        continue
    content = path.read_text(encoding="utf-8")
    name = path.relative_to(ROOT)
    check("\ufffd" not in content, f"Encoding replacement character: {name}")
    check("\ue200" not in content, f"Unresolved internal citation marker: {name}")
    for match in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", content):
        link = match.group(1).strip().strip("<>")
        parsed = urlsplit(link)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        target = (path.parent / unquote(parsed.path)).resolve()
        check(target.is_relative_to(ROOT), f"Link outside repository: {name}: {link}")
        check(target.exists(), f"Broken local link: {name}: {link}")

registry = json.loads((ROOT / ".work/issues/index.json").read_text(encoding="utf-8"))
check(registry["schema"] == "delsk.issue-index.v1", "Unexpected issue registry schema")
check(registry["repository"] == REPOSITORY, "Unexpected repository")
entries = registry["issues"]
by_id = {entry["id"]: entry for entry in entries}
check(len(by_id) == len(entries), "Duplicate issue ID")
check(set(by_id) == {f"DELSK-{n:03d}" for n in range(14)}, "Incomplete foundation backlog")
numbers = []
for entry in entries:
    ident = entry["id"]
    number = entry["number"]
    check(type(number) is int and number > 0, f"Unpublished issue: {ident}")
    numbers.append(number)
    expected = f"https://github.com/{REPOSITORY}/issues/{number}"
    check(entry["url"] == expected, f"Issue URL/number mismatch: {ident}")
    check(entry["priority"] in {"P0", "P1", "P2"}, f"Bad priority: {ident}")
    check(entry["title"].startswith(f"[{ident}] "), f"Title/ID mismatch: {ident}")
    body = ROOT / entry["body_path"]
    check(body.resolve().is_relative_to(ROOT), f"Unsafe body path: {ident}")
    check(body.is_file(), f"Missing issue body: {ident}")
    if body.is_file():
        content = body.read_text(encoding="utf-8")
        check(content.startswith(f"# {ident} "), f"Body/ID mismatch: {ident}")
        for heading in ("## Вопрос / результат", "## Шаги", "## Acceptance / evidence", "## CI и ресурсы"):
            check(heading in content, f"Missing issue section: {ident}: {heading}")
    for dependency in entry["depends_on"]:
        check(dependency in by_id, f"Unknown dependency: {ident} -> {dependency}")
check(len(set(numbers)) == len(numbers), "Duplicate GitHub issue number")


def visit(ident, stack, complete):
    if ident in stack:
        errors.append(f"Dependency cycle: {' -> '.join((*stack, ident))}")
        return
    if ident in complete or ident not in by_id:
        return
    for dependency in by_id[ident]["depends_on"]:
        visit(dependency, (*stack, ident), complete)
    complete.add(ident)


complete = set()
for ident in by_id:
    visit(ident, (), complete)

# Schema delsk.baseline-availability.v1 is fixed here, not read from the payload:
# changing a field or an enum value needs a new schema version.
AVAILABILITY_ENUMS = {
    "provenance": {"AUTHOR", "REIMPLEMENTED", "PROXY", "UNAVAILABLE"},
    "paper_fidelity": {"UNKNOWN", "KNOWN_DEVIATIONS", "NOT_APPLICABLE"},
    "license_status": {"CLEAR", "UNRESOLVED", "CONFLICT", "NOT_APPLICABLE"},
    "data_status": {"AVAILABLE", "PARTIAL", "WITHHELD", "UNKNOWN", "NOT_APPLICABLE"},
    "reproduction_status": {"NOT_ATTEMPTED", "PENDING", "BLOCKED", "VERIFIED"},
    "comparator_readiness": {"NEEDS_ADAPTER", "BLOCKED", "NOT_A_COMPARATOR", "NOT_APPLICABLE"},
}
ACCESS_LEVELS = {"FULL_TEXT", "AUTHOR_MANUSCRIPT", "ABSTRACT_ONLY", "METADATA_ONLY"}
WORK_KEYS = {"title", "venue", "url", "access"}
ARTIFACT_KEYS = {"label", "url", "commit", "project_license", "notes", *AVAILABILITY_ENUMS}

availability = json.loads((ROOT / ".work/research/baseline-availability.json").read_text(encoding="utf-8"))
check(availability.get("schema") == "delsk.baseline-availability.v1", "Unexpected baseline availability schema")
fields = availability.get("fields", {})
check(set(fields) == set(AVAILABILITY_ENUMS), "Baseline availability fields differ from schema v1")
for field, values in AVAILABILITY_ENUMS.items():
    documented = {value.strip() for value in fields.get(field, "").split(" — ")[0].split("|")}
    check(documented == values, f"Documented enum differs from schema v1: {field}")
seen = set()
for entry in availability.get("entries", []):
    ident = entry.get("id")
    check(ident and ident not in seen, f"Missing or duplicate baseline availability ID: {ident}")
    seen.add(ident)
    work = entry.get("work", {})
    check(WORK_KEYS <= set(work) <= WORK_KEYS | {"doi"}, f"Bad work keys: {ident}")
    check(work.get("access") in ACCESS_LEVELS, f"Bad access: {ident}: {work.get('access')}")
    artifacts = entry.get("artifacts") or []
    check(artifacts, f"No artifacts: {ident}")
    for artifact in artifacts:
        keys = set(artifact)
        check(ARTIFACT_KEYS <= keys <= ARTIFACT_KEYS | {"evidence"}, f"Bad artifact keys: {ident}: {sorted(keys ^ ARTIFACT_KEYS)}")
        for field, values in AVAILABILITY_ENUMS.items():
            check(artifact.get(field) in values, f"Bad {field}: {ident}: {artifact.get(field)}")
        if artifact.get("reproduction_status") == "VERIFIED":
            check("/actions/runs/" in (artifact.get("evidence") or ""), f"VERIFIED without Actions run: {ident}")
        if artifact.get("provenance") == "UNAVAILABLE":
            check(artifact.get("commit") is None, f"UNAVAILABLE artifact with commit: {ident}")
            check(artifact.get("reproduction_status") == "NOT_ATTEMPTED", f"Reproduction of UNAVAILABLE artifact: {ident}")
        else:
            commit = artifact.get("commit") or ""
            check(re.fullmatch(r"[0-9a-f]{40}", commit) and commit in (artifact.get("url") or ""), f"Unpinned artifact: {ident}")
        if artifact.get("license_status") == "CLEAR":
            check(artifact.get("project_license"), f"CLEAR license without project_license: {ident}")

if errors:
    print("\n".join(errors), file=sys.stderr)
    sys.exit(1)
print(f"PASS: {len(documents)} Markdown documents, {len(entries)} published issue mappings, local links and dependency DAG.")
print("Scope: documentation integrity only; no Delsk algorithm, benchmark or scientific gate was tested.")
