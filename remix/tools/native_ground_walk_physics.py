"""Import the shared compiled ground-walk physics callback shape.

Both calls resolve to original decomp functions. The only variable words are
the speed and friction float constants loaded into argument registers.
"""

import math
import struct
from pathlib import Path

from classify_action_callbacks import first_return_words
from common import BUILD, sha256, write_json


GROUND_WALK = (
    0x27bdffe8, 0xafbf0014, 0xafa40018, 0x8c840084,
    None, 0x0c03629c, None, 0x0c0361f4,
    0x8fa40018, 0x8fbf0014, 0x03e00008, 0x27bd0018,
)


def decode_ground_walk(ref, address):
    words = ref.words(address, 128)
    length = first_return_words(words)
    if length != len(GROUND_WALK):
        return None
    actual = words[:length]
    if any(expected is not None and got != expected
           for got, expected in zip(actual, GROUND_WALK)):
        return None
    if actual[4] & 0xffff0000 != 0x3c050000 or actual[6] & 0xffff0000 != 0x3c060000:
        return None
    speed, friction = (struct.unpack('>f', struct.pack('>I', (actual[index] & 0xffff) << 16))[0]
                       for index in (4, 6))
    if (not math.isfinite(speed) or not math.isfinite(friction) or
            not 0 < abs(speed) <= 256 or not 0 < friction <= 256):
        return None
    return {'address': f'{address:08x}', 'speed': speed, 'friction': friction,
            'native': f'nativeRemixGroundWalk_{address:08x}'}


def extract_ground_walks(ref, worklist):
    if worklist['reference_rom_sha256'] != sha256(ref.path):
        raise ValueError('Ground-walk callback worklist and pinned ROM differ')
    rows = []
    for row in worklist['targets']:
        decoded = decode_ground_walk(ref, int(row['address'], 16))
        if decoded is not None:
            rows.append({**decoded, 'symbols': row['symbols'], 'uses': len(row['uses'])})
    return {'schema': 1, 'reference_rom_sha256': sha256(ref.path),
            'recognized_callbacks': len(rows),
            'action_table_uses': sum(row['uses'] for row in rows),
            'accepted': rows}


def render_native_code(manifest):
    lines = ['/* Checked compiled ground-walk physics callbacks. */']
    for row in manifest['accepted']:
        lines += [f'void {row["native"]}(GObj *gobj) {{',
                  '    FTStruct *fp = ftGetStruct(gobj);',
                  f'    ftPhysicsSetGroundVelAbsStickRange(fp, {row["speed"].hex()}f, '
                  f'{row["friction"].hex()}f);',
                  '    ftPhysicsSetGroundVelTransferAir(gobj);',
                  '}', '']
    return '\n'.join(lines)


def write_ground_walks(ref, worklist, out):
    manifest = extract_ground_walks(ref, worklist)
    write_json(BUILD / 'native-ground-walk-physics.json', manifest)
    (Path(out) / 'native_ground_walk_physics.inc').write_text(render_native_code(manifest))
    return manifest
