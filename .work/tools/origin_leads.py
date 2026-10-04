"""Deterministic A08 review leads derived from acquired-origin evidence.

Every lead has a stable ID; the reviewed ancestry audit must carry exactly
one disposition per generated lead (checked by test_e0_freeze). Copyright
lines naming only the family's own authors are covered by the Slice D
license review and are not leads here.
"""
import re

import manifests as m

PROVENANCE = re.compile(r'based (?:on|upon)|derived from|adapted from|borrowed from|copied from|taken from|'
                        r'originally|automatically generated|generated (?:by|from)|public domain', re.I)
# Principal authors of each roster project; a notice by another family's author is a cross-family lead.
AUTHORS = {'bzip2': r'Julian Seward', 'curl': r'Daniel Stenberg',
           'libpng': r'Glenn Randers-Pehrson|Guy Eric Schalnat|Andreas Dilger|Cosmin Truta',
           'sqlite': r'D\. Richard Hipp', 'zlib': r'Jean-loup Gailly|Mark Adler', 'zstd': r'Yann Collet'}


def lead_id(kind, family, path, subject):
    return m.digest(['delsk.e0.lead.v1', kind, family, path, subject])


def generate(evidence):
    """Sorted leads {id, kind, family_id, path, subject, source_ids} over all retained members."""
    found = {}

    def add(kind, family, path, subject, source):
        key = kind, family, path, subject
        found.setdefault(key, set()).add(source)

    for row in evidence['members']:
        family, path, source = row['family_id'], row['path'], row['source_id']
        for token in row['origin_tokens']:
            if token != family:
                add('token', family, path, token, source)
        for marker in row['origin_markers']:
            text = marker['text']
            if PROVENANCE.search(text):
                add('marker', family, path, text, source)
            for other, pattern in AUTHORS.items():
                if other != family and re.search(pattern, text):
                    add('foreign_author', family, path, other, source)
    return sorted(({'id': lead_id(*key), 'kind': key[0], 'family_id': key[1], 'path': key[2],
                    'subject': key[3], 'source_ids': sorted(sources)} for key, sources in found.items()),
                  key=lambda v: v['id'])
