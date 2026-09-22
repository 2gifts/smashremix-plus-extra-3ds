"""Shared paths and provenance checks for the native Remix integration."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REMIX = ROOT / 'remix'
BUILD = REMIX / 'build'

def read_lock():
    data = json.loads((REMIX / 'upstream.lock.json').read_text(encoding='utf-8'))
    if data['schema'] != 1:
        raise ValueError('Unsupported upstream lock schema')
    return data

def git(repo, *args):
    return subprocess.check_output(
        ['git', '-c', 'safe.directory=' + str(repo.resolve()), '-C', str(repo), *args],
        text=True, encoding='utf-8', errors='replace').strip()

def checked_sources():
    lock = read_lock()
    sources = {}
    for name in ('extra', 'remix'):
        entry = lock[name]
        path = ROOT / entry['path']
        if not (path / '.git').exists():
            raise RuntimeError('Missing upstream sources; run git submodule update --init --recursive')
        actual = git(path, 'rev-parse', 'HEAD')
        if actual != entry['commit']:
            raise RuntimeError(f'{name}: expected {entry["commit"]}, found {actual}')
        if git(path, 'status', '--porcelain', '--untracked-files=no'):
            raise RuntimeError(f'{name}: upstream source was modified; keep changes in the native port')
        sources[name] = path
    return lock, sources

def sha256(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()

def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
