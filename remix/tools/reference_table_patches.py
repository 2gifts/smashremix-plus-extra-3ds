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
SPECIAL_DISPATCH_TABLES = frozenset({
    'ground_nsp', 'ground_usp', 'ground_dsp',
    'air_nsp', 'air_usp', 'air_dsp',
})
ENTRY_WIDTHS = (28, 12, 8, 4, 2, 1)
PARENT_IDS = {'MARIO': 0, 'FOX': 1, 'DONKEY': 2, 'SAMUS': 3,
              'LUIGI': 4, 'LINK': 5, 'YOSHI': 6, 'CAPTAIN': 7,
              'KIRBY': 8, 'PIKACHU': 9, 'JIGGLYPUFF': 10, 'NESS': 11}


def source_layouts(source):
    """Recover the row widths passed to Character's table-building macros."""
    clean = '\n'.join(line.split('//', 1)[0] for line in source.splitlines())
    result = {}
    calls = re.compile(r'(?m)^\s*(move_table(?:_12|_14)?|move_jab_3_table|'
                       r'move_rapid_jab_table|id_table(?:_12)?)\(([^)]+)\)')
    for match in calls.finditer(clean):
        macro, args = match.group(1), [part.strip() for part in match.group(2).split(',')]
        name = args[0]
        width = int(args[2], 0) if macro.startswith('move_table') else 4
        if name in result and result[name] != width:
            raise ValueError(f'Conflicting source widths for {name}')
        result[name] = width

    # External fighter files call table_patch_start directly. Its last
    # argument is the per-fkind stride, even for the four-argument offset form.
    for match in re.finditer(r'(?m)^\s*(?:Character\.)?table_patch_start\('
                             r'([A-Za-z_][A-Za-z_0-9]*),([^\n)]*)\)', clean):
        name = match.group(1)
        args = [part.strip() for part in match.group(2).split(',')]
        try:
            width = int(args[-1], 0)
        except ValueError:
            continue  # Macro definition with an entry_size parameter.
        if name in result and result[name] != width:
            raise ValueError(f'Conflicting source widths for {name}')
        result[name] = width

    # Some tables are declared directly rather than through move_table. Read
    # the first NUM_CHARACTERS fill inside the owning scope, before hooks or
    # helper scopes that follow the table data.
    for match in re.finditer(r'(?m)^\s*scope\s+([A-Za-z_][A-Za-z_0-9]*)\s*:?\s*\{', clean):
        name = match.group(1)
        depth, end = 1, match.end()
        while depth and end < len(clean):
            depth += (clean[end] == '{') - (clean[end] == '}')
            end += 1
        if depth:
            raise ValueError(f'Unclosed Character scope {name}')
        body = clean[match.end():end - 1]
        marker = re.search(r'\bconstant\s+TABLE_ORIGIN\(origin\(\)\)', body)
        if marker is None:
            continue
        nested = re.search(r'(?m)^\s*scope\s+', body[marker.end():])
        table_body = body[marker.end():marker.end() + nested.start()] if nested else body[marker.end():]
        fill = re.search(r'(?m)^\s*(?:fill|while)\s+[^\n]*?\bNUM_CHARACTERS\b'
                         r'\s*\)?\s*(?:\*\s*(0x[0-9A-Fa-f]+|\d+))?', table_body)
        if fill is None:
            continue
        width = int(fill.group(1), 0) if fill.group(1) else 1
        if name in result and result[name] != width:
            raise ValueError(f'Conflicting source widths for {name}')
        result[name] = width
    return result


def discover_layouts(ref, fighter_count, source=None):
    """Check source-declared row widths against final assembled table bounds."""
    symbols = sorted((address, match.group(1)) for name, address in ref.symbols.items()
                     if (match := re.fullmatch(r'Character\.([A-Za-z_]+)\.table', name)))
    declared = source_layouts(source) if source is not None else {}
    layouts = dict(TABLE_LAYOUTS)
    for (address, name), (next_address, _) in zip(symbols, symbols[1:]):
        span = next_address - address
        if name in declared:
            width = declared[name]
            if fighter_count * width > span:
                raise ValueError(f'{name} source width exceeds compiled table bounds')
        elif source is None:
            width = next((item for item in ENTRY_WIDTHS if fighter_count * item <= span), None)
            if width is None or span - fighter_count * width > 15:
                continue
        else:
            continue
        if name in layouts and layouts[name] != width:
            raise ValueError(f'Compiled row width disagrees with {name} patch macro')
        layouts[name] = width
    if symbols and symbols[-1][1] in declared:
        name = symbols[-1][1]
        if name in layouts and layouts[name] != declared[name]:
            raise ValueError(f'Compiled row width disagrees with {name} patch macro')
        layouts[name] = declared[name]
    if not TABLE_LAYOUTS.keys() <= layouts.keys():
        raise ValueError('Required patch table missing from reference')
    return dict(sorted(layouts.items()))


def table_row(ref, table, fkind, width):
    address = ref.symbols[f'Character.{table}.table'] + fkind * width
    offset = ref.rom_base + address - ref.ram_base
    if not 0 <= fkind < 256 or not 0 <= offset <= len(ref.rom) - width:
        raise ValueError(f'{table}[{fkind}] outside pinned reference')
    return list(ref.rom[offset:offset + width])


def extract_table_patches(ref, audit, source=None):
    """Machine-readable table patch IR, keyed by actual compiled fkind."""
    fighter_count = max(row['fkind'] for row in audit['fighters']) + 1
    layouts = discover_layouts(ref, fighter_count, source)
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


def validate_generic_dispatch(catalog, manifest):
    rows = {row['name']: row for row in manifest['fighters']}
    if not SPECIAL_DISPATCH_TABLES <= manifest['layouts'].keys():
        raise ValueError('Reference special-dispatch tables are incomplete')
    for fighter in catalog['fighters']:
        if fighter['registration'] != 'generic':
            continue
        row = rows[fighter['name']]
        changed = SPECIAL_DISPATCH_TABLES.intersection(row['changed_from_parent'])
        if changed:
            raise ValueError(f"{fighter['name']}: custom special-entry dispatch needs native code: "
                             + ', '.join(sorted(changed)))


def write_reference_tables(ref, audit, catalog, out):
    source = ref.path.with_name('src') / 'Character.asm'
    manifest = extract_table_patches(ref, audit, source.read_text())
    if manifest['reference_rom_sha256'] != audit['reference_rom_sha256']:
        raise ValueError('Table patches and fighter audit use different ROMs')
    validate_generic_dispatch(catalog, manifest)
    write_json(BUILD / 'fighter-table-patches.json', manifest)
    (Path(out) / 'generic_table_data.inc').write_text(render_native_tables(catalog, manifest))
    return manifest
