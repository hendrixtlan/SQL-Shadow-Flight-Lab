"""Portable SHA-256 integrity ledger, not a digital signature or trusted attestation."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def create_ledger(directory: Path, artifacts: list[Path]) -> dict[str, Any]:
    directory = directory.resolve()
    entries: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        absolute = artifact.resolve()
        if not absolute.is_relative_to(directory) or not absolute.is_file():
            raise ValueError('artifacts must be files inside the run directory')
        relative = absolute.relative_to(directory).as_posix()
        entries[relative] = {'sha256': digest(absolute), 'bytes': absolute.stat().st_size}
    return {
        'schema': 'medallion-x.integrity-ledger.v1',
        'scope': 'local integrity check, UNSIGNED; no proof of identity or independent trust',
        'artifacts': dict(sorted(entries.items())),
    }


def verify_ledger(directory: Path) -> list[str]:
    directory = directory.resolve()
    try:
        ledger = json.loads((directory / 'integrity_ledger.json').read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return ['integrity_ledger_missing_or_invalid']
    if ledger.get('schema') != 'medallion-x.integrity-ledger.v1':
        return ['invalid_ledger_schema']
    entries = ledger.get('artifacts')
    if not isinstance(entries, dict) or not entries:
        return ['invalid_ledger_entries']
    errors: list[str] = []
    for name, expected in entries.items():
        if not isinstance(name, str) or not isinstance(expected, dict):
            errors.append('invalid_ledger_entry')
            continue
        artifact = (directory / name).resolve()
        if not artifact.is_relative_to(directory) or not artifact.is_file():
            errors.append(f'missing_or_unsafe:{name}')
        elif digest(artifact) != expected.get('sha256') or artifact.stat().st_size != expected.get('bytes'):
            errors.append(f'hash_mismatch:{name}')
    return errors
