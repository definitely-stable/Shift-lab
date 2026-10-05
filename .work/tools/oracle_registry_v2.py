"""DELSK-003A C1-A: registry mechanics of the frozen provenance/G1 contract delsk.oracle-contract.v3.

v3 (.work/oracle/contract-v3.md) is the v2 text with substitutions; the registered-attempt model and the module names
(_v2) are those of v2, which was superseded before activation. Implements sections 3, 5 and 6 over immutable data:
canonical genesis and entries, closed schemas (.work/oracle/schemas-v3.json), hash chain, sequence, run-key
uniqueness, registry head,
level-1 witness prefix (rollback), stale-head primitive, physical branch form, science_identity and transition records,
and the external-checkpoint prefix rule (section 13.2). Stdlib only, no network, no Git writes, no natural bytes.

C1-B adds authority profiles: PRODUCTION is exactly the constants of section 5.1 and the frozen schemas; SMOKE is the
synthetic real-GitHub registry of activation item 8 (own ref, own workflow, domain-separated genesis digest), so a smoke
registry can never validate as the production registry and vice versa. Git transport lives in oracle_registry_git.py.

Not part of the v1 code manifest (oracle_eval.CODE_FILES), so it never changes a science identity (contract section 6).
Series state machine, classification and G1 live in oracle_g1_v2.py.
"""
from dataclasses import dataclass
import copy
import json
from types import MappingProxyType

import oracle_eval as ev

G1_CONTRACT = 'delsk.oracle-contract.v3'
MEASUREMENT_CONTRACT = 'delsk.oracle-contract.v1'
# Authority constants (contract 5.1): normative, never parameters, environment or CLI.
REPOSITORY = 'definitely-stable/Shift-lab'
REGISTRY_REMOTE = 'https://github.com/definitely-stable/Shift-lab.git'
REGISTRY_REF = 'refs/heads/delsk/registry-v3'
PROVIDER_API = 'https://api.github.com'
WORKFLOW_PATH = '.github/workflows/oracle-pilot.yml'
JOBS = ('register', 'measure')
SOURCE_REF = 'refs/heads/main'
RESULTS_ROOT = '.work/results/DELSK-003-ORACLE-V3/'
TRANSITION_FILE = '.work/oracle/series-transition.json'
AUTHORITY = MappingProxyType({'repository': REPOSITORY, 'registry_remote': REGISTRY_REMOTE,
                              'registry_ref': REGISTRY_REF, 'provider_api': PROVIDER_API,
                              'results_root': RESULTS_ROOT})

GENESIS_FILE, ENTRIES_FILE = 'genesis.json', 'entries.jsonl'
ENTRY_SCHEMA = 'delsk.oracle.registry-entry.v1'
SCIENCE_SCHEMA = 'delsk.oracle.science-identity.v1'
_SCHEMAS = ev.parse_doc((ev.ORACLE / 'schemas-v3.json').read_bytes())
# SHA-256 of the frozen contracts. The v3 digest (freeze-v3.json) is an authority constant of this contract generation;
# a future provenance contract gets a new constant rather than making this caller-selectable. The v2 freeze stays pinned
# as the base text of v3 (KAT gate) and is never a genesis binding.
MEASUREMENT_FREEZE_SHA256 = _SCHEMAS['$defs']['registry_genesis']['properties']['measurement_freeze_sha256']['const']
G1_FREEZE_SHA256 = 'bc1114821c7f1236190918ae45b34f8ab45daa3b4da58ad948b4b70ebedebf70'


@dataclass(frozen=True)
class Profile:
    """Registry authority profile. Only the two module constants below exist; neither is caller-configurable.

    schemas: schemas-v3 with this profile's genesis registry_ref, entry workflow_path and entry workflow_ref pattern.
    g1_freeze_sha256: the genesis binding that authoritative validation requires (contract 5.3)."""
    name: str
    registry_remote: str
    registry_ref: str
    workflow_path: str
    g1_freeze_sha256: str
    schemas: MappingProxyType


def _profile_schemas(registry_ref, workflow_path):
    """schemas-v3 with exactly three values replaced. Applied to the production values it reproduces the frozen
    schemas byte for byte (tested), so the derivation cannot weaken any other rule."""
    s = copy.deepcopy(_SCHEMAS)
    defs = s['$defs']
    defs['registry_genesis']['properties']['registry_ref']['const'] = registry_ref
    defs['registry_entry']['properties']['workflow_path']['const'] = workflow_path
    escaped = f'{REPOSITORY}/{workflow_path}'.replace('.', '\\.')
    defs['registry_entry']['properties']['workflow_ref']['pattern'] = (
        f'^{escaped}@refs/heads/[A-Za-z0-9][A-Za-z0-9._/-]{{0,199}}(?![\\s\\S])')
    return s


