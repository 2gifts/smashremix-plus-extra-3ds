"""Import assembled Remix variant identity tables for the native UI.

The source macros patch these rows in several places. Reading the final ROM
captures the last applied value for every fighter, including +EXTRA entries.
The generated include is private build data and is never committed.
"""

from collections import Counter
from pathlib import Path

from common import BUILD, sha256, write_json
from reference_table_patches import table_row


WIDTHS = {'variant_original': 4, 'variant_type': 1,
          'variants_with_same_model': 4}
VARIANT_TYPES = {0, 1, 2, 3, 4, 0xff}


def extract_variant_metadata(ref, patches):
    if (patches.get('schema') != 1 or patches.get('reference_rom_sha256') != sha256(ref.path)
            or any(patches.get('layouts', {}).get(name) != width
                   for name, width in WIDTHS.items())):
        raise ValueError('Variant metadata patch table does not match the reference')
    fighters = patches['fighters']
    if not fighters or len({row['fkind'] for row in fighters}) != len(fighters):
        raise ValueError('Variant metadata patch fighters must be nonempty and unique')
    count = max(row['fkind'] for row in fighters) + 1
    if not 29 <= count <= 256 or any(row['fkind'] < 0 for row in fighters):
        raise ValueError('Invalid compiled fighter count')
    rows = []
    for kind in range(count):
        original = int.from_bytes(bytes(table_row(ref, 'variant_original', kind, 4)), 'big')
        variant_type = table_row(ref, 'variant_type', kind, 1)[0]
        peers = table_row(ref, 'variants_with_same_model', kind, 4)
        if (original >= count or variant_type not in VARIANT_TYPES or
                any(peer >= count for peer in peers)):
            raise ValueError(f'Invalid compiled variant metadata for kind {kind}')
        rows.append({'fkind': kind, 'original': original,
                     'variant_type': variant_type, 'same_model': peers})
    for fighter in fighters:
        kind = fighter['fkind']
        for name, width in WIDTHS.items():
            if fighter['tables'][name] != table_row(ref, name, kind, width):
                raise ValueError(f"Stale compiled {name} row for {fighter['name']}")
    counts = Counter(row['variant_type'] for row in rows)
    return {'schema': 1, 'reference_rom_sha256': sha256(ref.path),
            'compiled_fighter_rows': count, 'variant_type_counts': dict(sorted(counts.items())),
            'rows': rows, 'native_3ds_playable': False}


def render_variant_metadata(report):
    rows = report['rows']
    lines = ['/* Private compiled Character variant identity tables. */',
             'static const NativeRemixVariantMeta native_remix_variant_metadata[] = {']
    for index, row in enumerate(rows):
        if row['fkind'] != index:
            raise ValueError('Variant metadata rows must be dense and ordered')
        peers = ', '.join(map(str, row['same_model']))
        lines.append(f'    {{{row["original"]}, {row["variant_type"]}, {{{peers}}}}},')
    lines += ['};', '']
    return '\n'.join(lines)


def write_variant_metadata(ref, patches, out):
    report = extract_variant_metadata(ref, patches)
    write_json(BUILD / 'variant-metadata.json', report)
    (Path(out) / 'native_variant_metadata.inc').write_text(render_variant_metadata(report))
    return report
