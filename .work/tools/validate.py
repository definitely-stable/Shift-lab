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

availability = json.loads((ROOT / ".work/research/baseline-availability.json").read_text(encoding="utf-8"))
check(availability["schema"] == "delsk.baseline-availability.v1", "Unexpected baseline availability schema")
allowed = {
    field: {value.strip() for value in spec.split("—")[0].split("|")}
    for field, spec in availability["fields"].items()
}
seen = set()
for entry in availability["entries"]:
    ident = entry["id"]
    check(ident not in seen, f"Duplicate baseline availability ID: {ident}")
    seen.add(ident)
    for artifact in entry["artifacts"]:
        for field, values in allowed.items():
            check(artifact.get(field) in values, f"Bad {field}: {ident}: {artifact.get(field)}")
        verified = artifact["reproduction_status"] == "VERIFIED"
        check(not verified or "/actions/runs/" in artifact.get("evidence", ""), f"VERIFIED without Actions run: {ident}")
        check(artifact["provenance"] == "UNAVAILABLE" or artifact.get("commit"), f"Unpinned artifact: {ident}")

if errors:
    print("\n".join(errors), file=sys.stderr)
    sys.exit(1)
print(f"PASS: {len(documents)} Markdown documents, {len(entries)} published issue mappings, local links and dependency DAG.")
print("Scope: documentation integrity only; no Delsk algorithm, benchmark or scientific gate was tested.")
