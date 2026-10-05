"""DELSK-003 Slice B: oracle runner and codec conformance of delsk.oracle-contract.v1.

    python3 oracle_run.py conformance TOOLS_JSON OUT_JSON CANDIDATE_JSON   C01-C14 on synthetic inputs (contract 10.3)
    python3 oracle_run.py synthetic OUT_DIR                                deterministic smoke corpus: locks + store
    python3 oracle_run.py run PHASE TOOLS_JSON CONFORMANCE_JSON STORE EVIDENCE_DIR PRIVATE_DIR [LOCK_DIR]

`run` measures every expected pair (delta codec) and every query's standalone representation (standalone codec) of
the bound candidate lock in canonical order, verifying each input object against the lock before every call, and
appends one full row per task to PRIVATE_DIR (fsync per row). A SIGTERM, an exception or the workload wall limit
turns every task not yet written into a not_run row. It never prints or publishes a cost: sealing, target rows and the
evaluation are oracle_eval.py finalize. Phase smoke accepts only synthetic locks (LOCK_DIR); phase pilot only the
frozen natural locks, a conformance PASS and a workflow_dispatch event.

Linux only: process groups, pidfd, setrlimit, wait4. Codec calls get only LC_ALL=C, stdin /dev/null, a fresh call
directory, RLIMIT_AS/RLIMIT_FSIZE, and SIGKILL of the whole process group at the wall limit or on any exit.
"""

import datetime as dt
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import select
import shutil
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import time
import zlib

TOOLS = Path(__file__).resolve().parent
WORK = TOOLS.parent
ORACLE = WORK / "oracle"
sys.path.insert(0, str(TOOLS))
import manifests as m  # noqa: E402
from oracle_build import CODE_FILES, code_manifest  # noqa: E402,F401

CODEC_LOCK, FREEZE, GOLDEN = ORACLE / "codec-lock.json", ORACLE / "freeze.json", ORACLE / "conformance.json"
INVOKE_ENV = {"LC_ALL": "C"}
NAMES = {"base": "base.bin", "target": "target.bin", "patch": "patch.bin", "payload": "payload.bin",
         "decoded": "decoded.bin"}
ENOMEM = re.compile(rb"(?i)cannot allocate memory|out of memory|not enough memory|allocation error")
LIMITS = {"smoke": {"workload_wall_seconds": 240, "work_dir_bytes": 256 << 20, "workload_address_space_bytes": 8 << 30},
          "pilot": {"workload_wall_seconds": 22 * 60, "work_dir_bytes": 1280 << 20,
                    "workload_address_space_bytes": 8 << 30}}
SYNTHETIC = ("delsk.oracle.synthetic-candidates.v1", "delsk.oracle.synthetic-corpus.v1")
PAIR_FIELDS = ("encode_exit", "encode_signal", "decode_exit", "decode_signal", "patch_payload_bytes", "patch_sha256",
               "wrapper_bytes", "base_reference_bytes", "codec_metadata_bytes", "delta_total_bytes", "decoded_bytes",
               "decoded_sha256", "encode_wall_ns", "decode_wall_ns", "encode_peak_rss_bytes", "decode_peak_rss_bytes")
SOLO_FIELDS = ("compress_exit", "compress_signal", "decompress_exit", "decompress_signal", "compressed_payload_bytes",
               "compressed_sha256", "compressed_wrapper_bytes", "compressed_total_bytes", "decoded_sha256",
               "compress_wall_ns", "decompress_wall_ns")


class RunError(Exception):
    pass


class Abort(Exception):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def wrapper(n):
    k = 1
    while n >= 128:
        n >>= 7
        k += 1
    return 1 + k


# --- one codec process ------------------------------------------------------------------------------------------------

def _killpg(pid):
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def invoke(argv, cwd, wall_seconds, address_space, file_cap):
    """Run one codec process; never raises on codec failure. The leader is reaped only after SIGKILL of its process
    group, so no descendant outlives the call and the group ID cannot be reused in between."""
    import resource

    def limits():
        resource.setrlimit(resource.RLIMIT_AS, (address_space, address_space))
        resource.setrlimit(resource.RLIMIT_FSIZE, (file_cap, file_cap))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    with tempfile.TemporaryFile() as err:  # read only to classify allocation failures; never stored or printed
        started = time.monotonic_ns()
        proc = subprocess.Popen(argv, cwd=cwd, env=dict(INVOKE_ENV), stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=err, start_new_session=True, preexec_fn=limits,
                                close_fds=True)
        pidfd = os.pidfd_open(proc.pid)
        try:
            ready = select.select([pidfd], [], [], wall_seconds)[0]
            wall = time.monotonic_ns() - started
        finally:
            os.close(pidfd)
            _killpg(proc.pid)
            _, status, usage = os.wait4(proc.pid, 0)
            proc.returncode = os.waitstatus_to_exitcode(status)
        err.seek(max(0, err.seek(0, os.SEEK_END) - 65536))
        tail = err.read()
    code = proc.returncode
    return {"exit": code if code >= 0 else None, "signal": -code if code < 0 else None, "wall_ns": wall,
            "peak_rss_bytes": usage.ru_maxrss * 1024, "timed_out": not ready and code == -signal.SIGKILL,
            "enomem": bool(ENOMEM.search(tail))}


def argv_for(template, exe, names=NAMES):
    """Locked argv with whole-token placeholders replaced; an unknown placeholder is a KeyError (fail closed)."""
    return [str(exe) if t == "{exe}" else names[t[1:-1]] if t.startswith("{") and t.endswith("}") else t
            for t in template]


