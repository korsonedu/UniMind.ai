"""Offer reference translations only for the exact published source they translate."""
import hashlib
import json
from pathlib import Path

DIRECTORY = Path(__file__).parent / 'legal_translations'


def with_reference_translation(document):
    metadata = json.loads((DIRECTORY / 'sources.json').read_text())
    source = metadata.get(document['doc_type'])
    if (not source or source['version'] != document['version']
            or source['sha256'] != hashlib.sha256(document['content'].encode()).hexdigest()):
        return document
    return {**document, 'reference_translation': {
        'language': 'en', 'source_version': source['version'],
        'title': 'Privacy Policy' if document['doc_type'] == 'privacy' else 'Terms of Service',
        'content': (DIRECTORY / f"{document['doc_type']}-en.html").read_text(),
    }}
