"""Translate the shared compiled Lucas aerial PK Fire velocity callback.

This callback is also referenced by normal Lucas and Japanese Kirby. Match its
entire MIPS body before emitting ARM code; a changed branch, field access, or
floating-point operation must remain unbound until reviewed.
"""

import hashlib
import math
import struct
from pathlib import Path

from classify_action_callbacks import first_return_words
from common import BUILD, sha256, write_json


SYMBOL = 'LucasNSP.air_move_'
NATIVE = 'nativeRemixLucasAirMove'
PATTERN = (
    0x27bdffe8, 0xafa40004, 0xafa80008, 0xafa9000c, 0xe7a00010,
    0xe7a20014, 0x8cc8017c, 0x11000009, 0x00000000, None,
    0x44890000, 0xc4c20044, 0x468010a0, 0x46020002, 0xc4c20048,
    0x46001001, 0xe4c00048, 0x8fa40004, 0x8fa80008, 0x8fa9000c,
    0xc7a00010, 0xc7a20014, 0x27bd0018, 0x03e00008, 0x00000000,
)


def decode_air_move(ref):
    address = ref.symbols.get(SYMBOL)
    if address is None:
        raise ValueError('Compiled Lucas air-move symbol is missing')
    words = ref.words(address, 64)
    if first_return_words(words) != len(PATTERN):
        raise ValueError('Compiled Lucas air-move length changed')
    actual = words[:len(PATTERN)]
    if any(expected is not None and word != expected
           for word, expected in zip(actual, PATTERN)):
        raise ValueError('Compiled Lucas air-move behavior changed')
    if actual[9] & 0xffff0000 != 0x3c090000:  # lui t1, speed-high-half
        raise ValueError('Compiled Lucas air speed is not a float immediate')
    speed = struct.unpack('>f', struct.pack('>I', (actual[9] & 0xffff) << 16))[0]
    if not math.isfinite(speed) or not 0 < speed <= 256:
        raise ValueError('Compiled Lucas air speed is outside native range')
    return {'address': f'{address:08x}', 'native': NATIVE,
            'speed': speed,
            'mips_sha256': hashlib.sha256(struct.pack('>' + 'I' * len(actual), *actual)).hexdigest()}


def render_native(row):
    return ('/* Exact compiled Lucas / N Lucas / J Kirby aerial PK Fire callback. */\n'
            f'void {NATIVE}(GObj *gobj) {{\n'
            '    FTStruct *fp = ftGetStruct(gobj);\n'
            '    if (fp->motion_vars.flags.flag0 != 0)\n'
            f'        fp->physics.vel_air.x -= {row["speed"].hex()}f * fp->lr;\n'
            '}\n')


def write_lucas_air_move(ref, out):
    row = decode_air_move(ref)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'native_lucas_air_move.inc').write_text(render_native(row))
    report = {'schema': 1, 'reference_rom_sha256': sha256(ref.path), **row,
              'scope': 'One exact shared aerial PK Fire callback; full Lucas and Kirby specials are not validated.'}
    write_json(BUILD / 'native-lucas-air-move.json', report)
    return report