PRODUCTION = Profile('production', REGISTRY_REMOTE, REGISTRY_REF, WORKFLOW_PATH, G1_FREEZE_SHA256, _SCHEMAS)
SMOKE_REGISTRY_REF = 'refs/heads/delsk/registry-v3-smoke'
SMOKE_WORKFLOW_PATH = '.github/workflows/oracle-registry-smoke.yml'
SMOKE = Profile('smoke', REGISTRY_REMOTE, SMOKE_REGISTRY_REF, SMOKE_WORKFLOW_PATH,
                ev.hc({'schema': 'delsk.oracle.registry-smoke-domain.v1', 'g1_freeze_sha256': G1_FREEZE_SHA256}),
                _profile_schemas(SMOKE_REGISTRY_REF, SMOKE_WORKFLOW_PATH))
PROFILES = (PRODUCTION, SMOKE)


class RegistryInvalid(ev.EvalError):
    """Contract 5.6 item 1: the registry is permanently REGISTRY_INVALID. No repair inside v3."""


_PHYSICAL_PROOF = object()


@dataclass(frozen=True)
class PhysicalRegistry:
    """Opaque authoritative registry snapshot.

    Only authoritative_registry() can construct a usable instance: it first verifies the complete Git history shape
    (contract 5.2), parses canonical bytes and binds genesis to this contract's exact freeze-v3 digest. The snapshot
    stores immutable bytes so later callers cannot mutate the already-validated registry objects in place.
    """
    genesis_bytes: bytes
    entries_bytes: bytes
    _proof: object
    profile: Profile = PRODUCTION

    def __post_init__(self):
        require(self._proof is _PHYSICAL_PROOF, 'physical registry proof')


def require(ok, reason):
    if not ok:
        raise RegistryInvalid(reason)


def schema_errors(value, name, schemas=None):
    schemas = _SCHEMAS if schemas is None else schemas
    return ev.schema_errors(value, schemas['$defs'][name], schemas)


def canonical_value(value):
    """True when value is representable in canonical JSON v1 (ints in int64, NFC strings, ASCII keys, no floats)."""
    try:
        ev.compact(value)
        return True
    except (ev.EvalError, UnicodeEncodeError):
        return False


def valid(value, name, schemas=None):
    return canonical_value(value) and not schema_errors(value, name, schemas)


def without(doc, key):
    return {k: v for k, v in doc.items() if k != key}


def self_digest_ok(doc, key):
    return doc[key] == ev.hc(without(doc, key))


def run_key(doc):
    return doc['run_id'], doc['run_attempt']


# --- identities (contract 6) ------------------------------------------------------------------------------------------

def science_identity(mi):
    """si = measurement identity v1 without measured_source_sha, plus the schema tag."""
    return {**without(mi, 'measured_source_sha'), 'schema': SCIENCE_SCHEMA}


@dataclass(frozen=True)
class GitSnapshot:
    """Immutable view of Git at one pinned main_head_sha (contract 9.0). ancestors maps each known commit to its proper
    ancestors; identities maps a commit to its git_source measurement identity (absent = unresolvable). Production builds
    it from commit-addressed objects of the pinned snapshot; the core never reads a moving ref."""
    main_head_sha: str
    ancestors: MappingProxyType
    identities: MappingProxyType

    @classmethod
    def build(cls, main_head_sha, ancestors, identities):
        return cls(main_head_sha, MappingProxyType({c: frozenset(a) for c, a in ancestors.items()}),
                   MappingProxyType({c: ev.compact(mi) for c, mi in identities.items()}))

    def ancestor_or_equal(self, commit, descendant):
        return commit in self.ancestors and descendant in self.ancestors and (
            commit == descendant or commit in self.ancestors[descendant])

    def on_main(self, commit):
        return self.ancestor_or_equal(commit, self.main_head_sha)

    def identity(self, commit):
        text = self.identities.get(commit)
        return None if text is None else json.loads(text)


# --- genesis, entries, transitions ------------------------------------------------------------------------------------

def make_genesis(g1_freeze_sha256, profile=PRODUCTION):
    return {'schema': 'delsk.oracle.registry-genesis.v1', 'g1_contract': G1_CONTRACT,
            'measurement_contract': MEASUREMENT_CONTRACT,
            'measurement_freeze_sha256': MEASUREMENT_FREEZE_SHA256,
            'g1_freeze_sha256': g1_freeze_sha256, 'repository': REPOSITORY, 'registry_ref': profile.registry_ref}


