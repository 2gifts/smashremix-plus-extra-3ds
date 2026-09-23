"""Import the compiled Character.crowd_chant_fgm table for every added fighter."""
from pathlib import Path

from common import BUILD, sha256, write_json
from native_results_patches import microcode_count


def extract_crowd_chants(ref, tables, audit, fgm_count):
    if tables['layouts'].get('crowd_chant_fgm') != 2:
        raise ValueError('Crowd chant table is not two bytes per fighter')
    code = (ref.path.with_name('src') / 'Character.asm').read_text()
    if ('move_table(crowd_chant_fgm, 0xA81A8, 0x2)' not in code or
            'scope get_crowd_chant_fgm_:' not in code or
            'add_to_table(crowd_chant_fgm, id.{name}, id.{parent}, 0x2)' not in code):
        raise ValueError('Pinned crowd chant patch layout changed')
    if not 0 < fgm_count <= 8192:
        raise ValueError('Invalid FGM microcode count')
    audited = {row['name']: row['fkind'] for row in audit['fighters']}
    rows = []
    for fighter in tables['fighters']:
        name, fkind = fighter['name'], fighter['fkind']
        if audited.get(name) != fkind:
            raise ValueError(f'{name}: crowd chant fighter does not match audit')
        payload = bytes(fighter['tables']['crowd_chant_fgm'])
        if len(payload) != 2:
            raise ValueError(f'{name}: truncated crowd chant ID')
        fgm = int.from_bytes(payload, 'big')
        if not 0 < fgm < fgm_count:
            raise ValueError(f'{name}: crowd chant {fgm} exceeds FGM microcode')
        rows.append({'name': name, 'fkind': fkind, 'fgm_id': fgm})
    return {'schema': 1, 'reference_rom_sha256': sha256(ref.path),
            'source_macro': 'Character.get_crowd_chant_fgm_',
            'fgm_microcode_count': fgm_count, 'fighters': rows}


def render_native_rows(manifest):
    lines = ['/* Compiled Character.crowd_chant_fgm rows, indexed by fkind. */',
             'static const u16 native_remix_crowd_chant_fgm[] = {']
    for row in sorted(manifest['fighters'], key=lambda item: item['fkind']):
        lines.append(f'    [{row["fkind"]}] = {row["fgm_id"]}, /* {row["name"]} */')
    lines += ['};', '']
    return '\n'.join(lines)


def write_crowd_chants(ref, tables, audit, out):
    manifest = extract_crowd_chants(ref, tables, audit, microcode_count(ref))
    if manifest['reference_rom_sha256'] != tables['reference_rom_sha256']:
        raise ValueError('Crowd chant and table patches use different ROMs')
    write_json(BUILD / 'fighter-crowd-chant-patches.json', manifest)
    (Path(out) / 'native_crowd_chant_rows.inc').write_text(render_native_rows(manifest))
    return manifest
