"""Import checked copies of vanilla air drift with a compiled speed override.

The mod reuses the original ftPhysicsApplyAirVelDrift branch and call sequence,
then substitutes an expansion helper that passes a fixed maximum speed to the
original stick-drift routine. Scan every action callback for that full pattern;
each distinct compiled speed gets one native wrapper.
"""

import hashlib
import json
import math
import struct
from pathlib import Path

from classify_action_callbacks import first_return_words, jal_target
from common import BUILD, ROOT, read_lock, sha256, write_json


COPIED_ROM_OFFSET = 0x548F0
COPIED_WORDS = 16
COPIED_SHA256 = 'b1a855e6c78da519efd82b2b7b7b637c7a0da3ae4accb30d564b4b4e757e0847'

# The only variable instruction is the direct call to the expansion helper.
MAIN = (
    0x27bdffe0, 0xafbf001c, 0xafb00014, 0xafb10018,
    0x8c900084, 0x8e0e018c, 0x8e1109c8, 0x02002025,
    0x000ec300, 0x07010005, 0x02202825, 0x0c036368,
    0x02002025, 0x10000004, 0x02002025, 0x0c036394,
    0x02202825, 0x02002025, 0x0c0363ea, 0x02202825,
    0x14400006, 0x02002025, None, 0x02202825,
    0x02002025, 0x0c03641d, 0x02202825, 0x8fbf001c,
    0x8fb00014, 0x8fb10018, 0x03e00008, 0x27bd0020,
)
HELPER = (
    0x27bdffd8, 0xafbf0014, 0x00a07025, 0x24050008,
    0x8dc6004c, None, 0x0c0363f2, 0x00000000,
    0x8fbf0014, 0x03e00008, 0x27bd0028,
)


def read_original_segment(path=None):
    if path is None:
        path = Path(json.loads((ROOT / '3ds/build-config.json').read_text())['rom'])
    path = Path(path)
    lock = read_lock()['base_rom']
    if path.stat().st_size != lock['bytes'] or hashlib.sha1(path.read_bytes()).hexdigest() != lock['sha1']:
        raise ValueError('Expected the pinned, unmodified US 1.0 ROM')
    with path.open('rb') as source:
        source.seek(COPIED_ROM_OFFSET)
        data = source.read(COPIED_WORDS * 4)
    if hashlib.sha256(data).hexdigest() != COPIED_SHA256:
        raise ValueError('Original air-drift copy segment changed')
    return list(struct.unpack('>' + 'I' * COPIED_WORDS, data))


def decode_air_drift(ref, address, original):
    words = ref.words(address, len(MAIN))
    if first_return_words(words) != len(MAIN):
        return None
    if any(want is not None and word != want for word, want in zip(words, MAIN)):
        return None
    if words[4:4 + COPIED_WORDS] != original:
        return None
    if words[22] >> 26 != 3:
        return None
    helper_address = jal_target(address + 22 * 4, words[22])
    if helper_address < ref.ram_base:
        return None
    helper = ref.words(helper_address, len(HELPER))
    if first_return_words(helper) != len(HELPER):
        return None
    if any(want is not None and word != want for word, want in zip(helper, HELPER)):
        return None
    if helper[5] & 0xffff0000 != 0x3c070000:
        return None
    high = helper[5] & 0xffff
    speed = struct.unpack('>f', struct.pack('>I', high << 16))[0]
    if not math.isfinite(speed) or not 0.0 < speed <= 128.0:
        return None
    return {'helper_address': f'{helper_address:08x}',
            'max_speed_bits': f'{high:04x}0000'}


def extract_air_drift(ref, worklist, original):
    if worklist['reference_rom_sha256'] != sha256(ref.path):
        raise ValueError('Air-drift worklist and pinned reference ROM differ')
    accepted = []
    for row in worklist['targets']:
        address = int(row['address'], 16)
        decoded = decode_air_drift(ref, address, original)
        if decoded is None:
            continue
        high = int(decoded['max_speed_bits'][:4], 16)
        accepted.append({'address': row['address'], 'symbols': row['symbols'],
                         'uses': len(row['uses']), **decoded,
                         'native': f'nativeRemixAirDriftMax_{high:04x}'})
    accepted.sort(key=lambda row: row['address'])
    return {'schema': 1, 'reference_rom_sha256': sha256(ref.path),
            'source_original_rom_offset': f'{COPIED_ROM_OFFSET:08x}',
            'source_original_segment_sha256': COPIED_SHA256,
            'checked_main_words': len(MAIN), 'checked_helper_words': len(HELPER),
            'recognized_callbacks': len(accepted),
            'action_table_uses': sum(row['uses'] for row in accepted),
            'accepted': accepted}


def render_native_code(manifest):
    lines = ['/* Checked original air drift with a compiled maximum-speed override. */',
             'static void nativeRemixAirDriftWithMax(GObj *gobj, f32 max_speed) {',
             '    FTStruct *fp = ftGetStruct(gobj);',
             '    FTAttributes *attr = fp->attr;',
             '    if (fp->is_fastfall) ftPhysicsApplyFastFall(fp, attr);',
             '    else ftPhysicsApplyGravityDefault(fp, attr);',
             '    if (ftPhysicsCheckClampAirVelXDecMax(fp, attr) == FALSE) {',
             '        ftPhysicsClampAirVelXStickRange(fp, 8, attr->air_accel, max_speed);',
             '        ftPhysicsApplyAirVelXFriction(fp, attr);',
             '    }',
             '}', '']
    for high in sorted({int(row['max_speed_bits'][:4], 16)
                        for row in manifest['accepted']}):
        speed = struct.unpack('>f', struct.pack('>I', high << 16))[0]
        lines += [f'void nativeRemixAirDriftMax_{high:04x}(GObj *gobj) {{',
                  f'    nativeRemixAirDriftWithMax(gobj, {speed.hex()}f);',
                  '}', '']
    return '\n'.join(lines)


def write_air_drift(ref, worklist, out, original=None):
    manifest = extract_air_drift(ref, worklist,
                                 read_original_segment() if original is None else original)
    write_json(BUILD / 'native-air-drift-overrides.json', manifest)
    (Path(out) / 'native_air_drift_overrides.inc').write_text(render_native_code(manifest))
    return manifest