def make_transition(phase, previous, new, reason, pull_request, merge_commit_sha):
    t = {'schema': 'delsk.oracle.series-transition.v1', 'g1_contract': G1_CONTRACT, 'phase': phase,
         'previous_science_identity_sha256': previous, 'new_science_identity_sha256': new, 'reason': reason,
         'change_review': {'pull_request': pull_request, 'merge_commit_sha': merge_commit_sha}}
    return {**t, 'transition_sha256': ev.hc(t)}


def make_entry(genesis, entries, *, run_id, run_attempt, measured_source_sha, workflow_ref, measurement_identity,
               transition=None, profile=PRODUCTION):
    """Next entry of a registry (contract 5.4). workflow_sha = measured_source_sha by construction."""
    e = {'schema': ENTRY_SCHEMA, 'sequence': len(entries) + 1,
         'previous_entry_sha256': entries[-1]['entry_sha256'] if entries else ev.hc(genesis),
         'g1_contract': G1_CONTRACT, 'repository': REPOSITORY, 'workflow_path': profile.workflow_path,
         'workflow_ref': workflow_ref, 'workflow_sha': measured_source_sha, 'measured_source_sha': measured_source_sha,
         'measurement_identity_sha256': ev.hc(measurement_identity),
         'science_identity_sha256': ev.hc(science_identity(measurement_identity)),
         'phase': measurement_identity['phase'], 'run_id': run_id, 'run_attempt': run_attempt, 'transition': transition}
    return {**e, 'entry_sha256': ev.hc(e)}


def parse_registry(genesis_bytes, entries_bytes):
    """genesis.json (canonical file form) and entries.jsonl (canonical JSONL) -> (genesis, entries). Malformed bytes,
    BOM, floats, duplicate keys or non-canonical serialization are REGISTRY_INVALID."""
    try:
        return ev.parse_doc(genesis_bytes), ev.parse_jsonl(entries_bytes)
    except (ev.EvalError, ValueError, UnicodeDecodeError) as error:
        raise RegistryInvalid(f'registry bytes are not canonical JSON: {type(error).__name__}') from None


def validate_physical(commits):
    """Contract 5.2 over the registry branch history, root first: [(parent_count, {path: bytes})]. Returns the head
    (genesis_bytes, entries_bytes). Merge commits, extra files, edits or more than one appended line per commit fail."""
    require(len(commits) >= 1, 'registry branch has no root commit')
    genesis_bytes = None
    entries_bytes = b''
    for n, (parents, files) in enumerate(commits):
        require(parents == (0 if n == 0 else 1), 'registry commit parent count')
        require(set(files) == {GENESIS_FILE, ENTRIES_FILE}, 'registry tree must be exactly genesis.json, entries.jsonl')
        if n == 0:
            genesis_bytes = files[GENESIS_FILE]
            require(files[ENTRIES_FILE] == b'', 'root commit entries.jsonl must be empty')
            continue
        require(files[GENESIS_FILE] == genesis_bytes, 'genesis.json changed')
        line = files[ENTRIES_FILE][len(entries_bytes):]
        require(files[ENTRIES_FILE].startswith(entries_bytes) and line.endswith(b'\n') and line.count(b'\n') == 1,
                'commit must append exactly one entry line')
        entries_bytes = files[ENTRIES_FILE]
    return genesis_bytes, entries_bytes


def authoritative_registry(commits, git, profile=PRODUCTION):
    """Composition boundary for production/runner code.

    The returned object cannot be obtained from a logically-valid final tree alone: the full registry branch history
    must first satisfy section 5.2, and genesis must bind to the exact frozen v3 contract (SMOKE: to its own
    domain-separated digest). Duplicate run keys remain section 5.6 item 2 and are intentionally checked by the caller
    so it can preserve REGISTRY_DUPLICATE semantics.
    """
    require(profile in PROFILES, 'unknown registry profile')
    genesis_bytes, entries_bytes = validate_physical(commits)
    genesis, entries = parse_registry(genesis_bytes, entries_bytes)
    validate(genesis, entries, git, profile.g1_freeze_sha256, profile)
    return PhysicalRegistry(genesis_bytes, entries_bytes, _PHYSICAL_PROOF, profile)


def physical_objects(snapshot):
    """Reparse immutable bytes from an authoritative registry snapshot."""
    require(type(snapshot) is PhysicalRegistry and snapshot._proof is _PHYSICAL_PROOF, 'authoritative registry required')
    return parse_registry(snapshot.genesis_bytes, snapshot.entries_bytes)


