"""Prevent the inherited vanilla packager from producing a mislabeled Remix game."""
import json
from pathlib import Path

def require_native_remix():
    root = Path(__file__).resolve().parents[2]
    lock = json.loads((root / 'remix/upstream.lock.json').read_text(encoding='utf-8'))
    if not lock['native_target']['playable']:
        raise SystemExit(
            'Remix +EXTRA native gameplay is not integrated yet. No playable CIA can be built. '
            'See docs/PORTING-STATUS.md and docs/BUILD-3DS.md. '
            'The reference ROM and asset pack are development inputs only.')
