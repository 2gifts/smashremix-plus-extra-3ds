"""Source-only roster gate for validated native Remix fighter integrations."""
import argparse
import json
import re
from pathlib import Path

from common import ROOT

CATALOG = ROOT / 'remix/native_fighters.json'
HEADER = ROOT / '3ds/include/native_remix_roster.h'
UI = ROOT / '3ds/include/native_remix_ui.inc'


def load_catalog(path=CATALOG):
    catalog = json.loads(Path(path).read_text())
    if catalog.get('schema') != 1:
        raise ValueError('Unsupported native fighter catalog schema')
    parents = catalog.get('parents')
    fighters = catalog.get('fighters')
    if not isinstance(parents, dict) or not isinstance(fighters, list) or not fighters:
        raise ValueError('Native fighter catalog requires parents and fighters')
    if len(set(parents.values())) != len(parents) or any(not isinstance(v, int) or not 0 <= v < 27 for v in parents.values()):
        raise ValueError('Invalid vanilla parent IDs')
    names, ids = set(), set()
    for fighter in fighters:
        name, kind = fighter['name'], fighter['fkind']
        if not re.fullmatch(r'[A-Z][A-Z0-9]*', name) or name in names or name in parents:
            raise ValueError(f'Invalid or duplicate fighter name: {name}')
        if not isinstance(kind, int) or not 27 <= kind < 256 or kind in ids:
            raise ValueError(f'Invalid or duplicate fighter ID: {kind}')
        if fighter['parent'] not in parents or fighter['registration'] not in ('generic', 'custom'):
            raise ValueError(f'Invalid parent or registration for {name}')
        if not re.fullmatch(r'[A-Z0-9 ]{1,16}', fighter['label']):
            raise ValueError(f'Invalid bottom-screen label for {name}')
        names.add(name)
        ids.add(kind)
    return catalog


def validate_reference(catalog, audit_path, reference_sha256=None):
    """Do not expose a new fighter merely because its ROM struct exists."""
    report = json.loads(Path(audit_path).read_text())
    if report.get('schema') != 2 or (reference_sha256 is not None and
                                     report.get('reference_rom_sha256') != reference_sha256):
        raise ValueError('Fighter audit does not match the pinned reference')
    rows = {row['name']: row for row in report['fighters']}
    for fighter in catalog['fighters']:
        row = rows.get(fighter['name'])
        if row is None or row['fkind'] != fighter['fkind'] or row['parent'] != fighter['parent']:
            raise ValueError(f"Reference fighter mismatch: {fighter['name']}")
        if not row['fixture_data_ready']:
            raise ValueError(f"Reference assets/scripts unready: {fighter['name']}")
        if fighter['registration'] == 'generic' and not row['action_table']['generic_action_table_compatible']:
            raise ValueError(f"Native action table requires a custom registration: {fighter['name']}")


def render_header(catalog):
    lines = [
        '#pragma once',
        '/* Generated from remix/native_fighters.json. Run native_fighter_catalog.py to update. */',
        '/* Temporary parent-card selector until the expanded Remix CSS is native. */',
    ]
    for name, kind in catalog['parents'].items():
        lines.append(f'#define NATIVE_REMIX_{name}_KIND {kind}u')
    for fighter in catalog['fighters']:
        lines.append(f"#define NATIVE_REMIX_{fighter['name']}_KIND {fighter['fkind']}u")
    lines += [
        '#define NATIVE_REMIX_VS_CSS_SCENE 16u',
        'extern volatile unsigned native_remix_selected_fkind[4];',
        '',
        'typedef struct NativeRemixVariant {',
        '    unsigned fkind;',
        '    unsigned parent;',
        '} NativeRemixVariant;',
        '',
        'static const NativeRemixVariant native_remix_variants[] = {',
    ]
    for fighter in catalog['fighters']:
        lines.append(f"    {{NATIVE_REMIX_{fighter['name']}_KIND, NATIVE_REMIX_{fighter['parent']}_KIND}},")
    lines += [
        '};',
        '',
        'static inline unsigned nativeRemixParentKind(unsigned fkind) {',
        '    switch (fkind) {',
    ]
    for fighter in catalog['fighters']:
        lines.append(f"    case NATIVE_REMIX_{fighter['name']}_KIND: return NATIVE_REMIX_{fighter['parent']}_KIND;")
    lines += [
        '    default: return fkind;',
        '    }',
        '}',
        '',
        'static inline unsigned nativeRemixIsVariant(unsigned fkind) {',
        '    return nativeRemixParentKind(fkind) != fkind;',
        '}',
        '',
        'static inline unsigned nativeRemixResolveKind(unsigned parent, unsigned selected) {',
        '    for (unsigned i = 0; i < sizeof(native_remix_variants) / sizeof(native_remix_variants[0]); i++)',
        '        if (native_remix_variants[i].fkind == selected && native_remix_variants[i].parent == parent)',
        '            return selected;',
        '    return parent;',
        '}',
        '',
        'static inline unsigned nativeRemixNextKind(unsigned card, unsigned selected) {',
        '    unsigned parent = nativeRemixParentKind(card);',
        '    unsigned first = 0, found = 0;',
        '    for (unsigned i = 0; i < sizeof(native_remix_variants) / sizeof(native_remix_variants[0]); i++) {',
        '        if (native_remix_variants[i].parent != parent) continue;',
        '        if (!first) first = native_remix_variants[i].fkind;',
        '        if (found) return native_remix_variants[i].fkind;',
        '        if (native_remix_variants[i].fkind == selected) found = 1;',
        '    }',
        '    return found ? 0 : first;',
        '}',
    ]
    return '\n'.join(lines) + '\n'


def render_generic_data(catalog):
    fighters = [row for row in catalog['fighters'] if row['registration'] == 'generic']
    lines = ['/* ROM-derived private include; generated from the validated fighter catalog. */',
             '#include "generic_table_data.inc"']
    lines += [f'#include "{row["name"].lower()}_data.inc"' for row in fighters]
    lines += ['', 'static const NativeRemixGenericDef native_remix_generic_defs[] = {']
    for row in fighters:
        name, prefix = row['name'], 'remix_' + row['name'].lower()
        lines.append('    {' + ', '.join((
            f'NATIVE_REMIX_{name}_KIND', f'NATIVE_REMIX_{row["parent"]}_KIND',
            f'{prefix}_files', f'REMIX_{name}_ATTRIBUTE_OFFSET',
            f'{prefix}_main_motions', f'ARRAY_COUNT({prefix}_main_motions)',
            f'{prefix}_menu_motions', f'&{prefix}_menu_count',
            f'{prefix}_relocate_scripts')) + '},')
    lines += ['};', '']
    return '\n'.join(lines)


def render_ui(catalog):
    lines = ['/* Generated from remix/native_fighters.json. */',
             'static const struct { unsigned kind, art; const char *label; } native_remix_ui[] = {']
    for fighter in catalog['fighters']:
        lines.append(f"    {{{fighter['fkind']}u, {catalog['parents'][fighter['parent']]}u, \"{fighter['label']}\"}},")
    lines += ['};', '']
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    catalog = load_catalog()
    output = render_header(catalog)
    ui_output = render_ui(catalog)
    if args.check:
        if HEADER.read_text() != output or UI.read_text() != ui_output:
            raise SystemExit('Generated native fighter tables are stale; run native_fighter_catalog.py')
    else:
        HEADER.write_text(output)
        UI.write_text(ui_output)


if __name__ == '__main__':
    main()
