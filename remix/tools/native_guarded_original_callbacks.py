"""Import compiled callbacks guarded by a motion flag before a vanilla call.

The pinned Remix code reuses Captain Falcon's existing turn interrupt across
several unrelated specials. Verify the complete wrapper before binding any
address; the only permitted variation is the compared flag value.
"""

from pathlib import Path

from classify_action_callbacks import first_return_words
from common import BUILD, sha256, write_json


CAPTAIN_TURN = (
    0x8c850084, 0x27bdfff0, 0xafa80004, 0xafa90008,
    0xafbf000c, 0x8ca80180, None, 0x15280003,
    0x00000000, 0x0c0580dc, 0x00000000, 0x8fa80004,
    0x8fa90008, 0x8fbf000c, 0x27bd0010, 0x03e00008,
    0x00000000,
)


def decode_guarded_captain_turn(ref, address):
    words = ref.words(address, 128)
    length = first_return_words(words)
    if length != len(CAPTAIN_TURN):
        return None
    actual = words[:length]
    if any(expected is not None and word != expected
           for word, expected in zip(actual, CAPTAIN_TURN)):
        return None
    if actual[6] & 0xffff0000 != 0x34090000:  # ori t1, zero, compare value
        return None
    return actual[6] & 0xffff


def extract_guarded_original_callbacks(ref, worklist):
    if worklist['reference_rom_sha256'] != sha256(ref.path):
        raise ValueError('Guarded callback worklist and pinned ROM differ')
    accepted = []
    for row in worklist['targets']:
        address = int(row['address'], 16)
        guard = decode_guarded_captain_turn(ref, address)
        if guard is None:
            continue
        accepted.append({'address': row['address'], 'symbols': row['symbols'],
                         'uses': len(row['uses']), 'motion_flag1_value': guard,
                         'native': f'nativeRemixGuardedCaptainTurn_{guard}'})
    return {'schema': 1, 'reference_rom_sha256': sha256(ref.path),
            'recognized_callbacks': len(accepted),
            'action_table_uses': sum(row['uses'] for row in accepted),
            'accepted': accepted}


def render_native_code(manifest):
    lines = ['/* Checked compiled motion-flag guard around the original Captain turn. */']
    for value in sorted({row['motion_flag1_value'] for row in manifest['accepted']}):
        lines += [f'void nativeRemixGuardedCaptainTurn_{value}(GObj *gobj) {{',
                  '    FTStruct *fp = ftGetStruct(gobj);',
                  f'    if (fp->motion_vars.flags.flag1 == {value}u)',
                  '        ftCaptainSpecialHiProcInterrupt(gobj);',
                  '}', '']
    return '\n'.join(lines)


def write_guarded_original_callbacks(ref, worklist, out):
    manifest = extract_guarded_original_callbacks(ref, worklist)
    write_json(BUILD / 'native-guarded-original-callbacks.json', manifest)
    (Path(out) / 'native_guarded_original_callbacks.inc').write_text(
        render_native_code(manifest))
    return manifest