def validate(genesis, entries, git, g1_freeze_sha256=None, profile=None):
    """Contract 5.6 item 1 on parsed objects. Raises RegistryInvalid; returns the registry head. Production passes the
    SHA-256 of freeze-v3.json in the pinned main tree as g1_freeze_sha256; the test core passes None (contract 14).
    profile None = the frozen production schemas."""
    schemas = None if profile is None else profile.schemas
    require(type(entries) is list, 'entries must be a list')
    require(valid(genesis, 'registry_genesis', schemas), 'genesis not canonical or not by schema')
    require(g1_freeze_sha256 is None or genesis['g1_freeze_sha256'] == g1_freeze_sha256,
            'genesis g1_freeze_sha256 differs from freeze-v3')
    previous = ev.hc(genesis)
    for number, e in enumerate(entries, 1):
        where = f'line {number}'
        require(valid(e, 'registry_entry', schemas), f'{where}: not canonical or not by schema')
        require(e['sequence'] == number, f'{where}: sequence gap or repeat')
        require(e['previous_entry_sha256'] == previous, f'{where}: previous_entry_sha256 breaks the chain')
        require(self_digest_ok(e, 'entry_sha256'), f'{where}: entry_sha256 != Hc(entry)')
        source = e['measured_source_sha']
        require(e['workflow_sha'] == source, f'{where}: workflow_sha != measured_source_sha')
        require(git.on_main(source), f'{where}: measured source unresolved or not on the pinned main')
        mi = git.identity(source)
        require(mi is not None, f'{where}: git_source does not resolve the measured source')
        require(ev.hc(mi) == e['measurement_identity_sha256'], f'{where}: measurement identity != git_source')
        si = science_identity(mi)
        require(valid(si, 'science_identity') and ev.hc(si) == e['science_identity_sha256'],
                f'{where}: science identity != contract 6')
        # git_source of this freeze yields only phase pilot (contract 5.4): a reveal entry is invalid.
        require(e['phase'] == mi['phase'] == 'pilot', f'{where}: phase differs from the identity phase')
        t = e['transition']
        if t is not None:
            require(self_digest_ok(t, 'transition_sha256'), f'{where}: transition_sha256 != Hc(transition)')
            require(t['previous_science_identity_sha256'] != t['new_science_identity_sha256'],
                    f'{where}: transition previous and new identities must differ')
        previous = e['entry_sha256']
    return head(genesis, entries)


def duplicate_keys(entries):
    """Contract 5.6 item 2: run keys present more than once. O(n) with a set."""
    seen, dup = set(), set()
    for e in entries:
        (dup if run_key(e) in seen else seen).add(run_key(e))
    return dup


def head(genesis, entries):
    if not entries:
        return {'sequence': 0, 'entry_sha256': ev.hc(genesis)}
    return {'sequence': entries[-1]['sequence'], 'entry_sha256': entries[-1]['entry_sha256']}


def history(genesis, entries):
    """[genesis_sha256, entry 1 sha, ...]: index = sequence. Valid registries only."""
    return [ev.hc(genesis), *(e['entry_sha256'] for e in entries)]


def on_history(witness, chain):
    """Level-1 witness (contract 5.6 item 5, 13.1): head {sequence, entry_sha256} is a prefix of chain (history())."""
    return 0 <= witness['sequence'] < len(chain) and chain[witness['sequence']] == witness['entry_sha256']


def stale(evaluated, reread):
    """Contract 5.6 items 3-4: anything re-read after the evaluation that differs from the evaluated value."""
    return evaluated != reread


def checkpoint_admissible(record_head, checkpoint, checkpoint_history, genesis_sha256):
    """Contract 13.2 (XC01-XC05): checkpoint_history = entry_sha256 of sequences 1..checkpoint.head.sequence of the
    chain ending at checkpoint.head. Admissible iff the history really ends at the committed head, the checkpoint is
    not earlier than the record, and the record head lies on that chain (sequence 0 -> genesis). checkpoint_sha256 is
    the provider's own digest (technology not fixed, D5) and is only syntax-checked."""
    if not (valid(checkpoint, 'external_checkpoint') and valid(record_head, 'registry_head')):
        return False
    chain = [genesis_sha256, *checkpoint_history]
    top = checkpoint['head']
    return (top['sequence'] == len(chain) - 1 and chain[-1] == top['entry_sha256']
            and top['sequence'] >= record_head['sequence'] and on_history(record_head, chain))


def checkpoint_history(genesis, entries, checkpoint_head):
    """History behind a checkpoint head, verified as a hash chain from the head back to genesis over full entries
    (they must form a valid chain: validate() first). Raises RegistryInvalid if the head is not on that chain."""
    chain = history(genesis, entries)
    require(on_history(checkpoint_head, chain), 'checkpoint head is not on the registry chain')
    return chain[1:checkpoint_head['sequence'] + 1]
