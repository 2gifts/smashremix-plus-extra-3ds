"""Translate verified parameter-only copies of original N64 callbacks.

The source mod uses OS.copy_segment to duplicate Mario's up-special map
callback and replace its landing-lag LUI. Scan every compiled action target,
compare the entire routine with the user's pinned original ROM, and emit one
native wrapper per distinct lag value. No fighter-name list is maintained.
"""

import hashlib
import json
import math
import struct
from pathlib import Path

from classify_action_callbacks import first_return_words
from common import BUILD, ROOT, read_lock, sha256, write_json


MARIO_HI_MAP_ROM_OFFSET = 0xD0D98
MARIO_HI_MAP_WORDS = 48
LAG_WORD_INDEX = 30
MARIO_HI_MAP_SHA256 = 'ab7be5cc796a24299b4438a1183b098fcb7adf1953527544c83049cfdd09d6e6'


def read_original_callback(path=None):
    """Read only a pinned original callback from the locally owned US ROM."""
    if path is None:
        config = json.loads((ROOT / '3ds/build-config.json').read_text())
        path = Path(config['rom'])
    path = Path(path)
    lock = read_lock()['base_rom']
    if path.stat().st_size != lock['bytes'] or hashlib.sha1(path.read_bytes()).hexdigest() != lock['sha1']:
        raise ValueError('Expected the pinned, unmodified US 1.0 ROM')
    with path.open('rb') as source:
        source.seek(MARIO_HI_MAP_ROM_OFFSET)
        body = source.read(MARIO_HI_MAP_WORDS * 4)
    if hashlib.sha256(body).hexdigest() != MARIO_HI_MAP_SHA256:
        raise ValueError('Original Mario up-special callback changed')
    return list(struct.unpack('>' + 'I' * MARIO_HI_MAP_WORDS, body))


def decode_lag_clone(words, original):
    """Accept the same routine with only the LUI a2 landing lag replaced."""
    if len(words) != MARIO_HI_MAP_WORDS or len(original) != MARIO_HI_MAP_WORDS:
        return None
    if first_return_words(words) != MARIO_HI_MAP_WORDS:
        return None
    if original[LAG_WORD_INDEX] != 0x3c063e8f:
        return None
    if any(actual != expected for index, (actual, expected) in
           enumerate(zip(words, original)) if index != LAG_WORD_INDEX):
        return None
    if words[LAG_WORD_INDEX] & 0xffff0000 != 0x3c060000:
        return None
    high = words[LAG_WORD_INDEX] & 0xffff
    lag = struct.unpack('>f', struct.pack('>I', high << 16))[0]
    return high if math.isfinite(lag) and 0.0 < lag <= 4.0 else None


def extract_clones(ref, worklist, original):
    if worklist['reference_rom_sha256'] != sha256(ref.path):
        raise ValueError('Vanilla-clone worklist and pinned reference ROM differ')
    accepted = []
    for row in worklist['targets']:
        address = int(row['address'], 16)
        words = ref.words(address, MARIO_HI_MAP_WORDS)
        high = decode_lag_clone(words, original)
        if high is None:
            continue
        accepted.append({'address': row['address'],
                         'symbols': row['symbols'],
                         'uses': len(row['uses']),
                         'landing_lag_bits': f'{high:04x}0000',
                         'native': f'nativeRemixMarioHiMapLag_{high:04x}'})
    accepted.sort(key=lambda row: row['address'])
    return {'schema': 1, 'reference_rom_sha256': sha256(ref.path),
            'source_original_rom_offset': f'{MARIO_HI_MAP_ROM_OFFSET:08x}',
            'source_original_callback_sha256': MARIO_HI_MAP_SHA256,
            'copied_words_verified_per_callback': MARIO_HI_MAP_WORDS,
            'permitted_changed_word': LAG_WORD_INDEX,
            'recognized_callbacks': len(accepted),
            'action_table_uses': sum(row['uses'] for row in accepted),
            'accepted': accepted}


def render_native_code(manifest):
    lines = ['/* Full-ROM-checked Mario up-special map clones with compiled landing lag. */',
             'static void nativeRemixMarioHiMapWithLag(GObj *fighter_gobj, f32 lag) {',
             '    FTStruct *fp = ftGetStruct(fighter_gobj);',
             '    if (fp->ga == nMPKineticsAir) {',
             '        if ((fp->motion_vars.flags.flag1 == 0) || (fp->physics.vel_air.y >= 0.0F)) {',
             '            mpCommonCheckFighterProject(fighter_gobj);',
             '        } else if (mpCommonCheckFighterPassCliff(fighter_gobj, ftMarioSpecialHiProcPass) != FALSE) {',
             '            if (fp->coll_data.mask_stat & MAP_FLAG_CLIFF_MASK)',
             '                ftCommonCliffCatchSetStatus(fighter_gobj);',
             '            else ftCommonLandingFallSpecialSetStatus(fighter_gobj, FALSE, lag);',
             '        }',
             '    } else mpCommonSetFighterFallOnEdgeBreak(fighter_gobj);',
             '}', '']
    for high in sorted({int(row['landing_lag_bits'][:4], 16)
                        for row in manifest['accepted']}):
        lag = struct.unpack('>f', struct.pack('>I', high << 16))[0]
        lines += [f'void nativeRemixMarioHiMapLag_{high:04x}(GObj *fighter_gobj) {{',
                  f'    nativeRemixMarioHiMapWithLag(fighter_gobj, {lag.hex()}f);',
                  '}', '']
    return '\n'.join(lines)


def write_clones(ref, worklist, out, original=None):
    manifest = extract_clones(ref, worklist, original or read_original_callback())
    write_json(BUILD / 'native-vanilla-clone-callbacks.json', manifest)
    (Path(out) / 'native_vanilla_clone_callbacks.inc').write_text(render_native_code(manifest))
    return manifest
