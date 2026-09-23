"""Import compiled Fireball.add_to_character profiles into native projectile data.

The armips macro emits a per-fighter jump-table thunk and a 0x30-byte physics
record.  Decode its final ROM bytes; never execute the MIPS code on the 3DS.
"""
import math
import re
import struct
from pathlib import Path

from common import BUILD, sha256, write_json


FIREBALL_BASE = 0x80188e30
PROFILE_SIZE = 0x30
EXPECTED_JUMPS = {'fireball': 0x80155ee4, 'kirby_fireball': 0x80156a54}


def _word(row, table):
    return int.from_bytes(bytes(row['tables'][table]), 'big')


def _thunk_id(ref, address, table):
    words = ref.words(address, 5)
    upper, lower, store, jump, delay = words
    if upper & 0xffff0000 != 0x3c040000 or lower & 0xffff0000 != 0x34840000:
        raise ValueError(f'{table} thunk {address:08x} is not li a0, profile_id')
    if (store, jump, delay) != (0xafa4001c, 0x08000000 | ((EXPECTED_JUMPS[table] >> 2) & 0x03ffffff), 0):
        raise ValueError(f'{table} thunk {address:08x} has unexpected control flow')
    return ((upper & 0xffff) << 16) | (lower & 0xffff)


def extract_fireballs(ref, table_manifest, audit, catalog=None):
    if table_manifest['layouts'].get('fireball') != 4 or table_manifest['layouts'].get('kirby_fireball') != 4:
        raise ValueError('Reference fireball tables do not have 4-byte rows')
    source = ref.path.with_name('src') / 'fireball.asm'
    macro = source.read_text()
    if 'macro add_to_character(id, struct)' not in macro or 'macro struct(name, defaults, duration, max_speed' not in macro:
        raise ValueError('Pinned fireball macro layout changed')
    macro_fighters = set(re.findall(r'(?m)^\s*add_to_character\(Character\.id\.([A-Z0-9]+),', macro))
    selected = {row['name'] for row in catalog['fighters']} if catalog else set()
    audit_by_name = {row['name']: row for row in audit['fighters']}
    rows = []
    other_patches = []
    for fighter in table_manifest['fighters']:
        if 'fireball' not in fighter['changed_from_parent']:
            continue
        name = fighter['name']
        if name not in macro_fighters:
            if name in selected:
                raise ValueError(f'{name}: fireball patch does not use Fireball.add_to_character')
            other_patches.append(name)
            continue
        if 'kirby_fireball' not in fighter['changed_from_parent']:
            raise ValueError(f'{name}: fireball and Kirby copy patches disagree')
        profile_ids = [_thunk_id(ref, _word(fighter, table), table)
                       for table in EXPECTED_JUMPS]
        if profile_ids[0] != profile_ids[1]:
            raise ValueError(f'{name}: fireball and Kirby copy select different profiles')
        address = FIREBALL_BASE + profile_ids[0] * PROFILE_SIZE
        words = ref.words(address, PROFILE_SIZE // 4)
        duration = words[0]
        floats = [struct.unpack('>f', struct.pack('>I', word))[0] for word in words[1:9]]
        data_pointer, reserved = words[9:11]
        palette = struct.unpack('>f', struct.pack('>I', words[11]))[0]
        if not 1 <= duration <= 600 or any(not math.isfinite(x) or abs(x) > 1000 for x in floats):
            raise ValueError(f'{name}: invalid fireball physics at {address:08x}')
        if reserved or not math.isfinite(palette) or not 0 <= palette <= 7:
            raise ValueError(f'{name}: invalid fireball metadata at {address:08x}')
        if not ref.ram_base <= data_pointer < ref.ram_base + 0x400000 or ref.words(data_pointer, 1)[0]:
            raise ValueError(f'{name}: unexpected fireball asset pointer {data_pointer:08x}')
        if not audit_by_name[name]['files'][5]:
            raise ValueError(f'{name}: fireball profile has no special asset file')
        rows.append({'name': name, 'fkind': fighter['fkind'], 'profile_id': profile_ids[0],
                     'profile_address': f'{address:08x}', 'asset_pointer': f'{data_pointer:08x}',
                     'special_file_id': audit_by_name[name]['files'][5], 'lifetime': duration,
                     'physics': floats, 'palette': palette})
    if macro_fighters - {row['name'] for row in rows}:
        raise ValueError('A Fireball.add_to_character source call is absent from the compiled table')
    return {'schema': 1, 'reference_rom_sha256': sha256(ref.path),
            'source_macro': 'Fireball.add_to_character', 'other_fireball_patches': other_patches,
            'profiles': rows}


def _cfloat(value):
    result = format(value, '.9g')
    if '.' not in result and 'e' not in result:
        result += '.0'
    return result + 'F'


def render_rows(catalog, manifest):
    selected = {row['name'] for row in catalog['fighters']}
    rows = [row for row in manifest['profiles'] if row['name'] in selected]
    lines = ['/* Generated from compiled Fireball.add_to_character records. */']
    for row in rows:
        args = [str(row['lifetime']), *(_cfloat(x) for x in row['physics']),
                'NULL', '0', _cfloat(row['palette'])]
        lines.append('    {' + ', '.join(args) + '}, /* ' + row['name'] + ' */')
    return '\n'.join(lines) + '\n'


def render_lookup(catalog, manifest):
    selected = {row['name'] for row in catalog['fighters']}
    rows = [row for row in manifest['profiles'] if row['name'] in selected]
    lines = ['/* Generated index into dWPMarioFireballWeaponAttributes. */']
    for index, row in enumerate(rows, 2):
        lines.append(f'    case NATIVE_REMIX_{row["name"]}_KIND: return {index};')
    return '\n'.join(lines) + '\n'


def write_fireballs(ref, table_manifest, audit, catalog, out):
    manifest = extract_fireballs(ref, table_manifest, audit, catalog)
    write_json(BUILD / 'fighter-fireball-patches.json', manifest)
    out = Path(out)
    (out / 'native_fireball_rows.inc').write_text(render_rows(catalog, manifest))
    (out / 'native_fireball_lookup.inc').write_text(render_lookup(catalog, manifest))
    return manifest