def call_dir(work, files):
    """Fresh call directory holding exactly the call's inputs."""
    d = Path(tempfile.mkdtemp(prefix="call-", dir=work))
    for name, data in files.items():
        fd = os.open(d / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(data)
    return d


def read_regular(path, limit):
    """Bytes of a regular file of at most `limit` bytes; None when missing, not regular or larger."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            return None
        data = f.read(limit + 1)
    return data if len(data) <= limit else None


def encode_failure(call, output, capped=False):
    """(status, phase, error_class) of a failed encode-side call, or None (contract section 5)."""
    if call["timed_out"]:
        return "timeout", "encode", "wall_timeout"
    if call["signal"] == signal.SIGXFSZ or (capped and call["exit"] != 0):  # a codec ignoring SIGXFSZ gets EFBIG
        return "resource_limit", "encode", "work_dir"
    if call["exit"] not in (0, None) and call["enomem"]:
        # ponytail: RLIMIT_AS shows up as the codec's own allocation error text; a codec that dies on an unchecked
        # NULL instead is recorded as codec_error/signal. Both are bounded +inf, so the oracle value is the same.
        return "resource_limit", "encode", "address_space"
    if call["signal"] is not None:
        return "codec_error", "encode", "signal"
    if call["exit"] != 0:
        return "codec_error", "encode", "nonzero_exit"
    if output is None:
        return "codec_error", "encode", "missing_output"
    return None


def decode_failure(call, decoded, target):
    """(status, phase, error_class) of a decode-side call on the encoder's own output, or None. Anything but a wall
    timeout is a correctness failure (decode_mismatch, contract A11), never a bounded codec_error."""
    if call["timed_out"]:
        return "timeout", "decode", "wall_timeout"
    if call["signal"] is not None:
        return "decode_mismatch", "decode", "signal"
    if call["exit"] != 0:
        return "decode_mismatch", "decode", "nonzero_exit"
    if decoded is None:
        return "decode_mismatch", "decode", "missing_output"
    if len(decoded) != len(target):
        return "decode_mismatch", "decode", "length_mismatch"
    if decoded != target:
        return "decode_mismatch", "decode", "bytes_mismatch"
    if sha256(decoded) != sha256(target):
        return "decode_mismatch", "decode", "sha256_mismatch"
    return None


def roundtrip(codec, inputs, encode_out, decode_inputs, target, work, file_cap, names=NAMES):
    """Encode then decode under the codec lock. Returns (failure or None, encoded bytes or None, encode call,
    decode call or None, decoded bytes)."""
    lim, entry = codec["limits"], codec["entry"]
    d = call_dir(work, {names[k]: v for k, v in inputs.items()})
    try:
        enc = invoke(argv_for(entry["encode_argv"], codec["exe"], names), d, lim["encode_wall_seconds"],
                     lim["address_space_bytes"], file_cap)
        encoded = read_regular(d / names[encode_out], file_cap)
        capped = any(f.stat().st_size >= file_cap for f in d.iterdir() if f.is_file())
        failure = encode_failure(enc, encoded, capped)
    finally:
        shutil.rmtree(d)
    if failure:
        return failure, None, enc, None, None
    d = call_dir(work, {**{names[k]: v for k, v in decode_inputs.items()}, names[encode_out]: encoded})
    try:
        dec = invoke(argv_for(entry["decode_argv"], codec["exe"], names), d, lim["decode_wall_seconds"],
                     lim["address_space_bytes"], file_cap)
        decoded = read_regular(d / names["decoded"], len(target))
    finally:
        shutil.rmtree(d)
    return decode_failure(dec, decoded, target), encoded, enc, dec, decoded


def measure_delta(codec, base, target, work, file_cap):
    """(status, phase, error_class, fields, patch) of one ordered pair; cost fields only for ok."""
    failure, patch, enc, dec, decoded = roundtrip(codec, {"base": base, "target": target}, "patch", {"base": base},
                                                  target, work, file_cap)
    fields = dict.fromkeys(PAIR_FIELDS)
    fields.update(encode_exit=enc["exit"], encode_signal=enc["signal"], encode_wall_ns=enc["wall_ns"],
                  encode_peak_rss_bytes=enc["peak_rss_bytes"])
    if dec is not None:
        fields.update(decode_exit=dec["exit"], decode_signal=dec["signal"], decode_wall_ns=dec["wall_ns"],
                      decode_peak_rss_bytes=dec["peak_rss_bytes"])
    if failure:
        return (*failure, fields, None)
    p = len(patch)
    fields.update(patch_payload_bytes=p, patch_sha256=sha256(patch), wrapper_bytes=wrapper(p), base_reference_bytes=32,
                  codec_metadata_bytes=0, delta_total_bytes=p + wrapper(p) + 32, decoded_bytes=len(decoded),
                  decoded_sha256=sha256(decoded))
    return "ok", None, None, fields, patch


def measure_standalone(codec, target, work, file_cap):
    """(status, phase, error_class, fields, frame) of one standalone representation; cost fields only for ok."""
    failure, frame, enc, dec, decoded = roundtrip(codec, {"target": target}, "payload", {}, target, work, file_cap)
    fields = dict.fromkeys(SOLO_FIELDS)
    fields.update(compress_exit=enc["exit"], compress_signal=enc["signal"], compress_wall_ns=enc["wall_ns"])
    if dec is not None:
        fields.update(decompress_exit=dec["exit"], decompress_signal=dec["signal"], decompress_wall_ns=dec["wall_ns"])
    if failure:
        return (*failure, fields, None)
    z = len(frame)
    fields.update(compressed_payload_bytes=z, compressed_sha256=sha256(frame), compressed_wrapper_bytes=wrapper(z),
                  compressed_total_bytes=z + wrapper(z), decoded_sha256=sha256(decoded))
    return "ok", None, None, fields, frame


# --- tools, locks and identity ------------------------------------------------------------------------------------------

TOOLS_KEYS = {"schema", "codec_lock_sha256", "compiler", "make", "codecs", "code", "source"}
TOOLS_CODEC_KEYS = {"codec_id", "archive_url", "archive_bytes", "archive_sha256", "archive_root", "archive_path",
                    "extracted_files", "extracted_tree_sha256", "skipped_members", "build_argv", "build_cwd",
                    "build_env", "executable", "executable_bytes", "executable_sha256", "self_report"}


def lock_provenance(entry):
    """The build-record fields that the frozen codec lock fixes for one role."""
    src, build = entry["source"], entry["build"]
    return {"codec_id": entry["codec_id"], "archive_url": src["archive_url"], "archive_bytes": src["archive_bytes"],
            "archive_sha256": src["archive_sha256"], "archive_root": src["archive_root"],
            "archive_path": f"archives/{src['archive_root']}.tar.gz", "build_argv": build["argv"],
            "build_cwd": build["cwd"], "build_env": build["env"],
            "executable": f"src/{build['cwd']}/{build['executable']}"}


def load_tools(tools_path, lock_data):
    """Codecs of a builder record. Every recipe field must equal the frozen codec lock role by role, the record must
    come from the current oracle code, and every executable is re-hashed, so a substituted binary is refused."""
    tools_path = Path(tools_path).resolve()
    tools = m.loads_strict(tools_path.read_bytes())
    if set(tools) != TOOLS_KEYS or tools["schema"] != "delsk.oracle.tools.v1" or \
            tools["codec_lock_sha256"] != sha256(lock_data):
        raise RunError("tools.json is not a build record of the committed codec lock")
    if tools["code"] != code_manifest():
        raise RunError("tools.json was built by other oracle code than this checkout")
    lock = m.loads_strict(lock_data)
    codecs = {}
    for role in ("delta", "standalone"):
        rec, entry = tools["codecs"][role], lock["codecs"][role]
        pinned = lock_provenance(entry)
        if set(rec) != TOOLS_CODEC_KEYS or {k: rec[k] for k in pinned} != pinned:
            raise RunError(f"{role}: build record differs from the frozen codec lock recipe")
        raw = tools_path.parent / rec["executable"]
        exe = raw.resolve()
        if raw.is_symlink() or not exe.is_relative_to(tools_path.parent) or not exe.is_file():
            raise RunError(f"{role}: executable outside the build directory or not a regular file")
        if rec["codec_id"] != entry["codec_id"] or sha256(exe.read_bytes()) != rec["executable_sha256"]:
            raise RunError(f"{role}: executable differs from its build record")
        codecs[role] = {"entry": entry, "exe": exe, "limits": entry["limits"], "record": rec}
    return tools, codecs


def load_locks(phase, lock_dir, freeze):
    """(candidate bytes, corpus bytes) for the phase: synthetic locks for smoke, the frozen natural locks for pilot."""
    natural = WORK / "corpus" / "e1" / "candidate-lock.json", WORK / "corpus" / "pilot-v1" / "corpus-lock.json.gz"
    if phase == "smoke":
        if lock_dir is None:
            raise RunError("smoke needs the synthetic lock directory")
        candidate, corpus = ((Path(lock_dir) / n).read_bytes() for n in ("candidate-lock.json", "corpus-lock.json"))
        if sha256(candidate) == freeze["bindings"]["candidate_lock_sha256"] or \
                [m.loads_strict(candidate)["schema"], m.loads_strict(corpus)["schema"]] != list(SYNTHETIC):
            raise RunError("smoke runs only on synthetic locks, never on the natural C_t")
        # Schema relabelling is not proof of synthetic inputs. No frozen natural object may be measured in smoke.
        natural_corpus = gzip.decompress(natural[1].read_bytes())
        if sha256(natural_corpus) != freeze["bindings"]["corpus_lock_sha256"]:
            raise RunError("smoke boundary needs the frozen natural corpus binding")
        natural_ids = {o["object_id"] for o in m.loads_strict(natural_corpus)["occurrences"]}
        if any(o["object_id"] in natural_ids for o in m.loads_strict(corpus)["occurrences"]):
            raise RunError("smoke refuses objects from the frozen natural corpus")
        return candidate, corpus
    candidate, corpus = natural[0].read_bytes(), gzip.decompress(natural[1].read_bytes())
    if (sha256(candidate), sha256(corpus)) != (freeze["bindings"]["candidate_lock_sha256"],
                                               freeze["bindings"]["corpus_lock_sha256"]):
        raise RunError("natural locks differ from the oracle freeze bindings")
    return candidate, corpus


def universe(candidate, corpus):
    """Queries with lock facts; canonical order = (target, base object) by ASCII (contract section 4)."""
    occ = {o["occurrence_id"]: o for o in corpus["occurrences"]}
    out = []
    for q in sorted(candidate["queries"], key=lambda q: q["target"]):
        o = occ[q["target"]]
        bases = [{"object_id": b["object_id"], "representative": b["representative"],
                  "bytes": occ[b["representative"]]["bytes"]} for b in sorted(q["bases"], key=lambda b: b["object_id"])]
        if any(occ[b["representative"]]["object_id"] != b["object_id"] for b in bases):
            raise RunError("candidate lock: base representative is another object")
        out.append({"target": q["target"], "status": q["status"], "object_id": o["object_id"], "bytes": o["bytes"],
                    "split": o["split"], "bases": bases})
    return out


def github(env):
    def num(key):
        value = env.get(key, "")
        return int(value) if value.isdigit() else 0
    return {"repository": env.get("GITHUB_REPOSITORY", ""), "run_id": num("GITHUB_RUN_ID"),
            "run_attempt": num("GITHUB_RUN_ATTEMPT"), "sha": env.get("GITHUB_SHA", ""),
            "workflow_ref": env.get("GITHUB_WORKFLOW_REF", ""), "workflow_sha": env.get("GITHUB_WORKFLOW_SHA", "")}


def check_conformance(doc, codecs, lock_data):
    """Strict shape and binding of a conformance record; a PASS must carry the committed golden digests."""
    checks = doc.get("checks")
    if set(doc) != {"schema", "codec_lock_sha256", "executables", "inputs_sha256", "golden", "checks", "verdict"} or \
            doc["schema"] != "delsk.oracle.conformance.v1" or doc["codec_lock_sha256"] != sha256(lock_data) or \
            type(checks) is not dict or sorted(checks) != [f"C{i:02d}" for i in range(1, 15)] or \
            any(type(c) is not dict or set(c) != {"status", "detail"} or c["status"] not in ("PASS", "FAIL", "CANDIDATE")
                for c in checks.values()):
        raise RunError("conformance.json is not a closed C01-C14 record of the committed codec lock")
    if doc["executables"] != {role: c["record"]["executable_sha256"] for role, c in codecs.items()}:
        raise RunError("conformance.json does not belong to these executables")
    statuses = {c["status"] for c in checks.values()}
    verdict = "FAIL" if "FAIL" in statuses else "CANDIDATE" if "CANDIDATE" in statuses else "PASS"
    if doc["verdict"] != verdict:
        raise RunError("conformance.json verdict differs from its checks")
    if verdict == "PASS":
        golden = m.loads_strict(GOLDEN.read_bytes())
        if (golden["codec_lock_sha256"], golden["inputs_sha256"], golden["golden"]) != \
                (sha256(lock_data), doc["inputs_sha256"], doc["golden"]):
            raise RunError("conformance PASS without the committed golden digests")


def prepare(phase, tools_path, conformance_path, lock_dir=None, env=os.environ):
    """Everything a run needs before the first codec call; raises RunError on any binding problem."""
    if phase not in LIMITS:
        raise RunError(f"phase {phase!r} is not run by this slice")
    lock_data, freeze_data = CODEC_LOCK.read_bytes(), FREEZE.read_bytes()
    freeze = m.loads_strict(freeze_data)
    if sha256(lock_data) != freeze["bindings"]["codec_lock_sha256"]:
        raise RunError("committed codec lock differs from the oracle freeze")
    tools, codecs = load_tools(tools_path, lock_data)
    conformance = m.loads_strict(Path(conformance_path).read_bytes())
    if type(conformance) is not dict:
        raise RunError("conformance.json is not an object")
    check_conformance(conformance, codecs, lock_data)
    gh = github(env)
    if phase == "pilot":
        if conformance["verdict"] != "PASS" or env.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
            raise RunError("pilot needs conformance PASS and a workflow_dispatch run")
        # Fail closed before any natural call: a record proves nothing unless these exact executables pass now.
        fresh, _ = conformance_record(tools_path, env=env)
        if fresh["verdict"] != "PASS" or m.canonical_bytes(fresh) != m.canonical_bytes(conformance):
            raise RunError("pilot refused: C01-C14 re-run on these executables does not reproduce the PASS record")
        # Slice C0 infrastructure: a direct CLI invocation cannot bypass dispatch/admission/attempt retention.
        from oracle_pilot import validate_gate, PilotError
        try:
            validate_gate(env, tools_path, conformance_path)
        except (PilotError, OSError, ValueError, KeyError) as error:
            raise RunError("pilot infrastructure gate refused") from None
    if not (re.fullmatch(r"[0-9a-f]{40}", gh["sha"]) and gh["sha"] == gh["workflow_sha"]):
        raise RunError("GITHUB_SHA must be a commit equal to GITHUB_WORKFLOW_SHA")
    candidate_data, corpus_data = load_locks(phase, lock_dir, freeze)
    candidate, corpus = m.loads_strict(candidate_data), m.loads_strict(corpus_data)
    if candidate["corpus_lock_sha256"] != sha256(corpus_data):
        raise RunError("candidate lock binds another corpus lock")
    lock = m.loads_strict(lock_data)
    queries = universe(candidate, corpus)
    if candidate["planned_pairs_per_codec"] != sum(len(q["bases"]) for q in queries if q["status"] == "near_duplicate"):
        raise RunError("candidate lock: planned_pairs_per_codec differs from its queries")
    identity = {"contract_id": "delsk.oracle-contract.v1", "contract_freeze_sha256": sha256(freeze_data),
                "codec_lock_sha256": sha256(lock_data),
                **{role: {k: lock["codecs"][role][k] for k in ("codec_id", "options_sha256")}
                   for role in ("delta", "standalone")},
                "corpus_lock_sha256": sha256(corpus_data), "candidate_lock_sha256": sha256(candidate_data),
                "measured_source_sha": gh["sha"],
                "oracle_code_sha256": m.digest(tools["code"]),
                "phase": phase, "sealed_splits": ["evaluation"]}
    copies = {"codec-lock.json": lock_data, "tools.json": Path(tools_path).read_bytes(),
              "conformance.json": Path(conformance_path).read_bytes()}
    if phase == "smoke":
        copies.update({"candidate-lock.json": candidate_data, "corpus-lock.json": corpus_data})
    verdict = "PASS" if conformance["verdict"] == "PASS" else "FAIL"
    builds = [{"codec_id": c["record"]["codec_id"], "archive_sha256": c["record"]["archive_sha256"],
               "build_argv_sha256": m.digest(c["record"]["build_argv"]),
               "executable_sha256": c["record"]["executable_sha256"],
               "self_report_sha256": sha256(c["record"]["self_report"].encode("utf-8")), "conformance": verdict}
              for c in codecs.values()]
    return {"phase": phase, "identity": identity, "identity_sha256": m.digest(identity), "codecs": codecs,
            "queries": queries, "copies": copies, "builds": builds, "github": gh,
            "compiler": tools["compiler"]["version"], "limits": LIMITS[phase],
            "tools_path": str(Path(tools_path).resolve()), "conformance_path": str(Path(conformance_path).resolve())}


# --- the run -----------------------------------------------------------------------------------------------------------

class Rows:
    """Append-only JSONL with one write and one fsync per row; a fresh file only (stale output is never reused)."""

    def __init__(self, path):
        self.fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND, 0o600)
        self.rows = 0  # durable rows, counted inside the masked window together with the write itself

    def write(self, row):
        data = (json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        # An abort signal is delivered between rows, never inside one: a row is whole or absent. A signal held back
        # here is delivered when the mask is restored, after the row is durable and counted.
        blocked = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
        try:
            while data:
                data = data[os.write(self.fd, data):]
            os.fsync(self.fd)
            self.rows += 1
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, blocked)

    def close(self):
        os.close(self.fd)


def load_object(store, object_id, size):
    """Object bytes from the store, only when length and SHA-256 equal the lock (independent input check)."""
    data = read_regular(Path(store) / object_id, size)
    return data if data is not None and len(data) == size and sha256(data) == object_id else None


def pair_row(ctx, q, b, status, phase, error_class, fields):
    ident = ctx["identity"]
    codec = ident["delta"]
    return {"schema": "delsk.oracle.pair.v1", "measurement_identity_sha256": ctx["identity_sha256"],
            "measured_source_sha": ident["measured_source_sha"], "corpus_lock_sha256": ident["corpus_lock_sha256"],
            "candidate_lock_sha256": ident["candidate_lock_sha256"], **codec,
            "pair_id": m.digest(["delsk.oracle.pair.v1", codec["codec_id"], q["target"], b["object_id"]]),
            "target_occurrence_id": q["target"], "target_object_id": q["object_id"], "target_bytes": q["bytes"],
            "base_object_id": b["object_id"], "base_representative": b["representative"], "base_bytes": b["bytes"],
            "split": q["split"], "status": status, "failure_phase": phase, "error_class": error_class,
            **(fields if fields is not None else dict.fromkeys(PAIR_FIELDS))}


def solo_row(ctx, q, status, phase, error_class, fields):
    ident = ctx["identity"]
    return {"schema": "delsk.oracle.standalone.v1", "measurement_identity_sha256": ctx["identity_sha256"],
            "measured_source_sha": ident["measured_source_sha"], "corpus_lock_sha256": ident["corpus_lock_sha256"],
            "candidate_lock_sha256": ident["candidate_lock_sha256"], **ident["standalone"],
            "target_occurrence_id": q["target"], "target_object_id": q["object_id"], "target_bytes": q["bytes"],
            "split": q["split"], "query_status": q["status"], "raw_total_bytes": q["bytes"] + wrapper(q["bytes"]),
            "status": status, "failure_phase": phase, "error_class": error_class,
            **(fields if fields is not None else dict.fromkeys(SOLO_FIELDS))}


def tasks_of(ctx):
    """All tasks in canonical order: pairs (target, base), then one standalone task per query."""
    return [("pair", q, b) for q in ctx["queries"] if q["status"] == "near_duplicate" for b in q["bases"]] + \
        [("solo", q, None) for q in ctx["queries"]]


def run_task(ctx, task, store, work, file_cap):
    kind, q, b = task
    target = load_object(store, q["object_id"], q["bytes"])
    if kind == "solo":
        if target is None:
            return solo_row(ctx, q, "input_integrity", "materialize", "target_integrity", None)
        return solo_row(ctx, q, *measure_standalone(ctx["codecs"]["standalone"], target, work, file_cap)[:4])
    if target is None:
        return pair_row(ctx, q, b, "input_integrity", "materialize", "target_integrity", None)
    base = load_object(store, b["object_id"], b["bytes"])
    if base is None:
        return pair_row(ctx, q, b, "input_integrity", "materialize", "base_integrity", None)
    return pair_row(ctx, q, b, *measure_delta(ctx["codecs"]["delta"], base, target, work, file_cap)[:4])


def not_run(ctx, task):
    kind, q, b = task
    if kind == "solo":
        return solo_row(ctx, q, "not_run", "runner", "runner_abort", None)
    return pair_row(ctx, q, b, "not_run", "runner", "runner_abort", None)


def _terminate(signum, frame):
    raise Abort("SIGTERM")


def environment(ctx, env):
    cpu = "unavailable"
    try:
        cpu = next((line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                    if line.startswith("model name")), cpu)
    except OSError:
        pass
    return {"compiler": ctx["compiler"], "cpu_model": cpu, "image_os": env.get("ImageOS", "unavailable"),
            "image_version": env.get("ImageVersion", "unavailable"), "kernel": platform.release(),
            "logical_cpus": os.cpu_count() or 0, "python": platform.python_version()}


def execute(ctx, store, evidence, private, env=os.environ, codec_limits=None, file_cap=None):
    """Measure every task and write run.json; returns the workload status. codec_limits/file_cap override the lock
    limits only in fault-injection tests."""
    import resource

    if ctx["phase"] == "pilot":
        from oracle_pilot import validate_gate
        validate_gate(env, ctx["tools_path"], ctx["conformance_path"], store)
        _, current = load_tools(ctx["tools_path"], CODEC_LOCK.read_bytes())
        if any(current[role]["record"] != ctx["codecs"][role]["record"] for role in current):
            raise RunError("pilot codec changed after conformance")

    evidence, private = Path(evidence), Path(private)
    for d in (evidence, private):
        d.mkdir(parents=True, exist_ok=True)
        if any(d.iterdir()):
            raise RunError(f"{d} is not empty: stale evidence is never reused")
    if codec_limits:
        for codec in ctx["codecs"].values():
            codec["limits"] = {**codec["limits"], **codec_limits}
    cap = ctx["limits"]["workload_address_space_bytes"]
    resource.setrlimit(resource.RLIMIT_AS, (cap, resource.getrlimit(resource.RLIMIT_AS)[1]))  # soft: codec calls lower it
    file_cap = file_cap or ctx["limits"]["work_dir_bytes"]
    for name, data in ctx["copies"].items():
        (evidence / name).write_bytes(data)
    started, clock = dt.datetime.now(dt.timezone.utc), time.monotonic()
    deadline = clock + ctx["limits"]["workload_wall_seconds"]

    def write_run(status):
        run = {"schema": "delsk.oracle.run.v1", "cache": "none", "codec_builds": ctx["builds"],
               "started_at": started.isoformat(), "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
               "environment": environment(ctx, env),
               "evidence": [{"path": n, "bytes": len(d), "sha256": sha256(d)} for n, d in sorted(ctx["copies"].items())],
               "github": ctx["github"], "limits": ctx["limits"], "measurement_identity": ctx["identity"],
               "measurement_identity_sha256": ctx["identity_sha256"], "timing_scope": "descriptive",
               "wall_seconds": int(time.monotonic() - clock), "workload_status": status}
        tmp = evidence / ".run.json.tmp"
        tmp.write_bytes(m.canonical_bytes(run))
        os.replace(tmp, evidence / "run.json")

    write_run("failed")  # pessimistic record first: a SIGKILLed runner still leaves identity and partial rows
    work = Path(tempfile.mkdtemp(prefix="oracle-calls-"))
    sinks = {"pair": Rows(private / "pairs.full.jsonl"), "solo": Rows(private / "standalone.full.jsonl")}
    tasks, done, status = tasks_of(ctx), 0, "ok"
    previous = signal.signal(signal.SIGTERM, _terminate)
    try:
        for task in tasks:
            if time.monotonic() > deadline:
                status = "limit_exceeded"
                raise Abort("workload wall limit")
            sinks[task[0]].write(run_task(ctx, task, store, work, file_cap))
            done += 1
    except BaseException as error:  # SIGTERM, KeyboardInterrupt, a bug: every unwritten task becomes not_run
        # Tasks are written in order, one row each: the durable rows, not the loop counter, say how many are done
        # (an abort can land after a row is durable but before `done += 1`).
        done = sum(sink.rows for sink in sinks.values())
        if status == "ok":
            status = "failed"
        print(f"runner aborted after {done} of {len(tasks)} tasks: {type(error).__name__}", file=sys.stderr)
        for task in tasks[done:]:
            sinks[task[0]].write(not_run(ctx, task))
    finally:
        signal.signal(signal.SIGTERM, previous)
        for sink in sinks.values():
            sink.close()
        shutil.rmtree(work, ignore_errors=True)
        write_run(status)
    print(f"runner: {done} of {len(tasks)} tasks measured, workload {status}")
    return status


# --- deterministic synthetic inputs -------------------------------------------------------------------------------------

def stream(label, n):
    """Deterministic pseudo-random bytes (SHA-256 counter mode); independent of Python and library versions."""
    out = bytearray()
    i = 0
    while len(out) < n:
        out += hashlib.sha256(f"delsk.oracle.synthetic.v1:{label}:{i}".encode()).digest()
        i += 1
    return bytes(out[:n])


def edited(data, label, every=100):
    """data with len(data)//every bytes flipped at deterministic positions (about 1% edits)."""
    buf, r = bytearray(data), stream(label, 4 * (len(data) // every))
    for k in range(len(data) // every):
        buf[int.from_bytes(r[4 * k:4 * k + 4], "big") % len(buf)] ^= 0xA5
    return bytes(buf)


def stored_gzip(payload):
    """A valid gzip member with stored deflate blocks: deterministic without any zlib compressor."""
    chunks = [payload[i:i + 65535] for i in range(0, len(payload), 65535)] or [b""]
    body = b"".join(bytes([i == len(chunks) - 1]) + struct.pack("<HH", len(c), len(c) ^ 0xFFFF) + c
                    for i, c in enumerate(chunks))
    return b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff" + body + struct.pack("<II", zlib.crc32(payload), len(payload))


def conformance_inputs():
    """C02-C09 (base, target) pairs of contract section 10.3."""
    base = stream("base", 64 << 10)
    return {"C02": (base, edited(base, "c02")), "C03": (stream("c03-base", 64 << 10), stream("c03-target", 64 << 10)),
            "C04": (base, b""), "C05": (b"", stream("c05-target", 64 << 10)), "C06": (b"", b""),
            "C07": (base, b"\x5a"), "C08": (base, base), "C09": (base, stored_gzip(stream("c09", 48 << 10)))}


# --- codec conformance C01-C14 (contract section 10.3) ------------------------------------------------------------------

def capture(argv, cwd):
    out = subprocess.run(argv, cwd=cwd, env=dict(INVOKE_ENV), stdin=subprocess.DEVNULL, capture_output=True,
                         timeout=60)
    return out.returncode, (out.stdout + out.stderr).decode("utf-8", "replace")


def vcdiff_windows(patch):
    """Window indicators of a VCDIFF stream whose header indicator is 0 (5-byte header); ValueError if malformed."""
    pos = 5

    def varint():
        nonlocal pos
        value = 0
        for _ in range(10):
            byte = patch[pos]
            pos += 1
            value = (value << 7) | (byte & 0x7F)
            if not byte & 0x80:
                return value
        raise ValueError("varint")

    windows = []
    try:
        while pos < len(patch):
            indicator = patch[pos]
            pos += 1
            if indicator & 0x03:
                varint(), varint()
            length = varint()  # read before advancing: `pos += varint()` would add to the stale position
            pos += length
            windows.append(indicator)
    except IndexError:
        raise ValueError("truncated window") from None
    if pos != len(patch):
        raise ValueError("window overruns the stream")
    return windows


def zstd_frame_error(frame, size):
    """None when frame is one Zstandard frame with content size == size, no checksum, no dictionary."""
    if frame[:4] != b"\x28\xb5\x2f\xfd" or len(frame) < 6:
        return "magic"
    fhd = frame[4]
    fcs_flag, single = fhd >> 6, (fhd >> 5) & 1
    if fhd & 0x04:
        return "checksum flag set"
    if fhd & 0x03:
        return "dictionary ID present"
    fcs_len = (1 if single else 0, 2, 4, 8)[fcs_flag]
    if not fcs_len:
        return "content size absent"
    pos = 5 + (0 if single else 1)
    if int.from_bytes(frame[pos:pos + fcs_len], "little") + (256 if fcs_len == 2 else 0) != size:
        return "content size differs"
    pos += fcs_len
    while True:
        if pos + 3 > len(frame):
            return "truncated block"
        header = int.from_bytes(frame[pos:pos + 3], "little")
        pos += 3
        if (header >> 1) & 3 == 3:
            return "reserved block type"
        pos += 1 if (header >> 1) & 3 == 1 else header >> 3
        if header & 1:
            break
    return None if pos == len(frame) else "bytes after the frame"


def conformance_record(tools_path, golden_path=GOLDEN, env=os.environ):
    """(conformance.json, candidate golden record) for the built codecs; synthetic data only."""
    lock_data = CODEC_LOCK.read_bytes()
    tools, codecs = load_tools(tools_path, lock_data)
    lock = m.loads_strict(lock_data)
    root = Path(tools_path).resolve().parent
    work = Path(tempfile.mkdtemp(prefix="oracle-conformance-"))
    checks, cap = {}, 64 << 20

    def put(cid, ok, detail):
        checks[cid] = {"status": "PASS" if ok else "FAIL", "detail": detail}

    try:
        xd, zs = codecs["delta"], codecs["standalone"]
        archives = True
        for c in codecs.values():
            data = read_regular(root / c["record"]["archive_path"], 16 << 20) or b""
            archives &= (len(data), sha256(data)) == (c["entry"]["source"]["archive_bytes"],
                                                      c["entry"]["source"]["archive_sha256"])
        _, config = capture([str(xd["exe"]), "config"], work)
        _, help_text = capture([str(xd["exe"]), "-h"], work)
        _, version = capture([str(zs["exe"]), "-vV"], work)
        lines = set(config.splitlines())
        flags = {"EXTERNAL_COMPRESSION=0", "SECONDARY_LZMA=0", "SECONDARY_DJW=1", "SECONDARY_FGK=0", "XD3_DEBUG=0",
                 "REGRESSION_TEST=1", "XD3_POSIX=1", "XD3_USE_LARGEFILE64=1", "XD3_USE_LARGESIZET=1"}
        no_armor = "armor" not in (config + help_text).lower() and b"blake3" not in xd["exe"].read_bytes().lower()
        zstd_ok = "v1.5.7" in version and "*** supports: zstd" in version.splitlines()
        put("C01", archives and flags <= lines and "3.2.1" in config and no_armor and zstd_ok,
            f"archives {archives}, xdelta3 flags {sorted(flags - lines) or 'ok'}, armor absent {no_armor}, "
            f"zstd 1.5.7 zstd-only {zstd_ok}")
        golden, inputs, patches, frames = {}, {}, {}, {}
        for cid, (base, target) in conformance_inputs().items():
            inputs[cid] = {"base": sha256(base), "target": sha256(target)}
            d = measure_delta(xd, base, target, work, cap)
            s = measure_standalone(zs, target, work, cap)
            patches[cid], frames[cid] = d[4], s[4]
            put(cid, d[0] == "ok" and s[0] == "ok", f"delta {d[0]}, standalone {s[0]}")
            if d[0] == "ok" and s[0] == "ok":
                golden[cid] = {"patch_sha256": sha256(d[4]), "frame_sha256": sha256(s[4])}
        good = {c: p for c, p in patches.items() if p is not None}
        header = [c for c, p in good.items() if p[:4] != b"\xd6\xc3\xc4\x00" or len(p) < 5 or p[4] & 0x07]
        put("C10", len(good) == 8 and not header, f"bad VCDIFF header or indicator: {header}")
        adler, frame_errors = [], {}
        for cid, patch in good.items():
            d = Path(tempfile.mkdtemp(dir=work))
            (d / "patch.bin").write_bytes(patch)
            code, text = capture([str(xd["exe"]), "printhdrs", "patch.bin"], d)
            try:
                windows = vcdiff_windows(patch)
            except ValueError:
                windows = None
            if code != 0 or "VCD_ADLER32" in text or windows is None or any(w & 0x04 for w in windows) or \
                    text.count("VCDIFF window number") != len(windows):
                adler.append(cid)
        for cid, frame in frames.items():
            if frame is not None and (error := zstd_frame_error(frame, len(conformance_inputs()[cid][1]))):
                frame_errors[cid] = error
        put("C11", len(good) == 8 and not adler and len([f for f in frames.values() if f]) == 8 and not frame_errors,
            f"window checksum or printhdrs mismatch: {adler}; zstd frame: {frame_errors}")
        other = {"base": "src-other.dat", "target": "tgt-other.dat", "patch": "out-other.vcdiff",
                 "payload": "out-other.zst", "decoded": "dec-other.dat"}
        moved = []
        for cid, (base, target) in conformance_inputs().items():
            sub = Path(tempfile.mkdtemp(prefix="elsewhere-", dir=work))
            d = roundtrip(xd, {"base": base, "target": target}, "patch", {"base": base}, target, sub, cap, other)
            s = roundtrip(zs, {"target": target}, "payload", {}, target, sub, cap, other)
            if (d[1], s[1]) != (patches[cid], frames[cid]) or d[0] or s[0]:
                moved.append(cid)
        put("C12", not moved, f"output changed with cwd or file names: {moved}")
        hostile = {"XDELTA": "-S lzma -A=leak -0", "ZSTD_CLEVEL": "1", "ZSTD_NBTHREADS": "4", "CFLAGS": "-O0",
                   "CPPFLAGS": "-DXD3_ARMOR=1", "LDFLAGS": "-s"}
        saved = {k: os.environ.get(k) for k in hostile}
        os.environ.update(hostile)
        try:
            base, target = conformance_inputs()["C02"]
            d = measure_delta(xd, base, target, work, cap)
            s = measure_standalone(zs, target, work, cap)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k)
                else:
                    os.environ[k] = v
        forbidden = set(lock["invocation"]["forbidden_env"]) <= set(hostile)
        put("C13", forbidden and (d[4], s[4]) == (patches["C02"], frames["C02"]),
            f"forbidden env covered {forbidden}; outputs unchanged {(d[4], s[4]) == (patches['C02'], frames['C02'])}")
        candidate = {"schema": "delsk.oracle.conformance-golden.v1", "contract_id": "delsk.oracle-contract.v1",
                     "codec_lock_sha256": sha256(lock_data), "inputs_sha256": inputs, "golden": golden,
                     "observed_in": {k: env.get(f"GITHUB_{k.upper()}") for k in ("repository", "run_id",
                                                                                  "run_attempt", "sha")}}
        if len(golden) != 8:
            put("C14", False, "golden digests incomplete: a roundtrip failed")
        elif not Path(golden_path).exists():
            checks["C14"] = {"status": "CANDIDATE", "detail": "no committed golden record; candidate written"}
        else:
            committed = m.loads_strict(Path(golden_path).read_bytes())
            same = (committed["codec_lock_sha256"], committed["inputs_sha256"], committed["golden"]) == \
                (sha256(lock_data), inputs, golden)
            put("C14", same, "golden digests equal the committed record" if same else
                f"differs from the committed record: {sorted(c for c in golden if committed['golden'].get(c) != golden[c])}")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    statuses = {c["status"] for c in checks.values()}
    verdict = "FAIL" if "FAIL" in statuses or len(checks) != 14 else "CANDIDATE" if "CANDIDATE" in statuses else "PASS"
    doc = {"schema": "delsk.oracle.conformance.v1", "codec_lock_sha256": sha256(lock_data),
           "executables": {role: c["record"]["executable_sha256"] for role, c in codecs.items()},
           "inputs_sha256": inputs, "golden": golden, "checks": dict(sorted(checks.items())), "verdict": verdict}
    return doc, candidate


# --- synthetic smoke corpus ---------------------------------------------------------------------------------------------

def synthetic(out):
    """Deterministic synthetic locks and object store for the PR smoke run (< 2 MiB, no natural data). Covers every
    split (evaluation is sealed), identity-only and empty-C_t queries, empty and one-byte targets, an empty base, a base
    equal to its target and a gzip-magic target."""
    out = Path(out)
    store = out / "store"
    store.mkdir(parents=True)
    a = stream("syn-a", 64 << 10)
    objects = {"a": a, "a1": edited(a, "syn-a1"), "a2": a[:20000] + stream("syn-ins", 3000) + a[20000:],
               "c": stream("syn-c", 32 << 10), "e": stream("syn-e", 40 << 10), "empty": b"", "one": b"\x01",
               "gz": stored_gzip(a[:30000])}
    objects.update(c1=edited(objects["c"], "syn-c1"), e1=edited(objects["e"], "syn-e1"),
                   e2=objects["e"][::-1][:20000])
    ids = {k: sha256(v) for k, v in objects.items()}
    for k, v in objects.items():
        (store / ids[k]).write_bytes(v)

    def occ(label):
        return m.digest(["delsk.oracle.synthetic.v1", "occurrence", label])

    split = {"a": "development", "a1": "development", "a2": "development", "c": "calibration", "c1": "calibration",
             "e": "evaluation", "e1": "evaluation", "e2": "evaluation", "empty": "development", "one": "development",
             "gz": "development", "a-dup": "development", "a-eq": "development", "lonely": "development"}
    obj_of = {**{k: k for k in objects}, "a-dup": "a", "a-eq": "a", "lonely": "c1"}
    occurrences = [{"occurrence_id": occ(label), "object_id": ids[o], "bytes": len(objects[o]), "split": split[label],
                    "family_id": "syn", "track": "synthetic"} for label, o in obj_of.items()]
    plan = {"a1": ["a", "a2", "empty"], "a2": ["a"], "c1": ["c"], "e1": ["e", "a"], "e2": ["e"], "empty": ["a"],
            "one": ["a"], "gz": ["a", "a1"], "a-eq": ["a", "a1"], "lonely": [], "a-dup": None}
    queries = []
    for label, bases in plan.items():
        refs = sorted(({"category": "synthetic", "object_id": ids[b], "representative": occ(b)} for b in bases or ()),
                      key=lambda b: b["object_id"])
        queries.append({"target": occ(label), "status": "identity_only" if bases is None else "near_duplicate",
                        "bases": refs, "candidate_count": len(refs),
                        "candidate_list_sha256": m.digest([b["object_id"] for b in refs]),
                        "duplicate_of": occ("a") if bases is None else None})
    corpus = {"schema": SYNTHETIC[1], "occurrences": sorted(occurrences, key=lambda o: o["occurrence_id"])}
    corpus_data = m.canonical_bytes(corpus)
    candidate = {"schema": SYNTHETIC[0], "corpus_lock_sha256": sha256(corpus_data),
                 "planned_pairs_per_codec": sum(len(q["bases"]) for q in queries),
                 "queries": sorted(queries, key=lambda q: q["target"])}
    (out / "corpus-lock.json").write_bytes(corpus_data)
    (out / "candidate-lock.json").write_bytes(m.canonical_bytes(candidate))
    return candidate


def main(argv, env=os.environ):
    command, args = (argv[0], argv[1:]) if argv else (None, [])
    try:
        if command == "conformance" and len(args) == 3:
            doc, candidate = conformance_record(args[0], env=env)
            Path(args[1]).write_bytes(m.canonical_bytes(doc))
            Path(args[2]).write_bytes(m.canonical_bytes(candidate))
            for cid, c in doc["checks"].items():
                print(f"{cid} {c['status']}: {c['detail']}")
            print(f"conformance verdict: {doc['verdict']}")
            return 0 if doc["verdict"] == "PASS" else 1
        if command == "synthetic" and len(args) == 1:
            candidate = synthetic(args[0])
            print(f"synthetic corpus: {len(candidate['queries'])} queries, {candidate['planned_pairs_per_codec']} pairs")
            return 0
        if command == "run" and len(args) in (6, 7):
            phase, tools_path, conformance_path, store, evidence, private, *lock_dir = args
            ctx = prepare(phase, tools_path, conformance_path, lock_dir[0] if lock_dir else None, env)
            if phase == "pilot":
                from oracle_pilot import validate_gate
                validate_gate(env, tools_path, conformance_path, store)
            return 0 if execute(ctx, store, evidence, private, env) == "ok" else 1
    except (RunError, KeyError, ValueError, OSError) as error:
        print(f"REFUSED: {type(error).__name__}: {str(error)[:300]}", file=sys.stderr)
        return 1
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
