"""Decode the compiled Character.kirby_inhale_struct rows for native use.

The source macro creates a 12-byte row for every expanded fighter. Kirby's
vanilla asset contains only 27 rows, so native gameplay must not index that
asset with Remix fighter IDs.
"""
import math
import struct
from pathlib import Path

from common import BUILD, sha256, write_json


def extract_kirby_rows(ref, table_manifest, audit):
    if table_manifest['layouts'].get('kirby_inhale_struct') != 12:
        raise ValueError('Kirby inhale table is not 12 bytes per fighter')
    source = ref.path.with_name('src') / 'Character.asm'
    code = source.read_text()
    if ('scope kirby_inhale_struct {' not in code or
            'origin kirby_inhale_struct.TABLE_ORIGIN + (id.{name} * 0xC)' not in code):
        raise ValueError('Pinned Kirby inhale macro layout changed')
    audited = {row['name']: row['fkind'] for row in audit['fighters']}
    rows = []
    for fighter in table_manifest['fighters']:
        name, fkind = fighter['name'], fighter['fkind']
        if audited.get(name) != fkind:
            raise ValueError(f'{name}: Kirby metadata does not match fighter audit')
        payload = bytes(fighter['tables']['kirby_inhale_struct'])
        if len(payload) != 12:
            raise ValueError(f'{name}: truncated Kirby inhale row')
        copy_id, hat_id, scale, damage = struct.unpack('>HhfI', payload)
        if copy_id > 255 or not -1 <= hat_id <= 255 or not math.isfinite(scale) or not .1 <= scale <= 8:
            raise ValueError(f'{name}: invalid Kirby copy metadata')
        if not 1 <= damage <= 255:
            raise ValueError(f'{name}: invalid Kirby star damage')
        rows.append({'name': name, 'fkind': fkind, 'copy_id': copy_id,
                     'hat_id': hat_id, 'star_scale': scale, 'star_damage': damage})
    return {'schema': 1, 'reference_rom_sha256': sha256(ref.path),
            'source_macro': 'Character.kirby_inhale_struct', 'fighters': rows}


def render_native_rows(manifest):
    lines = ['/* Private compiled Character.kirby_inhale_struct rows. */',
             'static const NativeRemixKirbyInhaleRow native_remix_kirby_inhale_rows[] = {']
    for row in manifest['fighters']:
        scale = format(row['star_scale'], '.9g')
        if '.' not in scale and 'e' not in scale:
            scale += '.0'
        lines.append(f'    [{row["fkind"]}] = {{{row["copy_id"]}, {row["hat_id"]}, '
                     f'{scale}F, {row["star_damage"]}}}, /* {row["name"]} */')
    lines += ['};', '']
    return '\n'.join(lines)


def write_kirby_rows(ref, table_manifest, audit, out):
    manifest = extract_kirby_rows(ref, table_manifest, audit)
    if manifest['reference_rom_sha256'] != table_manifest['reference_rom_sha256']:
        raise ValueError('Kirby inhale rows and table patches use different ROMs')
    write_json(BUILD / 'fighter-kirby-inhale-patches.json', manifest)
    (Path(out) / 'native_kirby_inhale_rows.inc').write_text(render_native_rows(manifest))
    return manifest
