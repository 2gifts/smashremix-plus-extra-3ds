"""Import Remix's assembled per-fighter Japanese hit-sound selection."""
import struct
from pathlib import Path

from common import BUILD, sha256, write_json
from native_results_patches import microcode_count


def extract_hit_sounds(ref, tables, audit, fgm_count):
    if tables['layouts'].get('sound_type') != 1:
        raise ValueError('Hit sound type table is not one byte per fighter')
    code = (ref.path.with_name('src') / 'Character.asm').read_text()
    for marker in ('scope sound_type_J:', 'OS.copy_segment(ORIGINAL_TABLE, 48)',
                   'scope apply_sound_type_:', 'li      a0, sound_type.table',
                   'dh      FGM.hit.J_PUNCH_S', 'dh      FGM.hit.J_KICK_L'):
        if marker not in code:
            raise ValueError('Pinned Japanese hit-sound patch layout changed')
    address = ref.symbols['Character.sound_type_J.table']
    offset = address - ref.ram_base + ref.rom_base
    if address < ref.ram_base or offset < 0 or offset + 48 > len(ref.rom):
        raise ValueError('Unmapped compiled Japanese hit-sound table')
    ids = struct.unpack_from('>24H', ref.rom, offset)
    if not 0 < fgm_count <= 8192 or any(not 0 < item < fgm_count for item in ids):
        raise ValueError('Japanese hit sound exceeds FGM microcode')
    # The patch copies the US table and replaces only punch/kick. Verify that
    # the remaining six families really retain their original compiled IDs.
    if len(ref.rom) < 0xA4500 + 48:
        raise ValueError('Original hit-sound table is truncated')
    original = struct.unpack_from('>24H', ref.rom, 0xA4500)
    if ids[6:] != original[6:]:
        raise ValueError('Japanese hit-sound table changes an unexpected family')
    audited = {row['name']: row['fkind'] for row in audit['fighters']}
    rows = []
    for fighter in tables['fighters']:
        name, fkind = fighter['name'], fighter['fkind']
        if audited.get(name) != fkind or not 27 <= fkind < 256:
            raise ValueError(f'{name}: hit sound fighter does not match audit')
        payload = bytes(fighter['tables']['sound_type'])
        if len(payload) != 1 or payload[0] not in (0, 1):
            raise ValueError(f'{name}: invalid compiled hit sound type')
        rows.append({'name': name, 'fkind': fkind, 'sound_type': payload[0]})
    return {'schema': 1, 'reference_rom_sha256': sha256(ref.path),
            'source_macro': 'Character.sound_type_J.apply_sound_type_',
            'fgm_microcode_count': fgm_count,
            'japanese_hit_fgm': [list(ids[i:i + 3]) for i in range(0, 24, 3)],
            'fighters': rows}


def render_native_rows(manifest):
    lines = ['/* Compiled Character.sound_type and sound_type_J hit FGM tables. */',
             'static const u8 native_remix_hit_sound_type[] = {']
    for row in sorted(manifest['fighters'], key=lambda item: item['fkind']):
        lines.append(f'    [{row["fkind"]}] = {row["sound_type"]}, /* {row["name"]} */')
    lines += ['};', 'static const u16 native_remix_j_hit_fgms[8][3] = {']
    for row in manifest['japanese_hit_fgm']:
        lines.append('    {' + ', '.join(str(item) for item in row) + '},')
    lines += ['};', '']
    return '\n'.join(lines)


def write_hit_sounds(ref, tables, audit, out):
    manifest = extract_hit_sounds(ref, tables, audit, microcode_count(ref))
    if manifest['reference_rom_sha256'] != tables['reference_rom_sha256']:
        raise ValueError('Hit sound and table patches use different ROMs')
    write_json(BUILD / 'fighter-hit-sound-patches.json', manifest)
    (Path(out) / 'native_hit_sound_rows.inc').write_text(render_native_rows(manifest))
    return manifest
