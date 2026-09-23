"""Resolve compiled entry-effect pointers to shared native vanilla effects.

Most added fighters point at one of the original 27 entry routines. Import the
final pointer table rather than assuming the parent fighter uses the same
entry effect. Expansion-owned routines remain explicit unported targets.
"""
from pathlib import Path

from common import BUILD, sha256, write_json
from reference_table_patches import table_row


def extract_entry_effects(ref, tables, audit):
    if tables['layouts'].get('entry_script') != 4:
        raise ValueError('Entry effect table is not four bytes per fighter')
    source = (ref.path.with_name('src') / 'Character.asm').read_text()
    if ('add_to_table(entry_script, id.{name}, id.{parent}, 0x4)' not in source or
            'scope get_entry_script_:' not in source):
        raise ValueError('Pinned entry effect patch layout changed')
    vanilla = {}
    for fkind in range(27):
        pointer = int.from_bytes(bytes(table_row(ref, 'entry_script', fkind, 4)), 'big')
        if not 0x80000000 <= pointer < ref.ram_base:
            raise ValueError(f'Vanilla entry effect {fkind} has unknown pointer')
        vanilla.setdefault(pointer, fkind)
    symbols = {}
    for name, address in ref.symbols.items():
        symbols.setdefault(address, []).append(name)
    audited = {row['name']: row['fkind'] for row in audit['fighters']}
    rows, unported = [], []
    for fighter in tables['fighters']:
        name, fkind = fighter['name'], fighter['fkind']
        if audited.get(name) != fkind:
            raise ValueError(f'{name}: entry effect fighter does not match audit')
        payload = bytes(fighter['tables']['entry_script'])
        if len(payload) != 4:
            raise ValueError(f'{name}: truncated entry effect pointer')
        pointer = int.from_bytes(payload, 'big')
        if pointer in vanilla:
            effect_kind = vanilla[pointer]
        elif pointer >= ref.ram_base:
            ref.words(pointer, 1)  # Must really be inside the assembled expansion.
            effect_kind = -2
            unported.append({'name': name, 'fkind': fkind,
                             'address': f'{pointer:08x}',
                             'symbols': sorted(symbols.get(pointer, []))})
        else:
            raise ValueError(f'{name}: unknown original entry effect pointer {pointer:08x}')
        rows.append({'name': name, 'fkind': fkind,
                     'reference_pointer': f'{pointer:08x}',
                     'native_effect_kind': effect_kind})
    return {'schema': 1, 'reference_rom_sha256': sha256(ref.path),
            'source_macro': 'Character.get_entry_script_',
            'reused_vanilla_count': len(rows) - len(unported),
            'unported_expansion_targets': unported, 'fighters': rows}


def render_native_rows(manifest):
    lines = ['/* Compiled entry-effect pointers mapped to native vanilla effect kinds. */',
             'static const NativeRemixEntryEffect native_remix_entry_effects[] = {']
    for row in sorted(manifest['fighters'], key=lambda item: item['fkind']):
        lines.append(f'    {{{row["fkind"]}, {row["native_effect_kind"]}}}, '
                     f'/* {row["name"]} */')
    lines += ['};', '']
    return '\n'.join(lines)


def write_entry_effects(ref, tables, audit, out):
    manifest = extract_entry_effects(ref, tables, audit)
    if manifest['reference_rom_sha256'] != tables['reference_rom_sha256']:
        raise ValueError('Entry effects and table patches use different ROMs')
    write_json(BUILD / 'fighter-entry-effect-patches.json', manifest)
    (Path(out) / 'native_entry_effect_rows.inc').write_text(render_native_rows(manifest))
    return manifest
