"""Read declarative Character.table_patch_start results from the assembled ROM.

The source macros write into per-fkind tables. Reading the final bytes avoids
trying to emulate nested armips macros or guessing which later patch won.
Only layouts with a known native consumer may be emitted into the 3DS build.
"""
import re
from pathlib import Path

from common import BUILD, sha256, write_json


# Character.set_default_costumes -> Character.table_patch_start(..., 0x8).
# FTCostume is exactly four royal, three team and one debug costume byte.
TABLE_LAYOUTS = {'default_costume': 8, 'entry_action': 8, 'down_bound_fgm': 2}
ENTRY_WIDTHS = (28, 12, 8, 4, 2, 1)
PARENT_IDS = {'MARIO': 0, 'FOX': 1, 'DONKEY': 2, 'SAMUS': 3,
              'LUIGI': 4, 'LINK': 5, 'YOSHI': 6, 'CAPTAIN': 7,
              'KIRBY': 8, 'PIKACHU': 9, 'JIGGLYPUFF': 10, 'NESS': 11}


def discover_layouts(ref, fighter_count):
    """Infer fixed row sizes from consecutive compiled Character tables.

    The assembler reserves one row per fkind. Accept only spans matching that
    shape with at most alignment padding. Tables followed by code or embedded
    data need an explicit layout, otherwise inferring their width is unsafe.
    """
    symbols = sorted((address, match.group(1)) for name, address in ref.symbols.items()
                     if (match := re.fullmatch(r'Character\.([A-Za-z_]+)\.table', name)))
    layouts = dict(TABLE_LAYOUTS)
    for (address, name), (next_address, _) in zip(symbols, symbols[1:]):
        span = next_address - address
        width = next((item for item in ENTRY_WIDTHS if fighter_count * item <= span), None)
        if width is None or span - fighter_count * width > 15:
            continue
        if name in layouts and layouts[name] != width:
            raise ValueError(f'Compiled row width disagrees with {name} patch macro')
        layouts[name] = width
    if not TABLE_LAYOUTS.keys() <= layouts.keys():
        raise ValueError('Required patch table missing from reference')
    return dict(sorted(layouts.items()))


def table_row(ref, table, fkind, width):
    address = ref.symbols[f'Character.{table}.table'] + fkind * width
    offset = ref.rom_base + address - ref.ram_base
    if not 0 <= fkind < 256 or not 0 <= offset <= len(ref.rom) - width:
        raise ValueError(f'{table}[{fkind}] outside pinned reference')
    return list(ref.rom[offset:offset + width])


def extract_table_patches(ref, audit):
    """Machine-readable table patch IR, keyed by actual compiled fkind."""
    fighter_count = max(row['fkind'] for row in audit['fighters']) + 1
    layouts = discover_layouts(ref, fighter_count)
    available = {match.group(1) for name in ref.symbols
                 if (match := re.fullmatch(r'Character\.([A-Za-z_]+)\.table', name))}
    rows = []
    for fighter in audit['fighters']:
        data = {name: table_row(ref, name, fighter['fkind'], width)
                for name, width in layouts.items()}
        parent = PARENT_IDS[fighter['parent']]
        changes = [name for name, width in layouts.items()
                   if data[name] != table_row(ref, name, parent, width)]
        rows.append({'name': fighter['name'], 'fkind': fighter['fkind'],
                     'parent': fighter['parent'], 'tables': data,
                     'changed_from_parent': changes})
    return {'schema': 1, 'reference_rom_sha256': sha256(ref.path),
            'source_macro': 'Character.table_patch_start',
            'native_applied_tables': sorted(TABLE_LAYOUTS),
            'skipped_unverified_layouts': sorted(available - layouts.keys()),
            'layouts': layouts, 'fighters': rows}


def render_native_tables(catalog, manifest):
    if manifest['schema'] != 1 or any(manifest['layouts'].get(name) != width
                                      for name, width in TABLE_LAYOUTS.items()):
        raise ValueError('Incompatible reference table patch manifest')
    rows = {row['name']: row for row in manifest['fighters']}
    lines = ['/* Private compiled Character.table_patch_start results. */']
    table_entries = []
    for fighter in catalog['fighters']:
        if fighter['registration'] != 'generic':
            continue
        row = rows.get(fighter['name'])
        if row is None or row['fkind'] != fighter['fkind'] or row['parent'] != fighter['parent']:
            raise ValueError(f"Costume patch mismatch: {fighter['name']}")
        values = row['tables']['default_costume']
        if len(values) != 8 or any(not 0 <= value <= 0xff for value in values):
            raise ValueError(f"Invalid costume patch: {fighter['name']}")
        royal = ', '.join(map(str, values[:4]))
        team = ', '.join(map(str, values[4:7]))
        lines.append(f'static FTCostume remix_{fighter["name"].lower()}_costume = '
                     f'{{{{{royal}}}, {{{team}}}, {values[7]}}};')
        entry = row['tables']['entry_action']
        down = row['tables']['down_bound_fgm']
        if len(entry) != 8 or len(down) != 2:
            raise ValueError(f"Invalid entry or down-bound patch: {fighter['name']}")
        status_r = int.from_bytes(bytes(entry[:4]), 'big')
        status_l = int.from_bytes(bytes(entry[4:]), 'big')
        fgm = int.from_bytes(bytes(down), 'big')
        if not 0 <= status_r < 512 or not 0 <= status_l < 512:
            raise ValueError(f"Invalid entry action patch: {fighter['name']}")
        table_entries.append(f'    {{&remix_{fighter["name"].lower()}_costume, '
                             f'{{{status_r}, {status_l}}}, {fgm}}},')
    lines += ['', 'static const NativeRemixTablePatch native_remix_table_patches[] = {',
              *table_entries, '};']
    return '\n'.join(lines) + '\n'


def write_reference_tables(ref, audit, catalog, out):
    manifest = extract_table_patches(ref, audit)
    if manifest['reference_rom_sha256'] != audit['reference_rom_sha256']:
        raise ValueError('Table patches and fighter audit use different ROMs')
    write_json(BUILD / 'fighter-table-patches.json', manifest)
    (Path(out) / 'generic_table_data.inc').write_text(render_native_tables(catalog, manifest))
    return manifest
